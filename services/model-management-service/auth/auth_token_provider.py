import os
from typing import Any, Dict
from uuid import UUID

import jwt
from dotenv import load_dotenv
from fastapi import Request , status, HTTPException
from sqlalchemy.orm import Session

from logger import logger


load_dotenv()

        

async def fetch_session(credentials: str, db: Session):
    # This cannot fail, since this was already checked during auth verification
    
    try:
        claims = jwt.decode(
            credentials, key=os.environ["JWT_SECRET_KEY"], algorithms=["HS256"]
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired"
        )

    from repositories.user_sessions_repository import UserSessionRepository
    from repositories.user_repository import UserRepository

    session_repo = UserSessionRepository(db)
    user_repo = UserRepository(db)

    # Session has to exist since it was already checked during auth verification
    session = await session_repo.find_by_user_id(int(claims["sub"]))

    #Pick the latest session
    session = session[0]

    if not session:
        return None

    user = await user_repo.find_by_id(session.user_id)

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
