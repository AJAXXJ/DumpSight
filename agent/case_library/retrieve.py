from pathlib import Path
import threading
from agent.case_library.fetcher import build_retrieval_context
from agent.config.llm_factory import get_embedding
from agent.config.settings import get_settings
from agent.case_library.store.faiss_store import FaissStore
from server.repository.case_repository import add_case, get_case, get_case_batch
from tools.logger import logger


BASE_DIR = Path(__file__).parent


class Retrieval:

    def __init__(self):
        self.config = get_settings()

        embeddings = get_embedding()

        self.faiss_store = FaissStore(
            embeddings=embeddings,
            index_path=BASE_DIR / "store" / "data" / "faiss_index",
            json_path=BASE_DIR / "store" / "data" / "library.json",
            template_path=BASE_DIR / "store" / "template" / "case_template.j2",
        )

    def search(self, state):
        query = build_retrieval_context(state)

        # FAISS 检索
        retrieval_results = self.faiss_store.search(
            query, self.config.retriever_top_k, self.config.retriever_score_threshold
        )

        if not retrieval_results:
            return []

        # 保留 score + case_id 映射
        score_map = {
            r["case_id"]: r["score"] for r in retrieval_results if r.get("case_id")
        }

        case_ids = list(score_map.keys())

        # MySQL 批量查询
        meta_cases = get_case_batch(case_ids)

        # 构建最终返回
        cases = []

        for meta_case in meta_cases:

            case_id = meta_case["case_id"]

            cases.append(
                {
                    "score": score_map.get(case_id, 0.0),
                    "case_id": case_id,
                    "signal_name": meta_case["signal_name"],
                    "crash_type": meta_case["crash_type"],
                    "crash_function": meta_case["crash_function"],
                    "main_path": meta_case["main_path"],
                    "missing_libs": meta_case["missing_libs"],
                    "dpdk_subsystems": meta_case["dpdk_subsystems"],
                    "root_cause": meta_case["root_cause"],
                    "repair_steps": meta_case["repair_steps"],
                    "description": meta_case["description"],
                    "log_feature": meta_case["log_feature"],
                    "reference_feature": meta_case["reference_feature"],
                    "anomaly_flags": meta_case["anomaly_flags"]
                }
            )

        # 按 score 排序
        cases.sort(key=lambda x: x["score"], reverse=True)

        return cases

    def add_case(self, case):
        if get_case(case["case_id"]) is not None:
            logger.info(f"ID 为: {case['case_id']} 案例已存在")

        # 数据库插入
        add_case(
            case_id=case["case_id"],
            root_cause=case["root_cause"],
            repair_steps=case["repair_steps"],
            description=case["description"],
            log_feature=case["log_feature"],
            signal_name=case.get("signal_name"),
            crash_type=case.get("crash_type"),
            crash_function=case.get("crash_function"),
            main_path=case.get("main_path"),
            dpdk_subsystems=case.get("dpdk_subsystems"),
            missing_libs=case.get("missing_libs"),
            reference_feature=case.get("reference_feature"),
            anomaly_flags=case.get("anomaly_flags"),
        )

        # faiss 插入
        self.faiss_store.add_case_to_faiss(case)


_rag = None
_rag_lock = threading.Lock()


def get_retrieval():
    global _rag
    with _rag_lock:
        if _rag is None:
            _rag = Retrieval()
    return _rag
