import yaml
from functools import lru_cache
from pathlib import Path
import warnings


class Settings:
    def __init__(self, config_path = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        # LLM
        llm = cfg.get("llm", {})
        self.llm_fast_model = llm.get("fast_model", "")
        self.llm_strong_model = llm.get("strong_model", "")
        self.llm_temperature = llm.get("temperature", 0.0)
        self.llm_max_tokens = llm.get("max_tokens", 4096)
        self.llm_timeout = llm.get("timeout", 60)
        self.llm_max_retries = llm.get("max_retries", 3)

        # 温度校验
        if self.llm_temperature > 0:
            warnings.warn(
                f"llm_temperature={self.llm_temperature} > 0，建议设为 0",
                UserWarning,
            )

        # API Keys
        api = cfg.get("api_keys", {})
        self.openai_api_key = api.get("openai_api_key", "")
        self.openai_api_base = api.get("openai_api_base", "")

        # Vector Store
        vs = cfg.get("vector_store", {})
        self.vector_store_type = vs.get("type", "chroma")

        chroma = vs.get("chroma", {})
        self.chroma_host = chroma.get("host", "localhost")
        self.chroma_port = chroma.get("port", 8000)
        self.chroma_collection = chroma.get("collection", "dpdk_cases")

        qdrant = vs.get("qdrant", {})
        self.qdrant_host = qdrant.get("host", "localhost")
        self.qdrant_port = qdrant.get("port", 6333)
        self.qdrant_collection = qdrant.get("collection", "dpdk_cases")

        # Embedding
        emb = cfg.get("embedding", {})
        self.embedding_model = emb.get("model", "text-embedding-3-small")
        self.embedding_dim = emb.get("dim", 1536)

        # Metadata DB
        self.metadata_db_url = cfg.get("metadata_db", {}).get(
            "url", "sqlite:///./case_library.db"
        )

        # Retriever
        ret = cfg.get("retriever", {})
        self.retriever_top_k = ret.get("top_k", 5)
        self.retriever_score_threshold = ret.get("score_threshold", 0.7)

        # Monitor
        mon = cfg.get("monitor", {})
        self.monitor_interval_1s = mon.get("interval_1s", 1.0)
        self.monitor_interval_5s = mon.get("interval_5s", 5.0)
        self.alert_webhook_url = mon.get("webhook_url", "")
        self.alert_cooldown_sec = mon.get("cooldown_sec", 60)

        # Prompt
        prompt = cfg.get("prompt", {})
        self.prompt_version = prompt.get("version")
        self.few_shots_enabled = prompt.get("few_shots_enabled", True)
        self.few_shots_max = prompt.get("few_shots_max", 3)

        # LangGraph
        lg = cfg.get("langgraph", {})
        self.checkpointer_type = lg.get("checkpointer_type", "memory")
        self.checkpointer_db_url = lg.get(
            "checkpointer_db_url", "./langgraph_checkpoints.db"
        )

        # Log
        log = cfg.get("log", {})
        self.log_level = log.get("level", "INFO")
        self.log_json = log.get("json", False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()