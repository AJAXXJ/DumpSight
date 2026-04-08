from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from config.settings import get_settings

logger = logging.getLogger(__name__)


LLMMode = Literal["fast", "strong"]


@lru_cache(maxsize=2)
def get_llm(mode: LLMMode = "fast") -> BaseChatModel:
    """
    获取 LLM：
        fast   → 低成本 / 高吞吐（Agent / 工具调用）
        strong → 高质量（总结 / 根因分析）

    使用 OpenAI-compatible API（支持任意第三方网关）
    """
    settings = get_settings()

    if mode == "fast":
        model = settings.llm_fast_model
    elif mode == "strong":
        model = settings.llm_strong_model
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    logger.info(
        "initializing LLM | mode=%s base=%s model=%s",
        mode,
        settings.openai_api_base,
        model,
    )

    return ChatOpenAI(
        model        = model,
        temperature  = settings.llm_temperature,
        max_tokens   = settings.llm_max_tokens,
        timeout      = settings.llm_timeout,
        max_retries  = settings.llm_max_retries,

        # 第三方网关关键参数
        api_key      = settings.openai_api_key or "EMPTY",
        base_url     = settings.openai_api_base,
    )


@lru_cache(maxsize=1)
def get_embedding() -> Embeddings:
    """
    使用同一 OpenAI-compatible embedding
    """
    settings = get_settings()

    logger.info(
        "initializing Embedding | base=%s model=%s",
        settings.openai_api_base,
        settings.embedding_model,
    )


    return OpenAIEmbeddings(
        model    = settings.embedding_model,
        api_key  = settings.openai_api_key or "EMPTY",
        base_url = settings.openai_api_base,
    )


def get_checkpointer():
    """
    根据 settings.checkpointer_type 返回 LangGraph Checkpointer。
      memory  → MemorySaver（进程内，重启丢失）
      sqlite  → SqliteSaver（单机持久化）
    """
    settings = get_settings()

    if settings.checkpointer_type == "memory":
        return MemorySaver()

    if settings.checkpointer_type == "sqlite":
        return SqliteSaver.from_conn_string(settings.checkpointer_db_url)

    raise ValueError(f"Unsupported checkpointer_type: '{settings.checkpointer_type}'")