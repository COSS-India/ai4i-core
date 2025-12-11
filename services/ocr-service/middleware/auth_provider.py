"""
Authentication provider for OCR service.

Matches ASR/NMT auth behavior: validates API keys against Postgres with a
Redis cache, populates `request.state` with auth context, and supports
ENV-based toggles for local/anonymous access.
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError
from models.auth_models import ApiKeyDB, UserDB
from repositories.api_key_repository import ApiKeyRepository
from repositories.ocr_repository import get_db_session

logger = logging.getLogger(__name__)


def get_api_key_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from Authorization header."""
    if not authorization:
        return None

    if authorization.startswith("Bearer "):
        return authorization[7:]
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    return authorization


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def validate_api_key(api_key: str, db: AsyncSession, redis_client) -> Tuple[ApiKeyDB, UserDB]:
    """Validate API key and return user and API key data."""
    try:
        key_hash = hash_api_key(api_key)

        cache_key = f"api_key:{key_hash}"
        cached_data = await redis_client.get(cache_key) if redis_client else None

        if cached_data:
            try:
                cache_data = json.loads(cached_data)
                api_key_id = cache_data.get("api_key_id")
                if cache_data.get("is_active"):
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
        if redis_client:
            await redis_client.setex(cache_key, 300, json.dumps(cache_data))

        await api_key_repo.update_last_used(api_key_db.id)

        return api_key_db, api_key_db.user

    except (InvalidAPIKeyError, ExpiredAPIKeyError):
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error validating API key: %s", exc)
        raise AuthenticationError("Failed to validate API key")


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    require_api_key = os.getenv("REQUIRE_API_KEY", "true").lower() == "true"
    allow_anonymous = os.getenv("ALLOW_ANONYMOUS_ACCESS", "false").lower() == "true"

    logger.info(
        "Auth config - AUTH_ENABLED=%s REQUIRE_API_KEY=%s ALLOW_ANONYMOUS_ACCESS=%s",
        auth_enabled,
        require_api_key,
        allow_anonymous,
    )

    if not auth_enabled or (allow_anonymous and not require_api_key):
        request.state.user_id = None
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = None
        request.state.is_authenticated = False

        return {"user_id": None, "api_key_id": None, "user": None, "api_key": None}

    try:
        api_key = get_api_key_from_header(authorization)
        if not api_key:
            raise AuthenticationError("Missing API key")

        redis_client = getattr(request.app.state, "redis_client", None)

        api_key_db, user_db = await validate_api_key(api_key, db, redis_client)

        request.state.user_id = user_db.id
        request.state.api_key_id = api_key_db.id
        request.state.api_key_name = api_key_db.name
        request.state.user_email = user_db.email
        request.state.is_authenticated = True

        return {
            "user_id": user_db.id,
            "api_key_id": api_key_db.id,
            "user": user_db,
            "api_key": api_key_db,
        }

    except (AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError):
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Authentication error: %s", exc)
        raise AuthenticationError("Authentication failed")


async def OptionalAuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session),
) -> Optional[Dict[str, Any]]:
    """Optional authentication provider that doesn't raise if auth is absent."""
    try:
        return await AuthProvider(request, authorization, x_auth_source, db)
    except AuthenticationError:
        return None

