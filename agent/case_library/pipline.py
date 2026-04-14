from agent.case_library.retriever import RetrievedCase
from agent.graphs.state import DPDKDiagnosisState
from tools.logger import logger
from agent.case_library.container import container
from agent.case_library.fetcher import process_core_data


def retriever_top_k_case(state: DPDKDiagnosisState, top_k: int = 3) -> list[RetrievedCase]:
    """
    执行完整的 RAG 检索流程
    """
    try:
        # 对原始崩溃数据进行处理
        processed_core_data = process_core_data(state)

        # 构造 RAG Query
        query = processed_core_data["query"]

        # 知识库检索
        retrieved_cases = container.retriever.search(
            query, k=top_k, cases=processed_core_data["cases"]
        )

        return retrieved_cases
    
    except Exception as e:
        logger.exception(f"RAG 流程未预期异常: {e}")
        return []
