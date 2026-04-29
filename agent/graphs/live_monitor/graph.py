from langgraph.graph import END, START, StateGraph

from agent.graphs.state import DPDKDiagnosisState
from agent.graphs.live_monitor.nodes import (
    node_fetch_metrics,
    node_rule_detection,
    node_semantic_detection,
    node_risk_assessment,
    node_alert_generation,
    node_escalate_to_fault,
    node_handle_error,
)
from agent.graphs.live_monitor.edges import (
    edge_after_fetch,
    edge_after_rule_detection,
    edge_after_semantic_detection,
    edge_after_risk,
    edge_after_alert,
)


def build_realtime_monitor_graph():
    """
    构建并编译实时预警 Graph。

    拓扑：
        START → fetch_metrics
                  ├─(error)─────────────────────────────────→ handle_error → END
                  └─(ok)──→ rule_detection
                                ├─(error)──────────────────→ handle_error → END
                                ├─(规则有异常)──────────────→ risk_assessment
                                ├─(规则无异常+快速轮询)─────→ END
                                └─(规则无异常+慢速轮询)──→ semantic_detection
                                                              ├─(error)────→ handle_error → END
                                                              ├─(语义有异常)→ risk_assessment
                                                              └─(无异常)───→ END
                                                                    ↓
                                                            risk_assessment
                                                              ├─(escalate)─→ escalate_to_fault → END
                                                              ├─(alert)────→ alert_generation → END
                                                              └─(冷却/无需)→ END

    escalate_to_fault 分支已在 edge_after_risk 处提前路由，
    alert_generation 永远不会在 escalate_to_fault=True 时被执行。
    因此 edge_after_alert 的 escalate 死分支已移除，
    add_conditional_edges 改为 add_edge。

    当前保持禁用状态（调试阶段），同时移除 run_fast/slow_poll 中
    无意义的 thread_id 传参。启用 checkpointer 时需同步评估
    _reset_state 的重置逻辑是否与持久化 State 兼容。
    """
    b = StateGraph(DPDKDiagnosisState)

    b.add_node("fetch_metrics", node_fetch_metrics)
    b.add_node("rule_detection", node_rule_detection)
    b.add_node("semantic_detection", node_semantic_detection)
    b.add_node("risk_assessment", node_risk_assessment)
    b.add_node("alert_generation", node_alert_generation)
    b.add_node("escalate_to_fault", node_escalate_to_fault)
    b.add_node("handle_error", node_handle_error)

    # 固定边
    b.add_edge(START, "fetch_metrics")
    b.add_edge("escalate_to_fault", END)
    b.add_edge("handle_error", END)
    b.add_edge("alert_generation", END)

    # 条件边
    b.add_conditional_edges(
        "fetch_metrics",
        edge_after_fetch,
        {"rule_detection": "rule_detection", "handle_error": "handle_error"},
    )
    b.add_conditional_edges(
        "rule_detection",
        edge_after_rule_detection,
        {
            "risk_assessment": "risk_assessment",
            "semantic_detection": "semantic_detection",
            "handle_error": "handle_error",
            "end": END,
        },
    )
    b.add_conditional_edges(
        "semantic_detection",
        edge_after_semantic_detection,
        {
            "risk_assessment": "risk_assessment",
            "handle_error": "handle_error",
            "end": END,
        },
    )
    b.add_conditional_edges(
        "risk_assessment",
        edge_after_risk,
        {
            "alert_generation": "alert_generation",
            "escalate_to_fault": "escalate_to_fault",
            "end": END,
        },
    )

    return b.compile(checkpointer=None)


_graph = None


def get_realtime_monitor_graph():
    """返回模块级单例 Graph。"""
    global _graph
    if _graph is None:
        _graph = build_realtime_monitor_graph()
    return _graph


def run_fast_poll(client_id: str, pid: int) -> dict:
    """
    快速轮询（建议 10s 调用一次）：
    只执行规则引擎，不触发 LLM，延迟可控在秒级。
    规则有异常时直接告警，无异常时直接结束本轮。
    """
    graph = get_realtime_monitor_graph()
    return graph.invoke(
        {
            "client_id": client_id,
            "pid": pid,
            "allow_semantic": False,
        },
    )


def run_slow_poll(client_id: str, pid: int) -> dict:
    """
    慢速轮询（建议 60s 调用一次）：
    规则引擎无异常时继续触发 LLM 语义检测，捕捉规则盲区。
    """
    graph = get_realtime_monitor_graph()
    return graph.invoke(
        {
            "client_id": client_id,
            "pid": pid,
            "allow_semantic": True,
        },
    )