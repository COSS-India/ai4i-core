"""
Policy routes.
GET    /policies
POST   /policies
GET    /policies/{policy_id}
PUT    /policies/{policy_id}
PATCH  /policies/{policy_id}/status
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_adopter_admin
from app.db.session import get_db
from app.models.schemas import (
    Meta,
    PolicyCreate,
    PolicyDetailOut,
    PolicyListResponse,
    PolicyOut,
    PolicyPiiTypeOut,
    PolicyStatusUpdate,
    PolicyUpdate,
)
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/policies", tags=["Policies"], dependencies=[Depends(require_adopter_admin)])


def _svc(db: AsyncSession = Depends(get_db)) -> PolicyService:
    return PolicyService(db)


@router.get("", response_model=PolicyListResponse, summary="List all policies")
async def list_policies(
    is_global: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    svc: PolicyService = Depends(_svc),
):
    rows, total = await svc.list(is_global=is_global, is_active=is_active, search=search, page=page, limit=limit)
    # Build list response explicitly (PolicyOut includes pii_types details)
    data: list[PolicyOut] = []
    for row in rows:
        links = row.pii_types or []
        data.append(
            PolicyOut(
                policy_id=row.policy_id,
                name=row.name,
                description=row.description,
                is_active=row.is_active,
                is_global=row.is_global,
                supported_languages=row.supported_languages or [],
                tenant_id=None,
                pii_types_count=len(links),
                pii_types=[
                    PolicyPiiTypeOut(
                        pii_type_id=link.pii_type_id,
                        pii_type_label=link.pii_type.pii_type_label,
                        mask_format=link.pii_type.mask_format,
                    )
                    for link in links
                    if link.pii_type is not None
                ],
                created_at=row.created_at,
            )
        )
    return PolicyListResponse(data=data, meta=Meta(total=total, page=page, limit=limit))


@router.post("", response_model=PolicyDetailOut, status_code=status.HTTP_201_CREATED, summary="Create a new policy")
async def create_policy(request: Request, body: PolicyCreate, svc: PolicyService = Depends(_svc)):
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    obj = await svc.create(body, auth_header=auth_header)
    return _build_detail(obj)


@router.get("/{policy_id}", response_model=PolicyDetailOut, summary="Get policy with linked PII types")
async def get_policy(policy_id: UUID, svc: PolicyService = Depends(_svc)):
    obj = await svc.get_detail(policy_id)
    return _build_detail(obj)


@router.put("/{policy_id}", response_model=PolicyDetailOut, summary="Update policy metadata")
async def update_policy(request: Request, policy_id: UUID, body: PolicyUpdate, svc: PolicyService = Depends(_svc)):
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    obj = await svc.update(policy_id, body, auth_header=auth_header)
    # Build explicit output to include linked PII type details (label + mask_format)
    return _build_detail(obj)


@router.patch("/{policy_id}/status", summary="Toggle active / inactive")
async def set_policy_status(
    policy_id: UUID, body: PolicyStatusUpdate, svc: PolicyService = Depends(_svc)
):
    return await svc.set_status(policy_id, body)


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_detail(policy) -> PolicyDetailOut:
    from app.models.schemas import PolicyPiiTypeOut
    pii_types_out = []
    for link in (policy.pii_types or []):
        pii_types_out.append(
            PolicyPiiTypeOut(
                pii_type_id=link.pii_type_id,
                pii_type_label=link.pii_type.pii_type_label,
                mask_format=link.pii_type.mask_format,
            )
        )
    return PolicyDetailOut(
        policy_id=policy.policy_id,
        name=policy.name,
        description=policy.description,
        is_active=policy.is_active,
        is_global=policy.is_global,
        supported_languages=policy.supported_languages or [],
        pii_types=pii_types_out,
        created_at=policy.created_at,
    )
