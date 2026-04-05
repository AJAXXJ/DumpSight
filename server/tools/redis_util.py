import redis
from main import app

class RedisUtil:

    def __init__(self):
        self.redis_client = redis.Redis(
            host="localhost", port=6379, db=0, decode_responses=True
        )
