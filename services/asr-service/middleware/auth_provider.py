"""Thin auth wrapper — delegates to the shared ai4icore_auth library.

Re-exports ``validate_api_key`` and ``hash_api_key`` for
``services/streaming_service.py`` which imports them from here.
"""

import hashlib
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.providers import create_auth_providers
from ai4icore_env import app_env
from ai4icore_constants.exceptions import (
    AuthenticationError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
)

logger = logging.getLogger(__name__)

AuthProvider, OptionalAuthProvider = create_auth_providers()


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Legacy local-DB API key validation (used by streaming_service.py)
# ---------------------------------------------------------------------------

async def validate_api_key(api_key: str, db: AsyncSession, redis_client):
    """Validate API key locally via DB + Redis cache.

    Returns ``(api_key_db, user_db)`` tuple -- kept for backward-compat
    with ``streaming_service.py``.
    """
    from repositories.api_key_repository import ApiKeyRepository

    try:
        key_hash = hash_api_key(api_key)
        cache_key = f"api_key:{key_hash}"
        cached_data = await redis_client.get(cache_key)

        if cached_data:
            try:
                cache_data = json.loads(cached_data)
                api_key_id = cache_data.get("api_key_id")
                is_active = cache_data.get("is_active", False)
                if is_active:
                    api_key_repo = ApiKeyRepository(db)
                    api_key_db = await api_key_repo.find_by_id(api_key_id)
                    if api_key_db and await api_key_repo.is_key_valid(api_key_db):
                        await api_key_repo.update_last_used(api_key_id)
                        return api_key_db, api_key_db.user
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Invalid cache data for API key: %s", exc)

        api_key_repo = ApiKeyRepository(db)
        api_key_db = await api_key_repo.find_by_key_hash(key_hash)
        if not api_key_db:
            raise InvalidAPIKeyError("API key not found")

        if not await api_key_repo.is_key_valid(api_key_db):
            if not api_key_db.is_active:
                raise InvalidAPIKeyError("API key is inactive")
            raise ExpiredAPIKeyError("API key has expired")

        cache_data = {
            "api_key_id": api_key_db.id,
            "user_id": api_key_db.user_id,
            "is_active": api_key_db.is_active,
        }
        await redis_client.setex(cache_key, app_env.api_key_cache_ttl, json.dumps(cache_data))
        await api_key_repo.update_last_used(api_key_db.id)
        return api_key_db, api_key_db.user

    except (InvalidAPIKeyError, ExpiredAPIKeyError):
        raise
    except Exception as exc:
        logger.error("Error validating API key: %s", exc)
        raise AuthenticationError("Failed to validate API key")
