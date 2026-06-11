from pathlib import Path
import threading
from agent.case_library.fetcher import build_retrieval_context
from agent.config.llm_factory import get_embedding
from agent.config.settings import get_settings
from server.service.case_service import search_cases_es_pg

BASE_DIR = Path(__file__).parent


class Retrieval:

    def __init__(self):
        self.config = get_settings()

    def search(self, state):
        description = state.get("description", "")
        if not description:
            state["retrieved_cases"] = []
            return []

        fused_results = search_cases_es_pg(
            query=description,
            bucket="dpdk_case_lib",
            index_name="dumpsight_cases",
            top_k=5,
        )

        return fused_results


_rag = None
_rag_lock = threading.Lock()


def get_retrieval():
    global _rag
    with _rag_lock:
        if _rag is None:
            _rag = Retrieval()
    return _rag
