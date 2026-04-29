import logging
from agent.config.llm_factory import get_embedding
from agent.knowledge.chunking import Chunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 10


def embed_chunks(
    chunks,
):
    """
    批量将文本块转为向量，自动分批避免超过 API 单次限制。
    同时过滤空块，保证 chunks 与 vectors 严格对齐。

    Args:
        chunks: list[str] 或 list[Chunk]

    Returns:
        (valid_chunks, vectors)
        valid_chunks: 过滤空块后的有效块列表（类型与输入一致）
        vectors:      与 valid_chunks 一一对应的向量列表
    """
    if not chunks:
        return [], []

    embedding = get_embedding()

    # 统一提取文本，同时记录有效块
    valid_chunks = []
    texts = []
    for chunk in chunks:
        if isinstance(chunk, Chunk):
            text = chunk.text
        else:
            text = chunk

        if text.strip():
            valid_chunks.append(chunk)
            texts.append(text)

    if not texts:
        return [], []

    vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i + BATCH_SIZE]
        try:
            batch_vectors = embedding.embed_documents(batch)
            vectors.extend(batch_vectors)
        except Exception as e:
            logger.error(f"第 {i // BATCH_SIZE + 1} 批 embedding 失败: {e}")
            raise

    return valid_chunks, vectors


def embed_query(text):
    """单条查询文本转向量，用于检索时的 query embedding。"""
    if not text.strip():
        raise ValueError("查询文本不能为空")
    return get_embedding().embed_query(text)
