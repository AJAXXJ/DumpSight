import os
import json
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from agent.case_library.fetcher import render_embedding_input_template
from server.repository.case_repository import add_case, get_case
from tools.logger import logger


class FaissStore:
    """
    FAISS 向量数据库存储
    """

    def __init__(self, embeddings, index_path, json_path, template_path):
        self.embeddings = embeddings
        self.index_path = index_path
        self.json_path = json_path
        self.template_path = template_path
        self._db = self._load_or_build()

    def _load_or_build(self):
        """
        加载本地索引若加载失败则触发构建
        """
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
        """
        从 JSON 构建 FAISS
        """
        if not self.json_path.exists():
            logger.error("知识库 JSON 不存在")
            return None
        try:
            # 加载 case 转为 document
            cases = json.loads(self.json_path.read_text(encoding="utf-8"))
            docs = [
                Document(
                    page_content=render_embedding_input_template(
                        template=self.template_path,
                        description=case["description"],
                    ),
                    metadata={
                        "case_id": case["case_id"],
                        "signal_name": case.get("signal_name"),
                        "crash_type": case.get("crash_type"),
                        "anomaly_flags": case.get("anomaly_flags", []),
                    },
                )
                for case in cases
            ]
            db = FAISS.from_documents(docs, self.embeddings, normalize_L2=True)
            db.save_local(self.index_path)

            # mysql
            for case in cases:
                if get_case(case["case_id"]) is None:
                    add_case(
                        case_id=case["case_id"],
                        signal_name=case["signal_name"],
                        crash_type=case["crash_type"],
                        crash_function=case["crash_function"],
                        main_path=case["main_path"],
                        missing_libs=case["missing_libs"],
                        dpdk_subsystems=case["dpdk_subsystems"],
                        root_cause=case["root_cause"],
                        repair_steps=case["repair_steps"],
                        description=case["description"],
                    )

            logger.info("FAISS 索引构建完成")
            return db
        except Exception as e:
            logger.error(f"构建失败: {e}")
            return None

    @property
    def available(self):
        return self._db is not None

    def add_case_to_faiss(self, case):
        """
        将 case 写入 FAISS
        """
        if not self.available:
            logger.error("FAISS 不可用")
            return False

        try:
            # 构造 Document
            doc = Document(
                page_content=render_embedding_input_template(
                    template=self.template_path,
                    description=case["description"],
                ),
                metadata={
                    "case_id": case["case_id"],
                    "signal_name": case.get("signal_name"),
                    "crash_type": case.get("crash_type"),
                    "anomaly_flags": case.get("anomaly_flags", []),
                },
            )

            # 写入 FAIS
            self._db.add_documents([doc])

            # 持久化
            self._db.save_local(self.index_path)

            logger.info(f"已写入 FAISS: {case['case_id']}")
            return True

        except Exception as e:
            logger.error(f"写入 FAISS 失败: {e}")
            return False

    def add_cases_to_faiss(self, cases):
        """
        批量写入 FAISS
        """
        if not self.available:
            logger.error("FAISS 不可用")
            return 0

        try:
            docs = []

            for case in cases:
                doc = Document(
                    page_content=render_embedding_input_template(
                        template=self.template_path,
                        description=case["description"],
                    ),
                    metadata={
                        "case_id": case["case_id"],
                        "signal_name": case.get("signal_name"),
                        "crash_type": case.get("crash_type"),
                        "anomaly_flags": case.get("anomaly_flags", []),
                    },
                )
                docs.append(doc)

            if not docs:
                return 0

            self._db.add_documents(docs)
            self._db.save_local(self.index_path)

            logger.info(f"批量写入 FAISS: {len(docs)} 条")
            return len(docs)

        except Exception as e:
            logger.error(f"批量写入失败: {e}")
            return 0

    def search(self, query, k=5, score_threshold=0.8):
        """
        FAISS 检索 + score过滤
        """
        if not self.available:
            return []

        docs_and_scores = self._db.similarity_search_with_score(query, k=k)

        results = []

        for doc, score in docs_and_scores:
            # normalize_L2=True 情况下
            sim = 1 - score / 2

            if sim >= score_threshold:
                results.append(
                    {
                        "case_id": doc.metadata["case_id"],
                        "score": sim,
                        "content": doc.page_content,
                    }
                )

        return results
