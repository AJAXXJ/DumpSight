import redis
from tools.logger import logger
from redis.exceptions import RedisError, ConnectionError
from config import config
import threading

class RedisUtil:

    def __init__(self):
        try:
            # Check if Redis configuration is available
            redis_host = getattr(config, 'redis_host', None)
            redis_port = getattr(config, 'redis_port', None)
            redis_db = getattr(config, 'redis_db', None)
            redis_password = getattr(config, 'redis_password', None)

            if not redis_host:
                logger.warning("Redis configuration not found. Please run 'dumpsight setup' first.")
                self.redis_client = None
                return

            self.redis_client = redis.Redis(
                host=redis_host,
                port=int(redis_port),
                password=redis_password,
                db=int(redis_db),
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

_redis_util = None
_lock = threading.Lock()

def get_redis_util() -> RedisUtil:
    global _redis_util
    if _redis_util is None:
        with _lock:
            if _redis_util is None:
                _redis_util = RedisUtil()
    return _redis_util