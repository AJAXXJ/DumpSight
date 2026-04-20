import redis
import threading
from typing import Optional
from tools.logger import logger
from dataclasses import dataclass
from redis.exceptions import RedisError, ConnectionError

@dataclass
class RedisConfig:
    host: str
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    retry_on_timeout: bool = True
    decode_responses: bool = True

    @classmethod
    def from_config(cls, config) -> Optional["RedisConfig"]:
        """从 dumpsight config 中读取"""
        host = getattr(config, "redis_host", None)
        if not host:
            return None
        return cls(
            host=host,
            port=int(getattr(config, "redis_port", 6379)),
            db=int(getattr(config, "redis_db", 0)),
            password=getattr(config, "redis_password", None),
        )

    @classmethod
    def from_app_config(cls, app_config) -> Optional["RedisConfig"]:
        """从 Flask/FastAPI 等 app.config 中读取"""
        host = app_config.get("REDIS_HOST")
        if not host:
            return None
        return cls(
            host=host,
            port=int(app_config.get("REDIS_PORT", 6379)),
            db=int(app_config.get("REDIS_DB", 0)),
            password=app_config.get("REDIS_PASSWORD"),
        )
    

class RedisUtil:
    """
    Redis utility class.
    """

    def __init__(self, redis_config: RedisConfig):
        try:
            self.redis_client = redis.Redis(
                host=redis_config.host,
                port=redis_config.port,
                password=redis_config.password,
                db=redis_config.db,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )

            self.redis_client.ping()
            logger.info("Redis connection established successfully.")

        except (RedisError, ConnectionError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    def set(self, key, value, expire=None):
        if not self.redis_client:
            logger.warning("Redis client not available. set operation skipped.")
            return False
        try:
            return self.redis_client.set(name=key, value=value, ex=expire)
        except RedisError as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False

    def get(self, key):
        if not self.redis_client:
            logger.warning("Redis client not available. get operation skipped.")
            return None
        try:
            return self.redis_client.get(key)
        except RedisError as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None

    def get_many(self, keys):
        """
        Get multiple keys in one batch via pipeline.
        """
        if not self.redis_client or not keys:
            return {}
        try:
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            values = pipe.execute()
            return {key: value for key, value in zip(keys, values) if value is not None}
        except RedisError as e:
            logger.error(f"Redis get_many error: {e}")
            return {}
        
    def delete(self, key):
        if not self.redis_client:
            logger.warning("Redis client not available. delete operation skipped.")
            return False
        try:
            return self.redis_client.delete(key)
        except RedisError as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            return False

    def delete_many(self, keys):
        """Delete multiple keys in one batch."""
        if not self.redis_client or not keys:
            return False
        try:
            return self.redis_client.delete(*keys)
        except RedisError as e:
            logger.error(f"Redis delete_many error: {e}")
            return False
    
    def exists(self, key):
        if not self.redis_client:
            logger.warning("Redis client not available. exists operation skipped.")
            return False
        try:
            return self.redis_client.exists(key) > 0
        except RedisError as e:
            logger.error(f"Redis exists error for key {key}: {e}")
            return False
        
    def scan(self, pattern):
        """
        Scan keys matching a pattern, returns a list of keys.
        """
        if not self.redis_client:
            logger.warning("Redis client not available. scan operation skipped.")
            return []
        try:
            keys = []
            cursor = 0
            while True:
                cursor, partial = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                keys.extend(partial)
                if cursor == 0:
                    break
            return keys
        except RedisError as e:
            logger.error(f"Redis scan error for pattern {pattern}: {e}")
            return []

    def scan_with_values(self, pattern):
        """
        Scan keys matching a pattern and return key-value pairs in one batch.
        Keys that have expired or been deleted between scan and pipeline fetch are excluded.
        """
        if not self.redis_client:
            return {}
        try:
            keys = self.scan(pattern)
            if not keys:
                return {}
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            values = pipe.execute()
            return {key: value for key, value in zip(keys, values) if value is not None}
        except RedisError as e:
            logger.error(f"Redis scan_with_values error for pattern {pattern}: {e}")
            return {}

_instances: dict[str, RedisUtil] = {}
_lock = threading.Lock()

_default_redis_util: Optional[RedisUtil] = None
_default_lock = threading.Lock()

def get_redis_util(redis_config: Optional[RedisConfig] = None) -> RedisUtil:
    key = f"{redis_config.host}:{redis_config.port}:{redis_config.db}"
    
    if key not in _instances:
        with _lock:
            if key not in _instances:
                _instances[key] = RedisUtil(redis_config)
    
    return _instances[key]


def get_redis_util_no_config() -> RedisUtil:
    """
    获取默认 Redis 实例，需要先调用 init_redis_util
    """
    if _default_redis_util is None:
        raise RuntimeError("Redis util not initialized, call init_redis_util first")
    return _default_redis_util


def init_redis_util(config) -> RedisUtil:
    """
    初始化默认 Redis 实例，模仿 MySQL 的 init 形式
    传入 app config，内部构建 RedisConfig
    """
    global _default_redis_util
    with _default_lock:
        if _default_redis_util is None:
            redis_config = RedisConfig.from_app_config(config)
            if redis_config is None:
                raise ValueError("Redis config is invalid or missing REDIS_HOST")
            _default_redis_util = RedisUtil(redis_config)
    return _default_redis_util