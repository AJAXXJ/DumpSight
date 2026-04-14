import logging
import uuid
from langchain_core.output_parsers import StrOutputParser

from agent.case_library.rag import get_rag
from agent.config.llm_factory import get_llm
from agent.config.settings import get_settings
from agent.output.output_formatter import (
    FAULT_SCHEMA_PROMPT,
    REPAIR_SCHEMA_PROMPT,
    FaultAnalysisResult,
    RepairSteps,
    output_json_parse,
)
from agent.output.report_formatter import ReportFormatter
from agent.prompts.prompt_builder import PromptBuilder
from agent.prompts.prompt_registry import get_registry
from agent.tools.tool_registry import get_tools

logger = logging.getLogger(__name__)
settings = get_settings()


_llm = get_llm()
_builder = PromptBuilder(registry=get_registry(settings.prompt_version))
_tools = get_tools()


def node_fetch_data(state, config):
    """
    调用五个 Tool 拉取原始数据，写入 State 输入字段。
    任一 Tool 失败则写 error 字段，由条件边路由到错误处理节点。
    """
    run_id = str(uuid.uuid4())
    logger.info("node_fetch_data start | run_id=%s", run_id)

    try:
        client_info = _tools["client_info"].invoke({"client_id": state["client_id"]})
        dpdk_info = _tools["dpdk_info"].invoke(
            {"client_id": state["client_id"], "pid": state["pid"]}
        )
        metrics_1s = _tools["log_1s"].invoke(
            {"client_id": state["client_id"], "pid": state["pid"]}
        )
        metrics_5s = _tools["log_5s"].invoke(
            {"client_id": state["client_id"], "pid": state["pid"]}
        )
        core_info = _tools["core_info"].invoke(
            {
                "client_id": state["client_id"],
                "pid": state["pid"],
                "timestamp": state["timestamp"],
            }
        )
    except Exception as exc:
        logger.exception("node_fetch_data failed | run_id=%s", run_id)
        return {"error": f"数据拉取失败: {exc}", "run_id": run_id}

    return {
        "run_id": run_id,
        "client_info": client_info,
        "dpdk_info": dpdk_info,
        "core_info": core_info,
        "metrics_1s": metrics_1s,
        "metrics_5s": metrics_5s,
        "error": "",
    }


def get_retrieve_description(state, config):
    messages, meta = _builder.build_case_ingestion(
        signal_name=state["core_info"]["meta"]["signal_name"],
        crash_type=state["core_info"]["meta"]["parsed_gdb_output"]["crash_type"],
        crash_function=state["core_info"]["meta"]["parsed_gdb_output"][
            "call_chain_graph"
        ]["crash_function"],
        main_path=state["core_info"]["meta"]["parsed_gdb_output"]["call_chain_llm"][
            "main_path"
        ],
        missing_libs=state["core_info"]["meta"]["parsed_gdb_output"]["shared_libs"][
            "missing_libs"
        ],
        dpdk_subsystems=state["core_info"]["meta"]["parsed_gdb_output"][
            "dpdk_subsystems"
        ],
    )

    try:
        response = _llm.invoke(messages, config=config)
        raw_text = StrOutputParser().invoke(response)
    except Exception as exc:
        logger.warning("生成检索描述失败 | %s", exc)
        raw_text = ""
    state["description"] = raw_text


def node_retrieve_cases(state, config):
    """
    以 core_info + dpdk_version 为查询，检索历史相似案例。
    """
    logger.info("node_retrieve_cases | run_id=%s", state.get("run_id"))

    try:
        get_retrieve_description(state, config)
        cases = get_rag().search(state=state)
    except Exception as exc:
        logger.warning("case retrieval failed, continuing without cases | %s", exc)
        cases = []  # 检索失败不中断流程，降级为无历史案例模式

    logger.info("retrieved %d cases | run_id=%s", len(cases), state.get("run_id"))
    return {"retrieved_cases": cases, "description": state["description"]}


