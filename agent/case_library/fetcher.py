from agent.case_library.render import render_embedding_input_template
from agent.graphs.state import DPDKDiagnosisState
from pathlib import Path


def build_retrieval_context(state: DPDKDiagnosisState) -> dict:
    """
    从 DPDK Core 崩溃原始数据获取关键信息

    :param state: 崩溃原始信息
    :return: 处理后关键崩溃信息
    """
    # 元数据过滤
    signal_name = state["core_info"]["meta"]["signal_name"]  # str
    crash_type = state["core_info"]["meta"]["parsed_gdb_output"]["crash_type"]  # str

    missing_libs = state["core_info"]["meta"]["parsed_gdb_output"]["shared_libs"][
        "missing_libs"
    ]  # list
    dpdk_subsystems = state["core_info"]["meta"]["parsed_gdb_output"][
        "dpdk_subsystems"
    ]  # list

    # 向量检索核心
    crash_function = state["core_info"]["meta"]["parsed_gdb_output"][
        "call_chain_graph"
    ][
        "crash_function"
    ]  # str
    main_path = state["core_info"]["meta"]["parsed_gdb_output"]["call_chain_llm"][
        "main_path"
    ]  # str

    # 描述
    description = state["description"]

    # TODO 加上 LLM 总结
    query = render_embedding_input_template(
        Path(__file__).parent / "store" / "template" / "case_template.j2",
        description,
    )

    return query
