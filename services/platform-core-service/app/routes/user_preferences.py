"""Per-user table column preferences (GET/PUT/DELETE /preferences/columns/{view_key})."""

from typing import Annotated, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.permissions import is_platform_admin
from app.schemas.common import SuccessResponse, error_responses
from app.services.user_preferences import column_preference_service as svc

router = APIRouter(prefix="/preferences/columns", tags=["User Preferences"])


class ColumnPreferenceData(BaseModel):
    viewKey: str
    visibleColumns: List[str]
    isDefault: bool


class ColumnPreferenceUpdate(BaseModel):
    visibleColumns: List[str] = Field(
        ..., description="Column ids to show; mandatory ids are added automatically."
    )


class ColumnPreferenceResponse(SuccessResponse[ColumnPreferenceData]):
    pass


def _user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise AppError("Authentication is required.", code="AUTHENTICATION_REQUIRED", status_code=401)
    return user_id


@router.get("/{view_key}", responses=error_responses(401, 404))
async def get_column_preference(
    view_key: str, request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> ColumnPreferenceResponse:
    """The caller's visible columns for a view; defaults when none are saved."""
    data = await svc.get_preference(session, _user_id(request), view_key, is_platform_admin(request))
    return ColumnPreferenceResponse(success=True, data=data)


@router.put("/{view_key}", responses=error_responses(401, 404))
async def save_column_preference(
    view_key: str,
    body: ColumnPreferenceUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ColumnPreferenceResponse:
    """Save the caller's visible columns for a view."""
    data = await svc.save_preference(
        session, _user_id(request), view_key, body.visibleColumns, is_platform_admin(request)
    )
    return ColumnPreferenceResponse(success=True, data=data)


@router.delete("/{view_key}", responses=error_responses(401, 404))
async def reset_column_preference(
    view_key: str, request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> ColumnPreferenceResponse:
    """Reset the caller's columns for a view to the defaults."""
    data = await svc.reset_preference(session, _user_id(request), view_key, is_platform_admin(request))
    return ColumnPreferenceResponse(success=True, data=data)
