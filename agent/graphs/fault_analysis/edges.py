from __future__ import annotations

import logging

from graphs.state import DPDKDiagnosisState

logger = logging.getLogger(__name__)


def edge_after_fetch(state: DPDKDiagnosisState) -> str:
    """数据拉取后：有错误则进错误处理，否则进案例检索。"""
    if state.get("error"):
        return "handle_error"
    return "retrieve_cases"


def edge_after_reasoning(state: DPDKDiagnosisState) -> str:
    """
    根因推理后：
    - 有错误          → handle_error
    - 置信度低/无修复步骤 → repair_suggestion（增强节点）
    - 其余            → generate_report
    """
    if state.get("error"):
        return "handle_error"

    low_confidence = state.get("confidence") == "low"
    no_repair_steps = not state.get("repair_steps")

    if low_confidence or no_repair_steps:
        logger.info(
            "routing to repair_suggestion | confidence=%s repair_steps=%d",
            state.get("confidence"),
            len(state.get("repair_steps", [])),
        )
        return "repair_suggestion"

    return "generate_report"


def edge_after_repair(state: DPDKDiagnosisState) -> str:
    """修复建议节点后：始终进报告生成（repair 节点本身不会写 error）。"""
    return "generate_report"
