import time
from typing import Any, Dict

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from redis_om.model.model import NotFoundError

from cache.api_key import ApiKeyCache
from repositories.api_key_repository import ApiKeyRepository


def populate_api_key_cache(credentials, db):
    api_key_repo = ApiKeyRepository(db)
    api_key = api_key_repo.find_one(api_key=credentials)
    if api_key:
        api_key_cache = ApiKeyCache(
            id=str(api_key.id),
            api_key=api_key.api_key,
            user_id=str(api_key.user_id),
            active=api_key.active
        )
        api_key_cache.save()
    return api_key_cache


def validate_credentials(credentials: str, request: Request, db: Session) -> bool:
    try:
        api_key = ApiKeyCache.get(credentials)
    except NotFoundError:
        try:
            api_key = populate_api_key_cache(credentials, db)
        except Exception:
            return False

    if not bool(api_key.active):
        return False

    request.state.api_key_name = api_key.name
    request.state.user_id = api_key.user_id
    request.state.api_key_id = api_key.id
    request.state.api_key_data_tracking = bool(api_key.data_tracking)
    request.state.api_key_type = api_key.type

    return True


async def fetch_session(credentials: str, db: Session):
    from repositories.user_repository import UserRepository

    api_key_repo = ApiKeyRepository(db)
    user_repo = UserRepository(db)

    # Api key has to exist since it was already checked during auth verification
    api_key = await api_key_repo.find_one(api_key=credentials)

    if not api_key:
        return None

    user_id = api_key.user_id
    user = await user_repo.find_by_id(user_id)

    if not user:
        return None

    # Convert to dict and remove password
    user_dict = {
        "id": str(user.id),
        "email": user.email,
        "name": user.username,
        # "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None
    }

    return user_dict
