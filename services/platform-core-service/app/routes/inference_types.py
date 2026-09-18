"""Inference type catalogue endpoints.

Reads are served from ``core:inference_type:*`` in Redis with a DB fallback;
writes commit to the DB and then rebuild the cache. The catalogue used to be a
module-level snapshot of ``inference_types.yaml`` read once at import — which
is exactly the "needs a redeploy to change" problem this replaces.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.inference_types import (
    InferenceTypeCreate,
    InferenceTypeResponse,
    InferenceTypesResponse,
    InferenceTypeUpdate,
    ListInferenceTypesResponse,
)
from app.services.pay_per_use import inference_type_service

router = APIRouter(
    prefix="/inference-types",
    tags=["Inference Types"],
)


@router.get("", response_model=ListInferenceTypesResponse)
async def list_inference_types(
    session: AsyncSession = Depends(get_db),
) -> ListInferenceTypesResponse:
    """List all supported inference types with their pricing unit."""
    items = await inference_type_service.list_inference_types(session)
    return ListInferenceTypesResponse(
        success=True, data=InferenceTypesResponse(inference_types=items)
    )


@router.get("/{name}", response_model=InferenceTypeResponse)
async def get_inference_type(
    name: str,
    session: AsyncSession = Depends(get_db),
) -> InferenceTypeResponse:
    """Get a single inference type by name."""
    item = await inference_type_service.get_inference_type(session, name)
    return InferenceTypeResponse(success=True, data=item)


@router.post("", response_model=InferenceTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_inference_type(
    request: Request,
    body: InferenceTypeCreate,
    session: AsyncSession = Depends(get_db),
) -> InferenceTypeResponse:
    """Register a new inference type."""
    created_by = request.headers.get("X-User-Id")
    item = await inference_type_service.create_inference_type(
        body, session, created_by=created_by
    )
    return InferenceTypeResponse(success=True, data=item)


@router.put("/{name}", response_model=InferenceTypeResponse)
async def update_inference_type(
    request: Request,
    name: str,
    body: InferenceTypeUpdate,
    session: AsyncSession = Depends(get_db),
) -> InferenceTypeResponse:
    """Update an inference type. Renaming a referenced type returns 409."""
    updated_by = request.headers.get("X-User-Id")
    item = await inference_type_service.update_inference_type(
        name, body, session, updated_by=updated_by
    )
    return InferenceTypeResponse(success=True, data=item)


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        204: {"description": "Inference type deleted. No content is returned."},
        409: {"description": "Referenced by tier_quotas or quota_usage."},
    },
)
async def delete_inference_type(
    name: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Delete an inference type. Blocked with 409 while any tier quota or usage
    row still references it, by id or by name."""
    await inference_type_service.delete_inference_type(name, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
