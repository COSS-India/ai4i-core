"""PPU usage dashboard routes."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.repositories.pay_per_use.ppu_usage_repository import PPUUsageRepository
from app.schemas.pay_per_use.usage import UsageSummaryResponse
from app.services.pay_per_use.ppu_usage_service import PPUUsageService

router = APIRouter(prefix="/usage", tags=["Usage"])

_ROLE_ADMIN = 1
_ROLE_MODERATOR = 2


def _require_admin(request: Request) -> None:
    raw = request.headers.get("X-Permission-IDS", "")
    ids = {int(m) for m in re.findall(r"\d+", raw)}
    if not ids & {_ROLE_ADMIN, _ROLE_MODERATOR}:
        raise InsufficientPermissionsError()


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    request: Request,
    billing_period: Optional[str] = Query(
        None, description="Billing month in YYYY-MM format. Defaults to current month."
    ),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(request)
    month = billing_period or date.today().strftime("%Y-%m")
    svc = PPUUsageService(PPUUsageRepository(db))
    return await svc.get_summary(month)
