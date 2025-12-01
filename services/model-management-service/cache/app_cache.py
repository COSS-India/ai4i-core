import os
import redis  # Synchronous Redis client for redis_om
from dotenv import load_dotenv

from logger import logger

load_dotenv()


def get_cache_connection() -> redis.Redis | None:
    """
    Create a synchronous Redis client for redis_om.
    redis_om requires a synchronous Redis client, not async.
    This is used specifically for caching models and services.
    """
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD")

    try:
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_timeout=10,
            socket_connect_timeout=10,
            health_check_interval=30,
        )
        
        # Test the connection
        client.ping()
        logger.info(f"Configured synchronous Redis client for redis_om at {redis_host}:{redis_port}, DB={redis_db}")
        return client
    except Exception as e:
        logger.exception(f"Failed to configure synchronous Redis client: {e}")
        return None


def get_async_cache_connection():
    """
    Create an async Redis client for auth and rate limiting.
    This is separate from the sync client used by redis_om.
    """
    import redis.asyncio as redis_async
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD")

    try:
        client = redis_async.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_timeout=10,
            socket_connect_timeout=10,
            health_check_interval=30,
        )
        logger.info(f"Configured async Redis client for auth/rate limiting at {redis_host}:{redis_port}, DB={redis_db}")
        return client
    except Exception as e:
        logger.exception(f"Failed to configure async Redis client: {e}")
        return None
