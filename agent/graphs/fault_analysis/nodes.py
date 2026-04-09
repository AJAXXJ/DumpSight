import re
import logging
import uuid
from langchain_core.output_parsers import StrOutputParser
from agent.config.llm_factory import get_llm
from agent.config.settings import get_settings
# from case_library.retriever import CaseRetriever
from agent.prompts.prompt_builder import PromptBuilder
from agent.prompts.prompt_registry import get_registry
from agent.tools.tool_registry import get_tools

logger = logging.getLogger(__name__)
settings = get_settings()


_llm = get_llm()
_builder = PromptBuilder(registry=get_registry(settings.prompt_version))
# _retriever = CaseRetriever()
_tools = get_tools()


def node_fetch_data(state, config):
    """
    调用五个 Tool 拉取原始数据，写入 State 输入字段。
    任一 Tool 失败则写 error 字段，由条件边路由到错误处理节点。
    """
    run_id = str(uuid.uuid4())
    logger.info("node_fetch_data start | run_id=%s", run_id)

    try:
        client_info = _tools["client_info"].invoke({state['client_id']})
        dpdk_info = _tools["dpdk_info"].invoke({state['client_id'], state['pid']})
        metrics_1s = _tools["log_1s"].invoke({state['client_id'], state['pid']})
        metrics_5s = _tools["log_5s"].invoke({state['client_id'], state['pid']})
        core_info = _tools["core_info"].invoke({state['client_id'], state['pid'], state['timestamp']})
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


def node_retrieve_cases(state, config):
    """
    以 core_info + dpdk_version 为查询，检索历史相似案例。
    """
    logger.info("node_retrieve_cases | run_id=%s", state.get("run_id"))

    try:
        # cases = _retriever.search(
        #     query=state["core_info"],
        #     dpdk_version=state["client_info"].get("dpdk_version"),
        #     top_k=settings.retriever_top_k,
        # )
        cases = []
    except Exception as exc:
        logger.warning("case retrieval failed, continuing without cases | %s", exc)
        cases = []  # 检索失败不中断流程，降级为无历史案例模式

    logger.info("retrieved %d cases | run_id=%s", len(cases), state.get("run_id"))
    return {"retrieved_cases": cases}


def node_root_cause_reasoning(state, config):
    """
    将原始数据 + 相似案例喂给 LLM，提取根因、调用链、置信度
    """
    logger.info("node_root_cause_reasoning | run_id=%s", state.get("run_id"))

    messages, meta = _builder.build_fault_analysis(
        client_info=state["client_info"],
        dpdk_info=state["dpdk_info"],
        core_info=state["core_info"],
        similar_cases=state.get("retrieved_cases", [])
    )

    try:
        response = _llm.invoke(messages, config=config)
        raw_text = StrOutputParser().invoke(response)
    except Exception as exc:
        logger.exception("LLM call failed | run_id=%s", state.get("run_id"))
        return {"error": f"LLM 调用失败: {exc}"}

    parsed = _parse_reasoning_output(raw_text)
    parsed["prompt_meta"] = meta.as_log_dict()
    return parsed


def _parse_reasoning_output(raw):
    """
    从 LLM 输出的结构化文本中提取各字段。
    模板约定输出格式为编号列表（1. 根因 2. 触发路径 ...）。
    解析失败时将原文整体写入 root_cause，保证流程不中断。
    """
    sections: dict[int, str] = {}
    for m in re.finditer(
        r"^\s*(\d)\.\s+[^\n]*\n([\s\S]*?)(?=^\s*\d\.|$)", raw, re.MULTILINE
    ):
        idx = int(m.group(1))
        body = m.group(2).strip()
        sections[idx] = body

    # 1=根因 2=触发路径 3=置信度 4=修复建议 5=历史案例匹配
    confidence_raw = sections.get(3, "").lower()
    if "高" in confidence_raw or "high" in confidence_raw:
        confidence = "high"
    elif "低" in confidence_raw or "low" in confidence_raw:
        confidence = "low"
    else:
        confidence = "medium"

    repair_raw = sections.get(4, "")
    repair_steps = [
        line.lstrip("-•· 0123456789.").strip()
        for line in repair_raw.splitlines()
        if line.strip()
    ]

    call_chain_raw = sections.get(2, "")
    call_chain = [
        line.lstrip("-•· ").strip()
        for line in call_chain_raw.splitlines()
        if line.strip()
    ]

    return {
        "root_cause": sections.get(1, raw),
        "call_chain": call_chain,
        "confidence": confidence,
        "repair_steps": repair_steps,
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
        dpdk_version=state["client_info"].get("dpdk_version", "unknown"),
        crash_context={
            "crash_stack": state.get("crash_stack", ""),
            "call_chain": state.get("call_chain", []),
        },
    )

    try:
        response = _llm.invoke(messages, config=config)
        raw_text = StrOutputParser().invoke(response)
    except Exception as exc:
        logger.warning("repair_suggestion LLM failed, keeping existing steps | %s", exc)
        return {}  # 失败时保留上一节点已有的 repair_steps

    steps = [
        line.lstrip("-•· 0123456789.").strip()
        for line in raw_text.splitlines()
        if line.strip()
    ]
    return {"repair_steps": steps, "prompt_meta": meta.as_log_dict()}


def node_generate_report(state, config):
    """
    将分析结果格式化为 Markdown 报告，写入 state["report"]。
    纯字符串拼接，不再调用 LLM，保证确定性输出。
    """
    logger.info("node_generate_report | run_id=%s", state.get("run_id"))

    confidence_label = {"high": "高", "medium": "中", "low": "低"}.get(
        state.get("confidence", "medium"), "中"
    )
    steps_md = "\n".join(
        f"{i+1}. {s}" for i, s in enumerate(state.get("repair_steps", []))
    )
    chain_md = "\n".join(f"- `{f}`" for f in state.get("call_chain", []))
    cases_md = "\n".join(
        f"- [{c.get('case_id','?')}] {c.get('root_cause','')} "
        f"(相似度 {c.get('score', 0):.2f})"
        for c in state.get("retrieved_cases", [])
    )

    report = f"""# DPDK 故障分析报告

**Run ID**: `{state.get('run_id', 'N/A')}`
**客户端**: {state['client_info'].get('client_id', 'N/A')}
**DPDK 版本**: {state['client_info'].get('dpdk_version', 'N/A')}

## 根因
{state.get('root_cause', '未确定')}

**置信度**: {confidence_label}

## 调用链
{chain_md or '- 未能还原'}

## 修复建议
{steps_md or '暂无'}

## 参考历史案例
{cases_md or '- 无匹配案例'}
"""
    return {"report": report.strip(), "error": ""}


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
