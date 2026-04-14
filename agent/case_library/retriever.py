import faiss
import numpy as np
from tools.logger import logger
from dataclasses import dataclass
from langchain_openai import OpenAIEmbeddings
from agent.config.settings import get_settings
from agent.case_library.knowledge import FaissStore
from server.models.client.crash_case_meta import CrashCaseMeta


@dataclass
class RetrievedCase:
    score: float
    root_cause: str
    repair_steps: str
    case_id: int | None = None


class Retriever:
    def __init__(self):
        """
        初始化检索器，内部持有 FaissStore 实例。

        :param config: 包含 LLM_API_KEY / LLM_BASE_URL / EMBED_MODEL 的配置字典
        :raises KnowledgeBaseError: FaissStore 初始化失败时透传异常
        """
        config = get_settings()
        embeddings = OpenAIEmbeddings(
            model=config["embedding_model"],
            openai_api_key=config["openai_api_key"],
            openai_api_base=config["openai_api_base"],
        )
        self._store = FaissStore(embeddings)

    def search(
        self,
        query: str,
        k: int = 3,
        cases: list[CrashCaseMeta] = None,
        score_threshold: float = 0.8,
    ) -> list[RetrievedCase]:
        query_vector = np.array(
            [self._store.embeddings.embed_query(query)], dtype=np.float32
        )

        # 建立 faiss_index -> doc 映射
        index_to_doc = {idx: doc for idx, doc in self._store.docstore._dict.items()}

        # 按 case_ids 过滤目标 faiss index
        if cases:
            case_id_set = {item["case_id"] for item in cases}
            target_indices = [
                idx
                for idx, doc in index_to_doc.items()
                if doc.metadata.get("case_id") in case_id_set
            ]
        else:
            target_indices = list(index_to_doc.keys())

        if not target_indices:
            logger.info("过滤后无匹配案例。")
            return []

        # 重构子向量并建临时索引
        sub_vectors = np.array(
            [self._store.index.reconstruct(i) for i in target_indices],
            dtype=np.float32,
        )
        sub_index = faiss.IndexFlatIP(sub_vectors.shape[1])
        sub_index.add(sub_vectors)

        scores, local_indices = sub_index.search(
            query_vector, k=min(k, len(target_indices))
        )

        case_id_to_meta = {item["case_id"]: item for item in cases} if cases else {}

        retrieved = []
        for score, local_idx in zip(scores[0], local_indices[0]):
            if local_idx == -1 or score < score_threshold:
                continue

            doc = index_to_doc[target_indices[local_idx]]
            case_id = doc.metadata.get("case_id")
            meta = case_id_to_meta.get(case_id, {})

            retrieved.append(
                RetrievedCase(
                    score=float(score),
                    root_cause=meta.get("root_cause", "暂无根因"),
                    repair_steps=meta.get("repair_steps", "暂无修复步骤"),
                    case_id=case_id,
                )
            )

        return retrieved
