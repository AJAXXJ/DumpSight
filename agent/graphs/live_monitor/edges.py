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

    allow_semantic 由 fetch_metrics 显式写入 State，
    此处 state.get("allow_semantic", True) 读到的是明确透传的值，
    不依赖跨节点的 State 残留。
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

    注意：语义节点写的是 escalate_from_semantic，不是 escalate_to_fault，
    此处不读取升级标志，升级决策由 risk_assessment 统一处理。
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
    - 需要升级      → escalate_to_fault（由 risk_assessment 统一写入）
    - 需要告警      → alert_generation
    - 冷却期/无需   → END

    escalate_to_fault 仅由 risk_assessment 写入，
    此处读到的是最终决策值，不存在双写竞争。
    escalate 优先于 should_alert：即便触发了告警生成条件，
    需要升级时也直接跳过告警生成直接升级，避免重复告警。
    """
    if state.get("escalate_to_fault"):
        return "escalate_to_fault"
    if state.get("should_alert"):
        return "alert_generation"
    return "end"


def edge_after_alert(state: DPDKDiagnosisState) -> str:
    """
    告警生成后：
    - END（正常结束）

    但由于 edge_after_risk 已经在 escalate_to_fault=True 时直接路由到
    escalate_to_fault 节点，alert_generation 实际上永远在
    escalate_to_fault=False 的情况下执行，该分支是死代码。

    现在移除死分支，edge_after_alert 只返回 "end"，
    语义更清晰，也不会因 State 里残留的 escalate_to_fault 值引发误路由。
    """
    return "end"