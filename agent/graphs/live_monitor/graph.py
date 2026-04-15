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
                                                              ├─(alert)────→ alert_generation
                                                              │               ├─(escalate)─→ escalate_to_fault → END
                                                              │               └─(ok)───────→ END
                                                              └─(冷却/无需)→ END
    """
    b = StateGraph(DPDKDiagnosisState)

    # 节点注册
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
    b.add_conditional_edges(
        "alert_generation",
        edge_after_alert,
        {"escalate_to_fault": "escalate_to_fault", "end": END},
    )

    # TODO: 调试阶段禁用 checkpointer
    return b.compile(checkpointer=None)


_graph = None


def get_realtime_monitor_graph():
    """返回模块级单例 Graph。"""
    global _graph
    if _graph is None:
        _graph = build_realtime_monitor_graph()
    return _graph



def run_fast_poll(client_id: str, pid: int, thread_id: str = None) -> dict:
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
            "allow_semantic": False,  # 禁用语义检测
        },
        config={"configurable": {"thread_id": thread_id or f"{client_id}:{pid}:fast"}},
    )


def run_slow_poll(client_id: str, pid: int, thread_id: str = None) -> dict:
    """
    慢速轮询（建议 60s 调用一次）：
    规则引擎无异常时继续触发 LLM 语义检测，捕捉规则盲区。
    """
    graph = get_realtime_monitor_graph()
    return graph.invoke(
        {
            "client_id": client_id,
            "pid": pid,
            "allow_semantic": True,  # 允许语义检测
        },
        config={"configurable": {"thread_id": thread_id or f"{client_id}:{pid}:slow"}},
    )
