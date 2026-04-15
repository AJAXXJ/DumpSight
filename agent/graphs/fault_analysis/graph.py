from langgraph.graph import END, START, StateGraph
from agent.graphs.fault_analysis.nodes import (
    node_fetch_data,
    node_fetch_data_escalation,
    node_retrieve_cases,
    node_root_cause_reasoning,
    node_root_cause_reasoning_escalation,
    node_repair_suggestion,
    node_generate_report,
    node_handle_error,
)
from agent.graphs.fault_analysis.edges import (
    edge_after_fetch,
    edge_after_retrieve,
    edge_after_root_cause,
)
from agent.graphs.state import DPDKDiagnosisState


def build_fault_analysis_graph():
    """
    故障分析 Graph，支持两套入口：

    正常流程：
        START → fetch_data → retrieve_cases
                  └─(error)→ handle_error → END

    预警升级流程：
        START → fetch_data_escalation → retrieve_cases

    汇合后共用路径：
        retrieve_cases
            ├─(有core_info)→ root_cause_reasoning
            └─(无core_info)→ root_cause_reasoning_escalation
                    ↓（两路汇合）
            ├─(low/无steps)→ repair_suggestion → generate_report → END
            ├─(high)───────→ generate_report → END
            └─(error)──────→ handle_error → END
    """
    b = StateGraph(DPDKDiagnosisState)

    b.add_node("fetch_data", node_fetch_data)
    b.add_node("fetch_data_escalation", node_fetch_data_escalation)
    b.add_node("retrieve_cases", node_retrieve_cases)
    b.add_node("root_cause_reasoning", node_root_cause_reasoning)
    b.add_node("root_cause_reasoning_escalation", node_root_cause_reasoning_escalation)
    b.add_node("repair_suggestion", node_repair_suggestion)
    b.add_node("generate_report", node_generate_report)
    b.add_node("handle_error", node_handle_error)

    # 固定边
    b.add_edge("fetch_data_escalation", "retrieve_cases")
    b.add_edge("repair_suggestion", "generate_report")
    b.add_edge("generate_report", END)
    b.add_edge("handle_error", END)

    # 正常流程入口
    b.add_conditional_edges(
        "fetch_data",
        edge_after_fetch,
        {"retrieve_cases": "retrieve_cases", "handle_error": "handle_error"},
    )

    # 检索后分路
    b.add_conditional_edges(
        "retrieve_cases",
        edge_after_retrieve,
        {
            "root_cause_reasoning": "root_cause_reasoning",
            "root_cause_reasoning_escalation": "root_cause_reasoning_escalation",
        },
    )

    # 两路根因分析汇合
    b.add_conditional_edges(
        "root_cause_reasoning",
        edge_after_root_cause,
        {
            "repair_suggestion": "repair_suggestion",
            "generate_report": "generate_report",
            "handle_error": "handle_error",
        },
    )

    b.add_conditional_edges(
        "root_cause_reasoning_escalation",
        edge_after_root_cause,
        {
            "repair_suggestion": "repair_suggestion",
            "generate_report": "generate_report",
            "handle_error": "handle_error",
        },
    )

    return b.compile(checkpointer=None)


_graph = None


def get_fault_analysis_graph():
    global _graph
    if _graph is None:
        _graph = build_fault_analysis_graph()
    return _graph
