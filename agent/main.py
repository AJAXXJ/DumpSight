import time
import logging
from typing import Callable, Optional

from agent.graphs.live_monitor.graph import get_realtime_monitor_graph

logger = logging.getLogger(__name__)


def run_realtime_monitor(
    graph,
    initial_state,
    alert_handler=None,
    fault_handler=None,
):
    """
    heartbeat 触发的单次 DPDK 监控执行。
    每次客户端 heartbeat 到达时调用一次，执行完整的监控分析流程后返回。

    Args:
        graph:             compiled LangGraph
        heartbeat_payload: heartbeat 携带的数据，至少包含 client_id 和 pid
        alert_handler:     告警回调，可对接 webhook / kafka / redis
    Returns:
        本次执行的完整 result dict
    """
    state = dict(initial_state)
    logger.info(
        "realtime monitor triggered | client=%s pid=%s",
        state.get("client_id"),
        state.get("pid"),
    )

    try:
        result = graph.invoke(state)

        if alert := result.get("alert"):
            # TODO

            if alert_handler:
                alert_handler(alert)
            logger.warning("alert fired | %s", alert.get("title"))

        if result.get("mode") == "fault_analysis" and fault_handler:
            # TODO

            fault_handler(result)
            logger.critical(
                "escalated to fault analysis | client=%s",
                state.get("client_id"),
            )

        return result

    except Exception as e:
        logger.exception(
            "monitor execution error | client=%s | %s",
            state.get("client_id"),
            e,
        )
        return {"error": str(e), "should_alert": False, "escalate_to_fault": False}


def run_fault_anlyse(graph, initial_state):
    """
    启动故障分析图，执行每个节点的逻辑并管理状态的转换。

    Args:
        graph: 编译后的 LangGraph。
        initial_state: 初始状态，包含故障分析的必要信息，如 `client_id`，`pid` 等。
    """
    state = dict(initial_state)

    logger.info(
        "Fault analysis started | client=%s pid=%s",
        state.get("client_id"),
        state.get("pid"),
    )

    start_time = time.time()

    result = graph.invoke(state)

    end_time = time.time()

    analyse_time = round(end_time - start_time, 4)

    return analyse_time, result
