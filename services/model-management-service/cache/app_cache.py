import redis
import os
from dotenv import load_dotenv
from logger import logger

load_dotenv()

def get_cache_connection() -> redis.Redis:
    try:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6381))
        redis_db   = int(os.getenv("REDIS_DB", 0))
        redis_password = os.getenv("REDIS_PASSWORD", None)

        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
        )

        # test connection
        r.ping()
        logger.info(f"Connected to Redis at {redis_host}:{redis_port}, DB={redis_db}")
        return r
    except Exception as e:
        logger.exception("Failed to connect to Redis.")
        raise e
