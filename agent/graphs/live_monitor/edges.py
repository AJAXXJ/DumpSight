import logging
from agent.graphs.state import DPDKDiagnosisState

logger = logging.getLogger(__name__)


def edge_after_fetch(state: DPDKDiagnosisState) -> str:
    """指标拉取后：有错误进错误处理，否则进规则检测。"""
    return "handle_error" if state.get("error") else "rule_detection"


def edge_after_rule_detection(state: DPDKDiagnosisState) -> str:
    """
    规则检测后三路分支：
    - 出错              → handle_error
    - 规则有异常        → risk_assessment（跳过语义检测）
    - 规则无异常        → semantic_detection 或 END
      - allow_semantic=True  → semantic_detection（慢速轮询，LLM兜底）
      - allow_semantic=False → END（快速轮询，不触发LLM）
    """
    if state.get("error"):
        return "handle_error"
    if state.get("rule_flags"):
        logger.info(
            "rule flags found, skip semantic | run_id=%s flags=%s",
            state.get("run_id"),
            state.get("rule_flags"),
        )
        return "risk_assessment"
    if not state.get("allow_semantic", True):
        logger.debug("fast-poll mode, skip semantic | run_id=%s", state.get("run_id"))
        return "end"
    return "semantic_detection"


def edge_after_semantic_detection(state: DPDKDiagnosisState) -> str:
    """
    语义检测后三路分支：
    - 出错          → handle_error
    - 语义有异常    → risk_assessment
    - 无异常        → END（本轮正常结束）
    """
    if state.get("error"):
        return "handle_error"
    if state.get("semantic_flags"):
        return "risk_assessment"
    logger.debug("no anomaly detected | run_id=%s", state.get("run_id"))
    return "end"


def edge_after_risk(state: DPDKDiagnosisState) -> str:
    """
    风险评估后三路分支：
    - 需要升级      → escalate_to_fault
    - 需要告警      → alert_generation
    - 冷却期/无需   → END
    """
    if state.get("escalate_to_fault"):
        return "escalate_to_fault"
    if state.get("should_alert"):
        return "alert_generation"
    return "end"


def edge_after_alert(state: DPDKDiagnosisState) -> str:
    """
    告警生成后：
    - 同时需要升级 → escalate_to_fault
    - 否则        → END
    """
    return "escalate_to_fault" if state.get("escalate_to_fault") else "end"
