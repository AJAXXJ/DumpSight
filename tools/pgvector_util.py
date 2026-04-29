import json
import threading
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_values


class PgVectorUtil:
    def __init__(self, config):
        cfg = config["PYVECTOR"]

        self.host = cfg["HOST"]
        self.port = cfg["PORT"]
        self.dbname = cfg["DBNAME"]
        self.user = cfg["USER"]
        self.password = cfg["PASSWORD"]

        self.pool = SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
        )

        self._init_extension()

    def _init_extension(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def get_conn(self):
        return self.pool.getconn()

    def put_conn(self, conn):
        self.pool.putconn(conn)

    def execute(self, sql, params=None, fetch=False):
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                result = None
                if fetch:
                    result = cur.fetchall()
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.put_conn(conn)

    def create_table(self, table: str, dim: int):
        """
        建表，新增 metadata JSONB 列用于存储分块元数据。
        """
        # 建表和建索引分开执行，避免部分数据库不支持多语句
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id        TEXT PRIMARY KEY,
                        content   TEXT,
                        embedding vector({dim}),
                        metadata  JSONB DEFAULT '{{}}'::jsonb
                    );
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS {table}_embedding_idx
                        ON {table} USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 100);
                """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.put_conn(conn)

    def insert_vector(self, table: str, data: dict):
        """
        单条写入，保留兼容性。
        data 示例：
        {
            "id": "xxx",
            "content": "...",
            "embedding": [0.1, 0.2, ...],
            "metadata": {}          # 可选
        }
        """
        sql = f"""
        INSERT INTO {table} (id, content, embedding, metadata)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
            SET content   = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata  = EXCLUDED.metadata;
        """
        self.execute(sql, (
            data["id"],
            data["content"],
            data["embedding"],
            json.dumps(data.get("metadata", {})),
        ))

    def batch_insert_vectors(self, table: str, records: list[dict]):
        """
        批量写入，使用 execute_values 减少 DB 往返。
        records 每项格式同 insert_vector 的 data。
        """
        if not records:
            return

        sql = f"""
        INSERT INTO {table} (id, content, embedding, metadata)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
            SET content   = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata  = EXCLUDED.metadata;
        """
        values = [
            (
                r["id"],
                r["content"],
                r["embedding"],
                json.dumps(r.get("metadata", {})),
            )
            for r in records
        ]

        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                execute_values(cur, sql, values)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.put_conn(conn)

    def search_similar(self, table: str, query_vector: list, top_k: int = 5):
        """
        相似度检索，返回 [(id, content, score, metadata), ...]
        使用余弦距离（<=>），score 越小越相似。
        """
        sql = f"""
        SELECT id, content,
               1 - (embedding <=> %s::vector) AS score,
               metadata
        FROM {table}
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """
        return self.execute(
            sql,
            (query_vector, query_vector, top_k),
            fetch=True,
        )

    def delete_by_etag(self, table: str, etag: str):
        """删除某个文件的全部 chunk。"""
        sql = f"DELETE FROM {table} WHERE id LIKE %s"
        self.execute(sql, (f"{etag}_%",))

_pgvector_util: PgVectorUtil | None = None
_pgvector_lock = threading.Lock()


def init_pgvector_util(config):
    global _pgvector_util

    if _pgvector_util is None:
        with _pgvector_lock:
            if _pgvector_util is None:
                _pgvector_util = PgVectorUtil(config)


def get_pgvector_util() -> PgVectorUtil:
    if _pgvector_util is None:
        raise RuntimeError(
            "PgVectorUtil not initialized. Call init_pgvector_util first."
        )
    return _pgvector_util
