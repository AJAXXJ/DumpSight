import logging
import threading
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)


class EsUtil:
    def __init__(self, config):
        """
        config 结构示例:
        config["ELASTICSEARCH"] = {
            "HOSTS": ["http://192.168.122.1:9200"],
            "USER": "elastic",
            "PASSWORD": "xxx"
        }
        """
        cfg = config["ELASTICSEARCH"]
        self.hosts = cfg.get("HOSTS", ["http://192.168.122.1:9200"])
        self.user = cfg.get("USER")
        self.password = cfg.get("PASSWORD")

        # 初始化客户端
        if self.user and self.password:
            self.client = Elasticsearch(
                self.hosts,
                basic_auth=(self.user, self.password) if self.user else None,
                verify_certs=False,  # 开发环境通常跳过 SSL 验证
            )
        else:
            self.client = Elasticsearch(self.hosts)

        # 验证连接
        if not self.client.ping():
            logger.error("无法连接到 Elasticsearch 服务")

    def ensure_index(self, index_name, mappings=None):
        """
        直接尝试创建并捕获已存在异常
        """
        index_body = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": mappings or {},
        }
        try:
            self.client.indices.create(index=index_name, body=index_body)
            logger.info(f"成功创建 Elasticsearch 索引: {index_name}")
        except Exception as e:
            if "resource_already_exists_exception" in str(e) or "already exists" in str(
                e
            ):
                logger.info(f"索引 {index_name} 已存在，无需创建")
            else:
                logger.error(f"创建索引时发生意外错误: {e}")

    def index_doc(self, index_name, doc_id, document):
        """单条写入"""
        try:
            self.client.index(
                index=index_name, id=doc_id, document=document, refresh=True
            )
            return True
        except Exception as e:
            logger.error(f"写入 ES 失败 [ID: {doc_id}]: {e}")
            return False

    def batch_index_docs(self, index_name, records: list[dict], id_field="case_id"):
        """
        批量写入文档
        records: 包含数据的字典列表
        id_field: 指定哪个字段作为 ES 的 _id
        """
        if not records:
            return

        actions = [
            {"_index": index_name, "_id": r.get(id_field), "_source": r}
            for r in records
        ]

        try:
            success, _ = helpers.bulk(self.client, actions, refresh=True)
            logger.info(f"批量写入 ES 成功: {success} 条数据")
            return success
        except Exception as e:
            logger.error(f"ES 批量写入异常: {str(e)}")
            raise e

    def search(self, index_name, search_query):
        """原生搜索"""
        try:
            return self.client.search(index=index_name, body=search_query)
        except Exception as e:
            logger.error(f"ES 搜索异常: {e}")
            return {"hits": {"hits": []}}

    def update_doc(self, index_name, doc_id, document):
        """局部更新文档"""
        try:
            self.client.update(index=index_name, id=doc_id, doc=document, refresh=True)
            return True
        except Exception as e:
            logger.error(f"更新 ES 失败 [ID: {doc_id}]: {e}")
            return False


_es_util: EsUtil | None = None
_es_lock = threading.Lock()


def init_es_util(config):
    global _es_util
    if _es_util is None:
        with _es_lock:
            if _es_util is None:
                _es_util = EsUtil(config)


def get_es_client() -> EsUtil:
    if _es_util is None:
        raise RuntimeError("EsUtil 未初始化，请先调用 init_es_util(config)")
    return _es_util
