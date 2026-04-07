"""
PII Type Library routes.
GET    /pii-types
POST   /pii-types
GET    /pii-types/{pii_type_id}
PUT    /pii-types/{pii_type_id}
DELETE /pii-types/{pii_type_id}
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.schemas import (
    Meta,
    PiiTypeCreate,
    PiiTypeListResponse,
    PiiTypeOut,
    PiiTypeUpdate,
)
from app.services.pii_type_service import PiiTypeService

router = APIRouter(prefix="/pii-types", tags=["PII Types"])


def _svc(db: AsyncSession = Depends(get_db)) -> PiiTypeService:
    return PiiTypeService(db)


@router.get("", response_model=PiiTypeListResponse, summary="List all PII types")
async def list_pii_types(
    search: Optional[str] = Query(None, description="Search by PII type label"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    svc: PiiTypeService = Depends(_svc),
):
    rows, total = await svc.list(search=search, page=page, limit=limit)
    data = [PiiTypeOut.model_validate(r) for r in rows]
    return PiiTypeListResponse(data=data, meta=Meta(total=total, page=page, limit=limit))


@router.post("", response_model=PiiTypeOut, status_code=status.HTTP_201_CREATED, summary="Create a new PII type")
async def create_pii_type(body: PiiTypeCreate, svc: PiiTypeService = Depends(_svc)):
    obj = await svc.create(body)
    return PiiTypeOut.model_validate(obj)


@router.get("/{pii_type_id}", response_model=PiiTypeOut, summary="Get a single PII type")
async def get_pii_type(pii_type_id: UUID, svc: PiiTypeService = Depends(_svc)):
    obj = await svc.get(pii_type_id)
    return PiiTypeOut.model_validate(obj)


@router.put("/{pii_type_id}", response_model=PiiTypeOut, summary="Update PII type")
async def update_pii_type(pii_type_id: UUID, body: PiiTypeUpdate, svc: PiiTypeService = Depends(_svc)):
    obj = await svc.update(pii_type_id, body)
    return PiiTypeOut.model_validate(obj)


@router.delete("/{pii_type_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a PII type")
async def delete_pii_type(pii_type_id: UUID, svc: PiiTypeService = Depends(_svc)):
    await svc.delete(pii_type_id)
