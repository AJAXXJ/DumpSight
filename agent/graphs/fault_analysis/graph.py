from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from agent.graphs.state import DPDKDiagnosisState
from agent.graphs.fault_analysis.nodes import (
    node_fetch_data,
    node_retrieve_cases,
    node_root_cause_reasoning,
    node_repair_suggestion,
    node_generate_report,
    node_handle_error,
)
from agent.graphs.fault_analysis.edges import (
    edge_after_fetch,
    edge_after_reasoning,
    edge_after_repair,
)


def build_fault_analysis_graph(*, checkpointer=None):
    """
    构建并编译故障分析 Graph。

    Args:
        checkpointer: LangGraph Checkpointer 实例。
                      None 时使用 MemorySaver（进程内，适合开发）。
                      生产环境传入 SqliteSaver 或 PostgresSaver。

    Returns:
        编译后的 CompiledGraph，可直接调用 .invoke() / .stream()。
    """
    builder = StateGraph(DPDKDiagnosisState)

    # 注册节点
    builder.add_node("fetch_data",        node_fetch_data)
    builder.add_node("retrieve_cases",    node_retrieve_cases)
    builder.add_node("root_cause",        node_root_cause_reasoning)
    builder.add_node("repair_suggestion", node_repair_suggestion)
    builder.add_node("generate_report",   node_generate_report)
    builder.add_node("handle_error",      node_handle_error)

    # 固定边
    builder.add_edge(START,            "fetch_data")
    builder.add_edge("retrieve_cases", "root_cause")
    builder.add_edge("generate_report", END)
    builder.add_edge("handle_error",    END)

    # 条件边
    # 根据状态动态绝对下一个节点
    builder.add_conditional_edges(
        "fetch_data",
        edge_after_fetch,
        {"retrieve_cases": "retrieve_cases", "handle_error": "handle_error"},
    )
    builder.add_conditional_edges(
        "root_cause",
        edge_after_reasoning,
        {
            "repair_suggestion": "repair_suggestion",
            "generate_report":   "generate_report",
            "handle_error":      "handle_error",
        },
    )
    builder.add_conditional_edges(
        "repair_suggestion",
        edge_after_repair,
        {"generate_report": "generate_report"},
    )

    cp = checkpointer or MemorySaver()
    # TODO 调试禁止使用 checkpointer
    return builder.compile(checkpointer=None)


_graph = None

def get_fault_analysis_graph(*, checkpointer=None):
    """返回模块级单例 Graph checkpointer 仅首次调用时生效 """
    global _graph
    if _graph is None:
        _graph = build_fault_analysis_graph(checkpointer=checkpointer)
    return _graph