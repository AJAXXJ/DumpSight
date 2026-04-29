import logging
import re
import threading
from dataclasses import dataclass
from agent.knowledge.chunking import Chunk
from tools.pgvector_util import get_pgvector_util

logger = logging.getLogger(__name__)


def _safe_table_name(namespace: str) -> str:
    return "vs_" + re.sub(r"[^a-zA-Z0-9]", "_", namespace)


@dataclass
class SearchResult:
    id: str
    content: str
    score: float
    metadata: dict


class VectorStoreUtil:
    """
    向量存储检索工具类。
    封装 pgvector 的表管理、写入、删除、检索，
    调用方只需关心 namespace / file_id / chunks / vectors。
    """

    def __init__(self, namespace: str, dim: int):
        """
        namespace: 用于隔离不同业务的表，如 bucket 名、项目 id 等
        dim:       embedding 向量维度
        """
        self.table = _safe_table_name(namespace)
        self.dim = dim
        self._ensure_table()

    def _ensure_table(self):
        get_pgvector_util().create_table(self.table, self.dim)

    def store(
        self,
        file_id: str,
        chunks: list[str] | list[Chunk],
        vectors: list[list[float]],
    ):
        """
        批量写入分块文本和对应向量。
        兼容 list[str] 与 list[Chunk] 两种输入。
        chunks 与 vectors 须严格对齐（由 embed_chunks 保证）。
        """
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks 数量({len(chunks)}) 与 vectors 数量({len(vectors)}) 不一致"
            )

        records = []
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            if isinstance(chunk, Chunk):
                records.append(
                    {
                        "id": f"{chunk.source_key}_{chunk.index}",
                        "content": chunk.text,
                        "embedding": vector,
                        "metadata": {
                            "char_start": chunk.char_start,
                            "filetype": chunk.filetype,
                            **chunk.metadata,
                        },
                    }
                )
            else:
                records.append(
                    {
                        "id": f"{file_id}_{idx}",
                        "content": chunk,
                        "embedding": vector,
                        "metadata": {},
                    }
                )

        get_pgvector_util().batch_insert_vectors(self.table, records)
        logger.info(f"写入 {len(records)} 条向量到表 {self.table}")

    def delete(self, file_id: str):
        """删除某文件的全部 chunk。"""
        get_pgvector_util().delete_by_etag(self.table, file_id)
        logger.info(f"已删除 file_id={file_id} 的全部向量")

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """
        相似度检索，返回 list[SearchResult]。
        """

        rows = get_pgvector_util().search_similar(self.table, query_vector, top_k)
        return [
            SearchResult(
                id=row[0],
                content=row[1],
                score=row[2],
                metadata=row[3] if len(row) > 3 else {},
            )
            for row in rows
        ]


_instances: dict[str, VectorStoreUtil] = {}
_lock = threading.Lock()


def get_vector_store(namespace, dim) -> VectorStoreUtil:
    """
    按 namespace 获取单例，线程安全。
    同一 namespace 只初始化一次（含建表）。
    dim 与已有实例不一致时抛出 ValueError，防止静默写入错误维度数据。
    """
    if namespace in _instances:
        existing = _instances[namespace]
        if existing.dim != dim:
            raise ValueError(
                f"namespace '{namespace}' 已以 dim={existing.dim} 初始化，"
                f"与请求的 dim={dim} 不一致，请检查 embedding 模型配置"
            )
        return existing

    with _lock:
        if namespace not in _instances:
            _instances[namespace] = VectorStoreUtil(namespace, dim)
        return _instances[namespace]
