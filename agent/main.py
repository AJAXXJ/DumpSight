import time
import logging

from agent.graphs.fault_analysis.graph import get_fault_analysis_graph

logger = logging.getLogger(__name__)


def run_fast_poll(
    graph,
    client_id: str,
    pid: int,
    alert_handler=None,
    fault_handler=None,
) -> dict:
    """
    快速轮询（建议 10s 调用一次）。

    只执行规则引擎，不触发 LLM 语义检测，延迟可控在秒级。
    适用于高频检测场景，捕捉规则可覆盖的确定性异常。

    Args:
        graph:         compiled LangGraph
        client_id:     客户端标识
        pid:           DPDK 进程 PID
        alert_handler: 告警回调，可对接 webhook / kafka / redis
        fault_handler: 故障升级回调

    Returns:
        本次执行的完整 result dict
    """
    state = {
        "client_id": client_id,
        "pid": pid,
        "allow_semantic": False,
    }
    logger.info("fast_poll triggered | client=%s pid=%s", client_id, pid)

    try:
        result = graph.invoke(state)

        if alert := result.get("alert"):
            if alert_handler:
                alert_handler(alert)
            logger.warning("alert fired | %s", alert.get("title"))

        if result.get("mode") == "fault_analysis" and fault_handler:
            fault_handler(result)
            logger.critical("escalated to fault analysis | client=%s", client_id)

        return result

    except Exception as e:
        logger.exception("fast_poll error | client=%s | %s", client_id, e)
        return {"error": str(e), "should_alert": False, "escalate_to_fault": False}


def run_slow_poll(
    graph,
    client_id: str,
    pid: int,
    alert_handler=None,
    fault_handler=None,
) -> dict:
    """
    慢速轮询（建议 60s 调用一次）。

    规则引擎无异常时继续触发 LLM 语义检测，捕捉规则盲区，
    如多指标联动劣化、趋势异常等规则无法表达的模式。

    Args:
        graph:         compiled LangGraph
        client_id:     客户端标识
        pid:           DPDK 进程 PID
        alert_handler: 告警回调，可对接 webhook / kafka / redis
        fault_handler: 故障升级回调

    Returns:
        本次执行的完整 result dict
    """
    state = {
        "client_id": client_id,
        "pid": pid,
        "allow_semantic": True,
    }
    logger.info("slow_poll triggered | client=%s pid=%s", client_id, pid)

    try:
        result = graph.invoke(state)

        if alert := result.get("alert"):
            if alert_handler:
                alert_handler(alert)
            logger.warning("alert fired | %s", alert.get("title"))

        if result.get("mode") == "fault_analysis" and fault_handler:
            fault_handler(result)
            logger.critical("escalated to fault analysis | client=%s", client_id)

        return result

    except Exception as e:
        logger.exception("slow_poll error | client=%s | %s", client_id, e)
        return {"error": str(e), "should_alert": False, "escalate_to_fault": False}


def run_fault_analyse(graph, initial_state):
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


def fault_handler(monitor_result):
    
    graph = get_fault_analysis_graph()
    graph.invoke(
        {
            "escalate_result": monitor_result,
        }
    )
