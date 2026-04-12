from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agent.graphs.state import DPDKDiagnosisState
from agent.graphs.live_monitor.nodes import (
    node_fetch_metrics,
    node_anomaly_detection,
    node_risk_assessment,
    node_alert_generation,
    node_escalate_to_fault,
    node_handle_error,
)
from agent.graphs.live_monitor.edges import (
    edge_after_fetch,
    edge_after_detection,
    edge_after_risk,
    edge_after_alert,
)


def build_realtime_monitor_graph(*, checkpointer=None):
    """
    构建并编译实时预警 Graph。

    Graph 拓扑：

        START
          │
      fetch_metrics
          │
      anomaly_detection ──(无异常)──→ END
          │(有异常)
      risk_assessment ──(冷却/无需)──→ END
          │              ╲(升级)
          │               escalate_to_fault → END
          │(需告警)
      alert_generation ──(仅告警)──→ END
          │(告警+升级)
      escalate_to_fault → END

      任意节点出错 → handle_error → END

    Args:
        checkpointer: 持久化 checkpointer，None 时用 MemorySaver。
                      实时监控场景建议用 SqliteSaver 保留跨周期状态。

    Returns:
        编译后的 CompiledGraph。
    """
    builder = StateGraph(DPDKDiagnosisState)

    # 注册节点
    builder.add_node("fetch_metrics",      node_fetch_metrics)
    builder.add_node("anomaly_detection",  node_anomaly_detection)
    builder.add_node("risk_assessment",    node_risk_assessment)
    builder.add_node("alert_generation",   node_alert_generation)
    builder.add_node("escalate_to_fault",  node_escalate_to_fault)
    builder.add_node("handle_error",       node_handle_error)

    # 固定边
    builder.add_edge(START,               "fetch_metrics")
    builder.add_edge("escalate_to_fault", END)
    builder.add_edge("handle_error",      END)

    # 条件边
    builder.add_conditional_edges(
        "fetch_metrics",
        edge_after_fetch,
        {"anomaly_detection": "anomaly_detection", "handle_error": "handle_error"},
    )
    builder.add_conditional_edges(
        "anomaly_detection",
        edge_after_detection,
        {
            "risk_assessment": "risk_assessment",
            "handle_error":    "handle_error",
            "end":             END,
        },
    )
    builder.add_conditional_edges(
        "risk_assessment",
        edge_after_risk,
        {
            "alert_generation":  "alert_generation",
            "escalate_to_fault": "escalate_to_fault",
            "end":               END,
        },
    )
    builder.add_conditional_edges(
        "alert_generation",
        edge_after_alert,
        {
            "escalate_to_fault": "escalate_to_fault",
            "end":               END,
        },
    )

    cp = checkpointer or MemorySaver()
    # TODO 调试禁止使用 checkpointer
    return builder.compile(checkpointer=None)


_graph = None


def get_realtime_monitor_graph(*, checkpointer=None):
    """返回模块级单例 Graph。"""
    global _graph
    if _graph is None:
        _graph = build_realtime_monitor_graph(checkpointer=checkpointer)
    return _graph