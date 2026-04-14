import os
import json
from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from agent.case_library.fetcher import render_embedding_input_template
from agent.config.settings import get_settings
from tools.logger import logger


class FaissKnowledge:

    def __init__(self):
        self.case_template_path = (
            Path(__file__).parent / "template" / "case_template.j2"
        )
        self.json_path = Path(__file__).parent / "data" / "dpdk_cases.json"
        self.index_path = Path(__file__).parent / "data" / "faiss_index"

        config = get_settings()
        self.embeddings = OpenAIEmbeddings(
            model=config["embedding_model"],
            openai_api_key=config["openai_api_key"],
            openai_api_base=config["openai_api_base"],
        )

        self.vector_db = self._load_or_build()

    def _load_or_build(self):
        if os.path.exists(self.index_path):
            try:
                db = FAISS.load_local(
                    self.index_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                logger.info("FAISS 索引加载成功")
                return db
            except Exception as e:
                logger.warning(f"索引损坏，重建中: {e}")

        return self._build()

    def _build(self):
        if not os.path.exists(self.json_path):
            logger.error("知识库 JSON 不存在")
            return None

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                cases = json.load(f)

            docs = []

            for case in cases:
                metadata = {"case_id": case["case_id"]}
                
                page_content = render_embedding_input_template(
                    template=self.case_template_path,
                    signal_name=case["signal_name"],
                    crash_type=case["crash_type"],
                    crash_function=case["crash_function"],
                    main_path=case["main_path"],
                    missing_libs=case["missing_libs"],
                    dpdk_subsystems=case["dpdk_subsystems"],
                )

                docs.append(Document(page_content=page_content, metadata=metadata))

            db = FAISS.from_documents(docs, self.embeddings)
            db.save_local(self.index_path)
            logger.info("FAISS 索引构建完成")
            return db

        except Exception as e:
            logger.error(f"构建失败: {e}")
            return None

    def query(self, text, k=3, threshold=0.3):
        if not self.vector_db:
            return "知识库不可用"

        try:
            results = self.vector_db.similarity_search_with_relevance_scores(text, k=k)
            hits = [
                f"[匹配度: {s:.2f}]\n{d.page_content}"
                for d, s in results
                if s >= threshold
            ]

            return "\n\n===\n\n".join(hits) if hits else "未找到高匹配案例"

        except Exception as e:
            logger.error(f"查询失败: {e}")
            return "查询异常"


_instance = None


def get_faiss_knowledge():
    global _instance
    if _instance is None:
        _instance = FaissKnowledge()
    return _instance