def node_root_cause_reasoning(state, config):
    """
    将原始数据 + 相似案例喂给 LLM，提取根因、调用链、置信度
    """
    logger.info("node_root_cause_reasoning | run_id=%s", state.get("run_id"))

    messages, meta = _builder.build_fault_analysis(
        client_info=state["client_info"],
        dpdk_info=state["dpdk_info"],
        core_info=state["core_info"],
        similar_cases=state.get("retrieved_cases", []),
    )

    try:
        response = _llm.invoke(messages, config=config)
        raw_text = StrOutputParser().invoke(response)
    except Exception as exc:
        logger.exception("LLM call failed | run_id=%s", state.get("run_id"))
        return {"error": f"LLM 调用失败: {exc}"}

    result = output_json_parse(
        raw_text,
        FaultAnalysisResult,
        FAULT_SCHEMA_PROMPT,
        llm_retry_fn=lambda msg: _llm.invoke(msg),
    )

    return {
        "root_cause": result.root_cause,
        "call_chain": result.call_chain,
        "confidence": result.confidence,
        "repair_steps": result.repair_steps,
        "error": "",
    }


def node_repair_suggestion(state, config):
    """
    当 confidence=low 或 repair_steps 为空时，单独调用修复建议模板增强输出。
    confidence=high 且 repair_steps 非空时，由条件边跳过本节点。
    """
    logger.info("node_repair_suggestion | run_id=%s", state.get("run_id"))

    messages, meta = _builder.build_repair_suggestion(
        root_cause=state.get("root_cause", ""),
        dpdk_version=state["client_info"]["envirnoment"]["version"],
        call_chain=state["core_info"]["meta"]["call_chain_llm"],
    )

    try:
        response = _llm.invoke(messages, config=config)
        raw_text = StrOutputParser().invoke(response)
    except Exception as exc:
        logger.warning("repair_suggestion LLM failed, keeping existing steps | %s", exc)
        return {}  # 失败时保留上一节点已有的 repair_steps

    result = output_json_parse(
        raw_text,
        RepairSteps,
        REPAIR_SCHEMA_PROMPT,
        llm_retry_fn=lambda msg: _llm.invoke(msg),
    )

    return {"repair_steps": result.repair_steps, "prompt_meta": meta.as_log_dict()}


def should_add_case(confidence, retrieved_cases, threshold=0.9):
    if confidence.lower() not in ["高", "high"]:
        return False

    if not retrieved_cases:
        return True

    top_score = float(retrieved_cases[0].get("score", 0.0))
    return top_score < threshold


def node_generate_report(state, config):
    """
    将分析结果格式化 并进行案例入库
    """
    logger.info("node_generate_report | run_id=%s", state.get("run_id"))

    # 格式化输出
    formatter = ReportFormatter()
    md_report = formatter.to_markdown(state)
    json_report = formatter.to_json(state)
    # 案例入库
    confidence = state["confidence"].lower()
    retrieved_cases = state.get("retrieved_cases", [])

    if should_add_case(confidence, retrieved_cases):
        get_rag().add_case(
            {
                "case_id": state["run_id"],
                "signal_name": state["core_info"]["meta"]["signal_name"],
                "crash_type": state["core_info"]["meta"]["parsed_gdb_output"][
                    "crash_type"
                ],
                "crash_function": state["core_info"]["meta"]["parsed_gdb_output"][
                    "call_chain_graph"
                ]["crash_function"],
                "main_path": state["core_info"]["meta"]["parsed_gdb_output"][
                    "call_chain_llm"
                ]["main_path"],
                "missing_libs": state["core_info"]["meta"]["parsed_gdb_output"][
                    "shared_libs"
                ]["missing_libs"],
                "dpdk_subsystems": state["core_info"]["meta"]["parsed_gdb_output"][
                    "dpdk_subsystems"
                ],
                "root_cause": state["root_cause"],
                "repair_steps": state["repair_steps"],
                "description": state["description"],
            }
        )
    return {"md_report": md_report, "json_report": json_report, "error": ""}


def node_handle_error(state, config):
    """
    统一错误处理节点。记录日志，生成最小化错误报告。
    """
    error_msg = state.get("error", "未知错误")
    logger.error(
        "fault_analysis error | run_id=%s | %s", state.get("run_id"), error_msg
    )

    report = f"""# DPDK 故障分析报告（异常终止）

                **Run ID**: `{state.get('run_id', 'N/A')}`
                **错误信息**: {error_msg}

                请检查日志并重试。
            """
    return {"report": report.strip()}
