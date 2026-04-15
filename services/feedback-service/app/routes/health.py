"""Health check endpoint."""

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(request: Request):
    db_session_factory = getattr(request.app.state, "db_session_factory", None)
    if db_session_factory:
        async with db_session_factory() as db:
            await db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "feedback-service"}
