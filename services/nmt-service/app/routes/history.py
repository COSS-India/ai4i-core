"""NMT history endpoints — read-only lookup of stored request/result data."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_nmt_service
from app.services.nmt_service import NMTService

router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT History"],
    dependencies=[Depends(AuthProvider)],
)


@router.get("/requests/{request_id}")
async def get_request_result(
    request_id: str,
    nmt_service: NMTService = Depends(get_nmt_service),
):
    """Return stored source and translated texts for a given NMT request ID."""
    try:
        uid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request_id format")

    record = await nmt_service.repository.get_request_by_id(uid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found")

    results = record.results or []
    return {
        "request_id": str(record.id),
        "source_language": record.source_language,
        "target_language": record.target_language,
        "translations": [
            {
                "source_text": r.source_text,
                "target_text": r.translated_text,
            }
            for r in results
        ],
    }
