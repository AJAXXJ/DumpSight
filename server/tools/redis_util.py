import redis
from tools.logger import logger
from redis.exceptions import RedisError, ConnectionError
from main import app
import threading

class RedisUtil:
    """
    Redis utility class.
    """

    def __init__(self):
        """
        Initialize the Redis client.
        """
        try:
            self.redis_client = redis.Redis(
                host=app.config['REDIS_HOST'],
                port=int(app.config['REDIS_PORT']),
                password=app.config['REDIS_DB'],
                db=int(app.config['REDIS_PASSWORD']),
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
        """
        Set a single key.
        """
        if not self.redis_client:
            logger.warning("Redis client not available. set operation skipped.")
            return False
        try:
            return self.redis_client.set(name=key, value=value, ex=expire)
        except RedisError as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False

    def get(self, key):
        """
        Get a single key.
        """
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
        """
        Delete a single key.
        """
        if not self.redis_client:
            logger.warning("Redis client not available. delete operation skipped.")
            return False
        try:
            return self.redis_client.delete(key)
        except RedisError as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            return False
        
    def delete_many(self, keys):
        """
        Delete multiple keys in one batch.
        """
        if not self.redis_client or not keys:
            return False
        try:
            return self.redis_client.delete(*keys)
        except RedisError as e:
            logger.error(f"Redis delete_many error: {e}")
            return False

    def exists(self, key):
        """
        Check if a key exists.
        """
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
        """
        if not self.redis_client:
            return {}
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
            if not keys:
                return {}
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            values = pipe.execute()
            return dict(zip(keys, values))
        except RedisError as e:
            logger.error(f"Redis scan_with_values error for pattern {pattern}: {e}")
            return {}
        
redis_util = RedisUtil()

_redis_util = None
_redis_lock = threading.Lock()

def get_redis_util() -> RedisUtil:
    global _redis_util
    if _redis_util is None:
        with _redis_lock:
            if _redis_util is None:
                _redis_util = RedisUtil()
    return _redis_util