"""LLM history endpoints — read-only lookup of stored request/result data."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_tenant_db_session
from app.repositories.llm_repository import LLMRepository

router = APIRouter(
    prefix="/api/v1/llm",
    tags=["LLM History"],
    dependencies=[Depends(AuthProvider)],
)


@router.get("/requests/{request_id}")
async def get_request_result(
    request: Request,
    request_id: str,
    tenant_id: Optional[str] = Query(None),
):
    """Return stored source and output texts for a given LLM request ID."""
    try:
        uid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id format")

    if tenant_id and not getattr(request.state, "tenant_id", None):
        request.state.tenant_id = tenant_id
        request.state.needs_tenant_context = False

    db: AsyncSession = await get_tenant_db_session(request)

    repository = LLMRepository(db)
    record = await repository.get_request_by_id(uid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found")

    results = record.results or []
    return {
        "request_id": str(record.id),
        "source_language": record.input_language,
        "target_language": record.output_language,
        "translations": [
            {
                "source_text": r.source_text,
                "target_text": r.output_text,
            }
            for r in results
        ],
    }
