"""Config management endpoints — list is open to all authenticated users; all other operations are ADMIN only."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError, ValidationError
from app.core.permissions import is_admin
from app.schemas.common import MessageMeta, error_responses
from app.schemas.config_management.config_schema import (
    ConfigCreate,
    ConfigDeletedData,
    ConfigListData,
    ConfigUpdate,
    CreateConfigResponse,
    DeleteConfigResponse,
    GetConfigResponse,
    ListConfigResponse,
    UpdateConfigResponse,
)
from app.services.config_management import config_service

router = APIRouter(prefix="/config", tags=["Config"])

_CONFIG_ID_DESC = "Config ID."


@router.get("")
async def list_configs(
    type: Annotated[Optional[str], Query(max_length=255, description="Filter by config type (e.g. 'domain').")] = None,
    sort_order: Annotated[
        Optional[str],
        Query(
            description=(
                "Sort direction: asc or desc. Without 'type', sorts the config rows by id "
                "(id ascending if omitted). With 'type', sorts that config's data items by "
                "label only when explicitly provided; omitted means no reordering."
            )
        ),
    ] = None,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ListConfigResponse:
    """List all config entries, optionally filtered by type. All authenticated roles."""
    if sort_order is not None and sort_order not in {"asc", "desc"}:
        raise ValidationError(message="sort_order must be 'asc' or 'desc'", code="INVALID_SORT_ORDER")
    items = await config_service.list_configs(session, type_filter=type, sort_order=sort_order)
    return ListConfigResponse(success=True, data=ConfigListData(items=items))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(403, 409),
)
async def create_config(
    payload: ConfigCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> CreateConfigResponse:
    """Create a new config entry. Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    user_id = request.headers.get("X-User-Id")
    item = await config_service.create_config(session, payload, created_by=user_id)
    return CreateConfigResponse(
        success=True,
        data=item,
        meta=MessageMeta(message=f"Config '{item.type}' created."),
    )


@router.get(
    "/{config_id}",
    responses=error_responses(403, 404),
)
async def get_config(
    request: Request,
    config_id: Annotated[int, Path(gt=0, description=_CONFIG_ID_DESC)],
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> GetConfigResponse:
    """Fetch a single config entry by ID. 404 if it does not exist. Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    item = await config_service.get_config(session, config_id)
    return GetConfigResponse(success=True, data=item)


@router.put(
    "/{config_id}",
    responses=error_responses(403, 404, 409),
)
async def update_config(
    payload: ConfigUpdate,
    request: Request,
    config_id: Annotated[int, Path(gt=0, description=_CONFIG_ID_DESC)],
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> UpdateConfigResponse:
    """Update a config entry. Only the fields sent are changed.
    404 if it does not exist. Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    user_id = request.headers.get("X-User-Id")
    item = await config_service.update_config(session, config_id, payload, updated_by=user_id)
    return UpdateConfigResponse(
        success=True,
        data=item,
        meta=MessageMeta(message=f"Config '{item.type}' updated."),
    )


@router.delete(
    "/{config_id}",
    responses=error_responses(403, 404),
)
async def delete_config(
    request: Request,
    config_id: Annotated[int, Path(gt=0, description=_CONFIG_ID_DESC)],
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> DeleteConfigResponse:
    """Delete a config entry by ID. 404 if it does not exist. Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    deleted_id = await config_service.delete_config(session, config_id)
    return DeleteConfigResponse(
        success=True,
        data=ConfigDeletedData(id=deleted_id),
        meta=MessageMeta(message=f"Config {deleted_id} deleted."),
    )
