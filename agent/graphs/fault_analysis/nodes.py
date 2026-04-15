import logging
import uuid
from langchain_core.output_parsers import StrOutputParser

from agent.case_library.rag import get_rag
from agent.config.llm_factory import get_llm
from agent.config.settings import get_settings
from agent.output.llm_output_formatter import (
    FAULT_SCHEMA_PROMPT,
    REPAIR_SCHEMA_PROMPT,
    FaultAnalysisResult,
    RepairSteps,
    output_json_parse,
)
from agent.output.report_formatter import ReportFormatter
from agent.prompts.prompt_builder import PromptBuilder
from agent.prompts.prompt_registry import get_registry
from agent.tools.telemetry_feature_tool import (
    build_llm_features,
    log_1s_statistic,
    log_5s_statistic,
)
from agent.tools.tool_registry import get_tools

logger = logging.getLogger(__name__)
settings = get_settings()
_llm = get_llm()
_builder = PromptBuilder(registry=get_registry(settings.prompt_version))
_tools = get_tools()



def node_fetch_data(state, config):
    """
    正常流程数据拉取节点。
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
            {"client_id": state["client_id"], "pid": state["pid"], "seconds": 20}
        )
        metrics_5s = _tools["log_5s"].invoke(
            {"client_id": state["client_id"], "pid": state["pid"], "seconds": 20}
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


def node_fetch_data_escalation(state, config):
    """
    预警升级流程数据准备节点。
    从 escalate_result（由 fault_handler 注入）中提取数据，
    构造与正常流程兼容的 State 字段，无需调用任何 Tool。

    escalate_result 来自 monitor Graph 的完整 result，包含：
    - client_info / dpdk_info：直接复用
    - log_feature：当前系统特征，作为分析主要依据
    - anomaly_flags：触发升级的异常标志列表
    - reference_feature：历史基线，辅助根因判断

    core_info 显式置为 None，供后续边函数判断走哪套分析路径。
    """
    run_id = str(uuid.uuid4())
    escalate_result = state.get("escalate_result", {})

    logger.info(
        "node_fetch_data_escalation start | run_id=%s | flags=%s",
        run_id,
        escalate_result.get("anomaly_flags"),
    )

    return {
        "run_id": run_id,
        "client_info": escalate_result.get("client_info", {}),
        "dpdk_info": escalate_result.get("dpdk_info", {}),
        "log_feature": escalate_result.get("log_feature", {}),
        "anomaly_flags": escalate_result.get("anomaly_flags", []),
        "reference_feature": escalate_result.get("reference_feature", {}),
        "core_info": None,  # 显式标记无 core_info，触发升级分析路径
        "error": "",
    }



def _get_retrieve_description(state, config) -> str:
    """
    根据流程类型生成案例检索描述文本。
    - 正常流程：基于 core_info 的崩溃信息生成
    - 预警升级：基于 anomaly_flags + log_feature.insight 生成
    """
    try:
        if state.get("core_info"):
            # 正常流程：崩溃信息检索描述
            messages, _ = _builder.build_case_ingestion(
                signal_name=state["core_info"]["meta"]["signal_name"],
                crash_type=state["core_info"]["meta"]["parsed_gdb_output"][
                    "crash_type"
                ],
                crash_function=state["core_info"]["meta"]["parsed_gdb_output"][
                    "call_chain_graph"
                ]["crash_function"],
                main_path=state["core_info"]["meta"]["parsed_gdb_output"][
                    "call_chain_llm"
                ]["main_path"],
                missing_libs=state["core_info"]["meta"]["parsed_gdb_output"][
                    "shared_libs"
                ]["missing_libs"],
                dpdk_subsystems=state["core_info"]["meta"]["parsed_gdb_output"][
                    "dpdk_subsystems"
                ],
            )
        else:
            # 预警升级流程：指标异常检索描述
            log_feature = state.get("log_feature", {})
            messages, _ = _builder.build_case_ingestion_escalation(
                anomaly_flags=state.get("anomaly_flags", []),
                insight=log_feature.get("insight", []),
                risk_level=log_feature.get("risk_level", ""),
                risk_breakdown=log_feature.get("risk_breakdown", {}),
                mempool_status=log_feature.get("mempool", {}).get("status", ""),
                heap_status=log_feature.get("heap", {}).get("status", ""),
                cpu_status=log_feature.get("cpu", {}).get("status", ""),
                traffic_trend=log_feature.get("traffic", {}).get("trend", ""),
            )

        raw_text = StrOutputParser().invoke(_llm.invoke(messages, config=config))
    except Exception as exc:
        logger.warning("生成检索描述失败 | %s", exc)
        raw_text = ""

    return raw_text


def node_retrieve_cases(state, config):
    """
    案例检索节点，正常流程和预警升级流程共用。
    基于当前流程类型生成检索描述，检索历史相似案例。
    检索失败不中断流程，降级为无历史案例模式。
    """
    logger.info("node_retrieve_cases | run_id=%s", state.get("run_id"))

    try:
        description = _get_retrieve_description(state, config)
        state["description"] = description
        cases = get_rag().search(state=state)
    except Exception as exc:
        logger.warning("case retrieval failed, continuing without cases | %s", exc)
        cases = []
        description = ""

    logger.info("retrieved %d cases | run_id=%s", len(cases), state.get("run_id"))
    return {"retrieved_cases": cases, "description": description}




def node_root_cause_reasoning(state, config):
    """
    正常流程根因分析节点：基于 core_info + 日志特征进行崩溃根因推断。
    使用 build_fault_analysis prompt，输入包含完整崩溃信息。
    """
    logger.info("node_root_cause_reasoning | run_id=%s", state.get("run_id"))

    statistic_1s = log_1s_statistic(state["metrics_1s"])
    statistic_5s = log_5s_statistic(state["metrics_5s"])
    log_feature = build_llm_features(statistic_1s, statistic_5s, state["metrics_1s"])

    messages, meta = _builder.build_core_fault_analysis(
        client_info=state["client_info"],
        dpdk_info=state["dpdk_info"],
        core_info=state["core_info"],
        log_feature=log_feature,
        similar_cases=state.get("retrieved_cases", []),
    )

    try:
        raw_text = StrOutputParser().invoke(_llm.invoke(messages, config=config))
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
        "log_feature": log_feature,
        "prompt_meta": meta.as_log_dict(),
        "error": "",
    }


def node_root_cause_reasoning_escalation(state, config):
    """
    预警升级流程根因分析节点：基于 log_feature + anomaly_flags 进行指标异常根因推断。
    无 core_info，使用 build_fault_analysis_escalation prompt。
    分析重点是：哪些指标异常、为何异常、如何在系统崩溃前介入处理。
    """
    logger.info("node_root_cause_reasoning_escalation | run_id=%s", state.get("run_id"))

    log_feature = state.get("log_feature", {})

    messages, meta = _builder.build_escalation_fault_analysis(
        client_info=state["client_info"],
        dpdk_info=state["dpdk_info"],
        log_feature=log_feature,
        anomaly_flags=state.get("anomaly_flags", []),
        reference_feature=state.get("reference_feature", {}),
        similar_cases=state.get("retrieved_cases", []),
    )

    try:
        raw_text = StrOutputParser().invoke(_llm.invoke(messages, config=config))
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
        "log_feature": log_feature,
        "prompt_meta": meta.as_log_dict(),
        "error": "",
    }



def node_repair_suggestion(state, config):
    """
    修复建议增强节点，两套流程共用。
    当 confidence=low 或 repair_steps 为空时触发，补充修复建议。
    失败时保留上一节点已有的 repair_steps，不中断流程。
    """
    logger.info("node_repair_suggestion | run_id=%s", state.get("run_id"))

    # 正常流程用 call_chain_llm，升级流程用 anomaly_flags 替代
    call_chain = (
        state["core_info"]["meta"]["call_chain_llm"]
        if state.get("core_info")
        else state.get("anomaly_flags", [])
    )

    messages, meta = _builder.build_repair_suggestion(
        root_cause=state.get("root_cause", ""),
        dpdk_version=state["client_info"]["envirnoment"]["version"],
        call_chain=call_chain,
    )

    try:
        raw_text = StrOutputParser().invoke(_llm.invoke(messages, config=config))
    except Exception as exc:
        logger.warning("repair_suggestion LLM failed, keeping existing steps | %s", exc)
        return {}

    result = output_json_parse(
        raw_text,
        RepairSteps,
        REPAIR_SCHEMA_PROMPT,
        llm_retry_fn=lambda msg: _llm.invoke(msg),
    )

    return {"repair_steps": result.repair_steps, "prompt_meta": meta.as_log_dict()}


def should_add_case(confidence, retrieved_cases, threshold=0.9) -> bool:
    """
    判断是否需要将本次分析结果入库。
    条件：confidence=high 且无高度相似的历史案例（top_score < threshold）。
    """
    if confidence.lower() not in ("高", "high"):
        return False
    if not retrieved_cases:
        return True
    return float(retrieved_cases[0].get("score", 0.0)) < threshold


def node_generate_report(state, config):
    """
    报告生成节点，两套流程共用。
    格式化输出 Markdown 和 JSON 报告，并在满足条件时将案例入库。
    入库字段根据是否有 core_info 自动适配。
    """
    logger.info("node_generate_report | run_id=%s", state.get("run_id"))

    formatter = ReportFormatter()
    report = formatter.to_markdown(state)

    if should_add_case(state.get("confidence", ""), state.get("retrieved_cases", [])):
        case_doc = {
            "case_id": state["run_id"],
            "root_cause": state["root_cause"],
            "repair_steps": state["repair_steps"],
            "description": state.get("description", ""),
            "log_feature": state.get("log_feature", {}),
        }

        if state.get("core_info"):
            # 正常流程：附加崩溃信息
            gdb = state["core_info"]["meta"]["parsed_gdb_output"]
            case_doc.update(
                {
                    "signal_name": state["core_info"]["meta"]["signal_name"],
                    "crash_type": gdb["crash_type"],
                    "crash_function": gdb["call_chain_graph"]["crash_function"],
                    "main_path": gdb["call_chain_llm"]["main_path"],
                    "missing_libs": gdb["shared_libs"]["missing_libs"],
                    "dpdk_subsystems": gdb["dpdk_subsystems"],
                }
            )
        else:
            # 预警升级流程：附加异常标志信息
            case_doc.update(
                {
                    "anomaly_flags": state.get("anomaly_flags", []),
                    "reference_feature": state.get("reference_feature", {}),
                }
            )

        get_rag().add_case(case_doc)

    return {"report": report, "error": ""}


def node_handle_error(state, config):
    """
    统一错误处理节点，两套流程共用。
    记录日志，生成最小化错误报告。
    """
    error_msg = state.get("error", "未知错误")
    logger.error(
        "fault_analysis error | run_id=%s | %s", state.get("run_id"), error_msg
    )

    report = (
        f"# DPDK 故障分析报告（异常终止）\n\n"
        f"**Run ID**: `{state.get('run_id', 'N/A')}`\n"
        f"**错误信息**: {error_msg}\n\n"
        f"请检查日志并重试。"
    )
    return {"report": report}
