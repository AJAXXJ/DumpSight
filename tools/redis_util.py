import redis
from tools.logger import logger
from redis.exceptions import RedisError, ConnectionError
from dumpsight import config

class RedisUtil:

    def __init__(self, config):
        try:
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=int(config.redis_port),
                password=config.redis_password,
                db=int(config.redis_db),
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

    def exists(self, key):
        if not self.redis_client:
            logger.warning("Redis client not available. exists operation skipped.")
            return False
        try:
            return self.redis_client.exists(key) > 0
        except RedisError as e:
            logger.error(f"Redis exists error for key {key}: {e}")
            return False

redis_util = RedisUtil(config)