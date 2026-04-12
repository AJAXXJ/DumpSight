import logging
from agent.graphs.state import DPDKDiagnosisState

logger = logging.getLogger(__name__)


def edge_after_fetch(state: DPDKDiagnosisState) -> str:
    """指标拉取后：有错误进错误处理，否则进异常检测。"""
    if state.get("error"):
        return "handle_error"
    return "anomaly_detection"


def edge_after_detection(state: DPDKDiagnosisState) -> str:
    """
    异常检测后：
    - 无异常 → END（本轮周期结束，等待下一次触发）
    - 有异常 → risk_assessment
    """
    if state.get("error"):
        return "handle_error"
    if not state.get("anomaly_flags"):
        logger.debug("no anomaly detected | run_id=%s", state.get("run_id"))
        return "end"
    return "risk_assessment"


def edge_after_risk(state: DPDKDiagnosisState) -> str:
    """
    风险评估后（三路分支）：
    - 需要升级      → escalate_to_fault
    - 需要告警      → alert_generation
    - 冷却期内/无需 → END
    """
    if state.get("escalate_to_fault"):
        return "escalate_to_fault"
    if state.get("should_alert"):
        return "alert_generation"
    return "end"


def edge_after_alert(state: DPDKDiagnosisState) -> str:
    """
    告警生成后：
    - 同时需要升级 → escalate_to_fault（告警已发，再升级）
    - 否则        → END
    """
    if state.get("escalate_to_fault"):
        return "escalate_to_fault"
    return "end"