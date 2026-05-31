from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pay_per_use.wallet import WalletBalance

logger = logging.getLogger("pay-per-use-helpers")


async def sliding_allow(rds, key: str, limit: int, window_sec: float) -> bool:
    if limit <= 0:
        return True
    now = time.time()
    await rds.zremrangebyscore(key, "-inf", now - window_sec)
    n = await rds.zcard(key)
    if n >= limit:
        return False
    await rds.zadd(key, {f"{now}-{uuid.uuid4().hex}": now})
    await rds.expire(key, int(window_sec) + 1)
    return True


async def policy_snapshot(tenant_id: str, rds) -> Dict[str, Any]:
    raw = await rds.get(f"policy:{tenant_id}")
    if raw:
        return json.loads(raw)
    url = f"{settings.auth_service_url.rstrip('/')}/internal/tenant-plan/tenant-id/{tenant_id}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    data = r.json()
    await rds.setex(f"policy:{tenant_id}", 3600, json.dumps(data))
    return data


async def policy_snapshot_safe(tenant_id: str, rds) -> Dict[str, Any]:
    try:
        return await policy_snapshot(tenant_id, rds)
    except HTTPException:
        return {}
    except Exception as exc:
        logger.warning("policy_snapshot_failed tenant_id=%s err=%s", tenant_id, exc, exc_info=False)
        return {}


async def incr_daily_block_counter(rds, kind: str) -> None:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    k = f"ppu:block:{kind}:{day}"
    await rds.incr(k)
    await rds.expire(k, 86400 * 14)


async def daily_block_counts(rds) -> tuple[int, int, int]:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    q = int(await rds.get(f"ppu:block:quota:{day}") or 0)
    rlim = int(await rds.get(f"ppu:block:rate:{day}") or 0)
    b = int(await rds.get(f"ppu:block:budget:{day}") or 0)
    return q, rlim, b


def remaining_balance(wb: WalletBalance) -> Decimal:
    tpc = Decimal(str(wb.total_plan_cost or 0))
    tu = Decimal(str(wb.total_used or 0))
    if tpc > 0:
        return tpc - tu
    return Decimal(str(wb.balance or 0))


async def wallet_row(
    session: AsyncSession,
    tenant_id: str,
    policy: Optional[Dict[str, Any]] = None,
) -> WalletBalance:
    row = await session.scalar(select(WalletBalance).where(WalletBalance.tenant_id == tenant_id))
    if row is None:
        row = WalletBalance(
            tenant_id=tenant_id,
            balance=Decimal("0"),
            total_plan_cost=Decimal("0"),
            total_used=Decimal("0"),
            currency="INR",
        )
        if policy:
            pc = policy.get("plan_cost")
            if pc is not None:
                try:
                    pcd = Decimal(str(pc))
                    row.total_plan_cost = pcd
                    row.balance = pcd
                except Exception:
                    pass
        session.add(row)
        await session.flush()
    elif policy:
        pc = policy.get("plan_cost")
        if pc is not None:
            try:
                pcd = Decimal(str(pc))
                if (row.total_plan_cost is None or row.total_plan_cost == 0) and pcd > 0:
                    row.total_plan_cost = pcd
                    row.balance = remaining_balance(row)
            except Exception:
                pass
    return row


def rate_from_policy(policy: Dict[str, Any], service_id: str, tier: str) -> Decimal:
    for s in policy.get("allowed_services") or []:
        if not isinstance(s, dict):
            continue
        if str(s.get("service_id") or "") == str(service_id):
            v = s.get("cost_per_unit")
            if v is not None:
                try:
                    return Decimal(str(v))
                except Exception:
                    return Decimal("0")
    return Decimal("0")


async def fetch_service_billing(service_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
    from app.models.service import Service
    sid = str(service_id).strip()
    if not sid:
        return None
    svc = await session.scalar(select(Service).where(Service.service_id == sid))
    if not svc:
        return None
    return {
        "name": svc.name,
        "cost_per_unit": float(svc.cost_per_unit) if svc.cost_per_unit is not None else None,
        "unit_type": svc.billing_unit_type,
        "task_type": None,
    }


async def resolve_usage_rate(
    policy: Dict[str, Any],
    service_id: str,
    tier: str,
    rds,
    session: AsyncSession,
) -> Decimal:
    rate = rate_from_policy(policy, service_id, tier)
    if rate > 0:
        return rate
    cpu_s = await rds.get(f"pricing:{service_id}:{tier}")
    if cpu_s is None:
        cpu_s = await rds.get(f"pricing:{service_id}:{tier or 'Tier-2'}")
    if cpu_s is not None:
        try:
            d = Decimal(str(cpu_s))
            if d > 0:
                return d
        except Exception:
            pass
    mm = await fetch_service_billing(service_id, session)
    if mm and mm.get("cost_per_unit") is not None:
        try:
            d = Decimal(str(mm["cost_per_unit"]))
            if d > 0:
                await rds.setex(f"pricing:{service_id}:{tier}", 86400, str(d))
                return d
        except Exception:
            pass
    return Decimal("0")


async def prefetch_service_billing(service_ids: List[str], session: AsyncSession) -> Dict[str, Dict[str, Any]]:
    from app.models.service import Service
    seen = list(dict.fromkeys(str(x).strip() for x in service_ids if str(x).strip()))
    if not seen:
        return {}
    rows = await session.execute(select(Service).where(Service.service_id.in_(seen)))
    return {
        svc.service_id: {
            "name": svc.name,
            "cost_per_unit": float(svc.cost_per_unit) if svc.cost_per_unit is not None else None,
            "unit_type": svc.billing_unit_type,
            "task_type": None,
        }
        for svc in rows.scalars().all()
    }


def mm_rate_from_entry(mm: Optional[Dict[str, Any]]) -> float:
    if not mm:
        return 0.0
    try:
        return float(mm.get("cost_per_unit") or 0)
    except (TypeError, ValueError):
        return 0.0


def mm_service_label(
    mm: Optional[Dict[str, Any]],
    sid: str,
    policy_name: str,
    policy_ut: str,
) -> tuple[str, str]:
    if mm:
        tt = str(mm.get("task_type") or "").strip().upper()
        if tt:
            ut = str(mm.get("unit_type") or "").strip() or policy_ut or "units"
            return tt, ut
        nm = str(mm.get("name") or "").strip()
        if nm:
            ut = str(mm.get("unit_type") or "").strip() or policy_ut or "units"
            return nm, ut
    if policy_name and policy_name != sid:
        return policy_name, policy_ut or "units"
    return sid, policy_ut or "units"


def period_month() -> str:
    d = date.today()
    return f"{d.year:04d}-{d.month:02d}"


def match_quota_limit(service_label: str, slist: list) -> tuple[int, str]:
    label_u = service_label.upper().replace(" ", "_")
    for sl in slist:
        if not isinstance(sl, dict):
            continue
        st = str(sl.get("service_type") or "").strip()
        if not st:
            continue
        st_u = st.upper().replace(" ", "_")
        if st_u == label_u or st_u in label_u or label_u in st_u:
            return int(sl.get("limit_value") or 0), str(sl.get("unit_type") or "")
    return 0, ""
