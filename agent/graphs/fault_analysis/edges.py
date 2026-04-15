import logging

logger = logging.getLogger(__name__)


def edge_after_fetch(state):
    """数据拉取后 有错误则进错误处理 否则进案例检索"""
    if state.get("error"):
        return "handle_error"
    return "retrieve_cases"


def edge_after_retrieve(state) -> str:
    """
    案例检索后：根据是否有 core_info 决定走哪套根因分析路径。
    - 有 core_info → 崩溃根因分析（core dump 路径）
    - 无 core_info → 指标异常根因分析（预警升级路径）
    """
    if state.get("core_info"):
        return "root_cause_reasoning"
    return "root_cause_reasoning_escalation"


def edge_after_root_cause(state) -> str:
    """
    根因分析后：
    - 出错            → handle_error
    - confidence=low 或 repair_steps 为空 → repair_suggestion 增强
    - 否则            → generate_report
    """
    if state.get("error"):
        return "handle_error"
    confidence = state.get("confidence", "").lower()
    repair_steps = state.get("repair_steps")
    if confidence in ("low", "低") or not repair_steps:
        return "repair_suggestion"
    return "generate_report"


def edge_after_repair(state):
    """修复建议节点后 始终进报告生成 repair 节点本身不会写 error"""
    return "generate_report"
