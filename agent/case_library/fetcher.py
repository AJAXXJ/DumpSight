from agent.graphs.state import DPDKDiagnosisState
from jinja2 import Template
from server.repository.crash_case_meta_repository import filter_crash_case_meta
from tools.logger import logger
from pathlib import Path


def process_core_data(state: DPDKDiagnosisState) -> dict:
    """
    从 DPDK Core 崩溃原始数据获取关键信息

    :param state: 崩溃原始信息
    :return: 处理后关键崩溃信息
    """
    # 元数据过滤
    signal_name = state["meta"]["signal_name"]  # str
    crash_type = state["meta"]["parsed_gdb_output"]["crash_type"]  # str

    missing_libs = state["meta"]["parsed_gdb_output"]["shared_libs"][
        "missing_libs"
    ]  # list
    dpdk_subsystems = state["meta"]["parsed_gdb_output"]["dpdk_subsystems"]  # list

    # 向量检索核心
    crash_function = state["meta"]["parsed_gdb_output"]["call_chain_graph"][
        "crash_function"
    ]  # str
    main_path = state["meta"]["parsed_gdb_output"]["call_chain_llm"]["main_path"]  # str

    # crash_case 元数据检索
    cases = filter_crash_case_meta(crash_type, signal_name)
    logger.info(f"元数据检索到相似案例：{len(cases)} 个")

    # TODO 加上 LLM 总结
    query = render_embedding_input_template(
        Path(__file__).parent / "knowledge" / "template" / "case_template.j2",
        signal_name,
        crash_type,
        crash_function,
        main_path,
        missing_libs,
        dpdk_subsystems,
    )

    return {
        "cases": cases,
        "query": query,
        "meta": {
            "signal_name": signal_name,
            "crash_type": crash_type,
            "missing_libs": missing_libs,
            "dpdk_subsystems": dpdk_subsystems,
            "crash_function": crash_function,
            "main_path": main_path,
        },
    }


def render_embedding_input_template(
    template,
    signal_name,
    crash_type,
    crash_function,
    main_path,
    missing_libs,
    dpdk_subsystems,
):
    """
    渲染 j2 模板 根据 template 分为 case 和 query
    """
    template_str = open(template).read()
    template = Template(template_str)

    embedding_input = template.render(
        signal_name=signal_name,
        crash_type=crash_type,
        crash_function=crash_function,
        main_path=main_path,
        missing_libs=missing_libs,
        dpdk_subsystems=dpdk_subsystems,
    )

    return embedding_input
