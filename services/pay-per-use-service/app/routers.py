from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_access import assert_adopter_usage_access, assert_tenant_usage_access, assert_wallet_access
from app.config import settings
from app.database import get_session
from app.models_db import QuotaUsage, UsageRecord, WalletBalance, WalletTransaction
from app.redis_client import get_redis
from app.schemas import CheckRequest, CheckResponse, RecordRequest, RecordResponse, TopUpRequest

logger = logging.getLogger("pay-per-use-api")

router = APIRouter()


async def _sliding_allow(rds, key: str, limit: int, window_sec: float) -> bool:
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


async def _policy_snapshot(tenant_id: str, rds) -> Dict[str, Any]:
    raw = await rds.get(f"policy:{tenant_id}")
    if raw:
        return json.loads(raw)
    url = f"{settings.multi_tenant_url.rstrip('/')}/internal/tenant-plan/tenant-id/{tenant_id}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    data = r.json()
    await rds.setex(f"policy:{tenant_id}", 3600, json.dumps(data))
    return data


async def _policy_snapshot_safe(tenant_id: str, rds) -> Dict[str, Any]:
    try:
        return await _policy_snapshot(tenant_id, rds)
    except HTTPException:
        return {}


async def _incr_daily_block_counter(rds, kind: str) -> None:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    k = f"ppu:block:{kind}:{day}"
    await rds.incr(k)
    await rds.expire(k, 86400 * 14)


async def _daily_block_counts(rds) -> tuple[int, int, int]:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    q = int(await rds.get(f"ppu:block:quota:{day}") or 0)
    rlim = int(await rds.get(f"ppu:block:rate:{day}") or 0)
    b = int(await rds.get(f"ppu:block:budget:{day}") or 0)
    return q, rlim, b


def _remaining_balance(wb: WalletBalance) -> Decimal:
    tpc = Decimal(str(wb.total_plan_cost or 0))
    tu = Decimal(str(wb.total_used or 0))
    if tpc > 0:
        return tpc - tu
    return Decimal(str(wb.balance or 0))


async def _wallet_row(
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
                    row.balance = _remaining_balance(row)
            except Exception:
                pass
    return row


def _rate_from_policy(policy: Dict[str, Any], service_id: str, tier: str) -> Decimal:
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


async def _fetch_model_management_billing(service_id: str) -> Optional[Dict[str, Any]]:
    base = (settings.model_management_url or "").strip().rstrip("/")
    if not base or not str(service_id).strip():
        return None
    path_id = quote(str(service_id).strip(), safe="")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/internal/service-billing/{path_id}")
    except Exception as e:
        logger.warning("model_management billing HTTP error service_id=%s: %s", service_id, e)
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


async def _resolve_usage_rate(
    policy: Dict[str, Any],
    service_id: str,
    tier: str,
    rds,
) -> Decimal:
    rate = _rate_from_policy(policy, service_id, tier)
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
    mm = await _fetch_model_management_billing(service_id)
    if mm and mm.get("cost_per_unit") is not None:
        try:
            d = Decimal(str(mm["cost_per_unit"]))
            if d > 0:
                await rds.setex(f"pricing:{service_id}:{tier}", 86400, str(d))
                return d
        except Exception:
            pass
    return Decimal("0")


async def _prefetch_mm_billing(service_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    seen: List[str] = []
    for x in service_ids:
        s = str(x).strip()
        if s and s not in seen:
            seen.append(s)
    if not seen:
        return {}
    sem = asyncio.Semaphore(10)

    async def one(sid: str) -> tuple[str, Optional[Dict[str, Any]]]:
        async with sem:
            mm = await _fetch_model_management_billing(sid)
            return sid, mm

    pairs = await asyncio.gather(*[one(s) for s in seen])
    return {sid: mm for sid, mm in pairs if mm}


def _mm_rate_from_entry(mm: Optional[Dict[str, Any]]) -> float:
    if not mm:
        return 0.0
    try:
        return float(mm.get("cost_per_unit") or 0)
    except (TypeError, ValueError):
        return 0.0


def _mm_service_label(
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


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = now.date().toordinal() + 1
    next_midnight = datetime.fromordinal(tomorrow).replace(tzinfo=timezone.utc)
    return max(1, int((next_midnight - now).total_seconds()))


def _period_month() -> str:
    d = date.today()
    return f"{d.year:04d}-{d.month:02d}"


@router.post("/check", response_model=CheckResponse)
async def check_usage(body: CheckRequest, session: AsyncSession = Depends(get_session)):
    rds = await get_redis()
    try:
        policy = await _policy_snapshot(body.tenant_id, rds)
    except HTTPException as e:
        if e.detail == "tenant_policy_not_found":
            return CheckResponse(allowed=False, reason="no_policy")
        raise

    rc = policy.get("rate_limit_config") or {}
    qc = policy.get("quota_config") or {}

    rph_key = int(rc.get("requests_per_hour_per_api_key") or 10**9)
    rph_tenant = int(rc.get("requests_per_hour_per_tenant") or 10**9)

    if not await _sliding_allow(rds, f"rate:apikey:hour:{body.api_key_id}", rph_key, 3600.0):
        await _incr_daily_block_counter(rds, "rate")
        raise HTTPException(status_code=429, detail={"allowed": False, "reason": "rate_limit_exceeded"})
    if not await _sliding_allow(rds, f"rate:tenant:hour:{body.tenant_id}", rph_tenant, 3600.0):
        await _incr_daily_block_counter(rds, "rate")
        raise HTTPException(status_code=429, detail={"allowed": False, "reason": "rate_limit_exceeded"})

    req_hour = int(qc.get("requests_per_hour") or 10**9)
    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    hkey = f"quota:reqhour:{body.tenant_id}:{hour_bucket}"
    used_h = int(await rds.incr(hkey))
    if used_h == 1:
        await rds.expire(hkey, 7200)
    if used_h > req_hour:
        await _incr_daily_block_counter(rds, "quota")
        raise HTTPException(status_code=429, detail={"allowed": False, "reason": "quota_exceeded"})

    wb = await _wallet_row(session, body.tenant_id, policy)
    await session.refresh(wb)
    rem = _remaining_balance(wb)
    if rem <= 0:
        await _incr_daily_block_counter(rds, "budget")
        raise HTTPException(status_code=402, detail={"allowed": False, "reason": "plan_budget_exhausted"})

    return CheckResponse(allowed=True)


@router.post("/record", response_model=RecordResponse)
async def record_usage(body: RecordRequest, session: AsyncSession = Depends(get_session)):
    rds = await get_redis()
    policy = await _policy_snapshot(body.tenant_id, rds)
    tier = str(policy.get("tier") or "")

    rate = await _resolve_usage_rate(policy, body.service_id, tier, rds)

    units = Decimal(str(body.units_consumed))
    cost = units * rate

    wb = await _wallet_row(session, body.tenant_id, policy)
    await session.refresh(wb)
    rem = _remaining_balance(wb)
    if rem < cost:
        raise HTTPException(status_code=402, detail="Plan budget exhausted")

    new_used = Decimal(str(wb.total_used or 0)) + cost
    wb.total_used = new_used
    wb.balance = _remaining_balance(wb)

    session.add(
        WalletTransaction(
            tenant_id=body.tenant_id,
            amount=-cost,
            type="debit",
            reference_id=str(uuid.uuid4()),
        )
    )
    session.add(
        UsageRecord(
            tenant_id=body.tenant_id,
            api_key_id=body.api_key_id,
            service_id=body.service_id,
            units_consumed=units,
            cost=cost,
            rate_used=rate,
            tier=tier or None,
        )
    )

    period = _period_month()
    qu = await session.scalar(
        select(QuotaUsage).where(
            QuotaUsage.tenant_id == body.tenant_id,
            QuotaUsage.service_id == body.service_id,
            QuotaUsage.period == period,
        )
    )
    if qu is None:
        qu = QuotaUsage(
            tenant_id=body.tenant_id,
            service_id=body.service_id,
            period=period,
            requests_used=1,
            units_used=units,
        )
        session.add(qu)
    else:
        qu.requests_used = int(qu.requests_used or 0) + 1
        qu.units_used = Decimal(str(qu.units_used or 0)) + units

    qk = f"quota:{body.tenant_id}:{body.service_id}"
    await rds.incrbyfloat(qk, float(units))

    await session.commit()
    await session.refresh(wb)
    return RecordResponse(recorded=True, cost=float(cost), remaining_balance=float(_remaining_balance(wb)))


@router.get("/usage/tenant/{tenant_id}")
async def usage_tenant(
    tenant_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    assert_tenant_usage_access(request, tenant_id)
    rds = await get_redis()
    total_req = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(UsageRecord.tenant_id == tenant_id)
    )
    wb = await _wallet_row(session, tenant_id)
    await session.refresh(wb)

    try:
        policy = await _policy_snapshot(tenant_id, rds)
    except HTTPException:
        policy = {}

    tpc = float(wb.total_plan_cost or 0)
    tu = float(wb.total_used or 0)
    rem = float(_remaining_balance(wb))
    util_pct = round(100.0 * tu / tpc, 1) if tpc > 0 else 0.0

    qc = policy.get("quota_config") or {}
    svc_limits = qc.get("service_limits") or []
    if isinstance(svc_limits, dict):
        svc_limits = [
            {"service_type": k, "unit_type": "", "limit_value": int(v)}
            for k, v in svc_limits.items()
        ]

    by_svc = await session.execute(
        select(UsageRecord.service_id, func.sum(UsageRecord.units_consumed), func.sum(UsageRecord.cost))
        .where(UsageRecord.tenant_id == tenant_id)
        .group_by(UsageRecord.service_id)
    )

    sid_meta: Dict[str, Dict[str, Any]] = {}
    for s in policy.get("allowed_services") or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("service_id") or "")
        if not sid:
            continue
        sname = str(s.get("service_name") or s.get("task_type") or sid)
        try:
            rate_pu = float(s.get("cost_per_unit") or 0)
        except (TypeError, ValueError):
            rate_pu = 0.0
        sid_meta[sid] = {
            "service_name": sname,
            "unit_type": str(s.get("unit_type") or ""),
            "rate_per_unit": rate_pu,
        }

    slist = svc_limits if isinstance(svc_limits, list) else []

    def _match_quota_limit(service_label: str) -> tuple[int, str]:
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

    service_usage: List[Dict[str, Any]] = []
    for sid, u, c in by_svc.all():
        sid_s = str(sid)
        meta = sid_meta.get(sid_s, {})
        sname = str(meta.get("service_name") or sid_s)
        ut = str(meta.get("unit_type") or "")
        rate_pu = float(meta.get("rate_per_unit") or 0.0)
        recorded_cost = float(c or 0)
        units_used = float(u or 0)
        if rate_pu <= 0 or (units_used > 0 and recorded_cost == 0):
            mm = await _fetch_model_management_billing(sid_s)
            if mm:
                sname, ut = _mm_service_label(mm, sid_s, sname, ut)
                try:
                    mm_cpu = float(mm.get("cost_per_unit") or 0)
                    if mm_cpu > 0:
                        rate_pu = mm_cpu
                except (TypeError, ValueError):
                    pass
        lim, ut_sl = _match_quota_limit(sname)
        if lim == 0:
            lim, ut_sl = _match_quota_limit(sid_s)
        ut = ut or ut_sl or "units"
        qpct = round(100.0 * units_used / lim, 1) if lim and lim > 0 else 0.0
        display_cost = recorded_cost if recorded_cost > 0 else round(units_used * rate_pu, 6)
        service_usage.append(
            {
                "service_name": sname,
                "unit_type": ut,
                "units_used": units_used,
                "quota_limit": lim or 0,
                "quota_percent": qpct,
                "rate_per_unit": rate_pu,
                "total_cost": display_cost,
            }
        )

    by_key = await session.execute(
        select(
            UsageRecord.api_key_id,
            func.count(),
            func.sum(UsageRecord.units_consumed),
            func.sum(UsageRecord.cost),
            func.max(UsageRecord.created_at),
        )
        .where(UsageRecord.tenant_id == tenant_id)
        .group_by(UsageRecord.api_key_id)
    )
    api_key_breakdown: List[Dict[str, Any]] = []
    for kid, cnt, units, cst, last_at in by_key.all():
        masked = f"{str(kid)[:8]}***" if kid else ""
        api_key_breakdown.append(
            {
                "api_key_id": str(kid),
                "api_key_masked": masked,
                "requests": int(cnt or 0),
                "units_consumed": float(units or 0),
                "total_cost": float(cst or 0),
                "last_used": last_at.isoformat() if last_at else None,
            }
        )

    near_quota = any((s.get("quota_percent") or 0) >= 80 for s in service_usage)
    low_budget = tpc > 0 and (rem / tpc) < 0.2
    status = "Active"
    if rem <= 0 or any((s.get("quota_percent") or 0) >= 100 for s in service_usage):
        status = "Blocked"
    elif near_quota or low_budget:
        status = "Near limit"

    display_name = str(policy.get("tenant_name") or tenant_id)

    return {
        "tenant_id": tenant_id,
        "tenant_name": display_name,
        "plan": {
            "plan_name": policy.get("plan_name", ""),
            "tier": policy.get("tier", ""),
            "cost": tpc or float(policy.get("plan_cost") or 0),
        },
        "wallet": {
            "total_plan_cost": tpc,
            "total_used": tu,
            "remaining": rem,
            "utilization_percent": util_pct,
        },
        "status": status,
        "total_requests": int(total_req or 0),
        "service_usage": service_usage,
        "api_key_breakdown": api_key_breakdown,
        "alerts": {
            "quota_warning": near_quota,
            "quota_exceeded": any((s.get("quota_percent") or 0) >= 100 for s in service_usage),
            "budget_low": low_budget,
            "budget_exhausted": rem <= 0,
        },
    }


@router.get("/usage/tenant/{tenant_id}/api-keys")
async def usage_tenant_api_keys(
    tenant_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    assert_tenant_usage_access(request, tenant_id)
    by_key = await session.execute(
        select(
            UsageRecord.api_key_id,
            func.count(),
            func.sum(UsageRecord.units_consumed),
            func.sum(UsageRecord.cost),
            func.max(UsageRecord.created_at),
        )
        .where(UsageRecord.tenant_id == tenant_id)
        .group_by(UsageRecord.api_key_id)
    )
    rows = []
    for kid, cnt, units, cst, last_at in by_key.all():
        rows.append(
            {
                "api_key_id": str(kid),
                "api_key_masked": f"{str(kid)[:8]}***",
                "requests": int(cnt or 0),
                "units_consumed": float(units or 0),
                "total_cost": float(cst or 0),
                "last_used": last_at.isoformat() if last_at else None,
            }
        )
    return rows


@router.get("/usage/adopter")
async def usage_adopter(request: Request, session: AsyncSession = Depends(get_session)):
    assert_adopter_usage_access(request)
    rds = await get_redis()

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    y_start = today_start - timedelta(days=1)
    y_end = today_start

    req_today = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(UsageRecord.created_at >= today_start)
    )
    req_yesterday = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(
            UsageRecord.created_at >= y_start,
            UsageRecord.created_at < y_end,
        )
    )
    rt = int(req_today or 0)
    ry = max(int(req_yesterday or 0), 1)
    vs_y = int(round(100.0 * (rt - ry) / ry))

    q_blk, r_blk, b_blk = await _daily_block_counts(rds)
    quota_sub = q_blk + b_blk
    total_blocked = quota_sub + r_blk

    tenants_distinct = await session.execute(select(UsageRecord.tenant_id).distinct())
    tids_usage = [r[0] for r in tenants_distinct.all()]
    wrows = await session.execute(select(WalletBalance))
    wallets = list(wrows.scalars().all())
    wallet_tids = [w.tenant_id for w in wallets]
    active_tenants = len({*tids_usage, *wallet_tids})

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_svc_month = await session.execute(
        select(
            UsageRecord.service_id,
            func.coalesce(func.sum(UsageRecord.units_consumed), 0),
            func.coalesce(func.sum(UsageRecord.cost), 0),
        )
        .where(UsageRecord.created_at >= month_start)
        .group_by(UsageRecord.service_id)
    )
    svc_rows = list(by_svc_month.all())

    tid_svc_month = await session.execute(
        select(
            UsageRecord.tenant_id,
            UsageRecord.service_id,
            func.coalesce(func.sum(UsageRecord.units_consumed), 0),
            func.coalesce(func.sum(UsageRecord.cost), 0),
        )
        .where(UsageRecord.created_at >= month_start)
        .group_by(UsageRecord.tenant_id, UsageRecord.service_id)
    )
    tsm_rows = list(tid_svc_month.all())

    unique_mm_sids: List[str] = []
    _seen_sid: set[str] = set()
    for sid, _, _ in svc_rows:
        s = str(sid)
        if s not in _seen_sid:
            _seen_sid.add(s)
            unique_mm_sids.append(s)
    for _tid, sid, _, _ in tsm_rows:
        s = str(sid)
        if s not in _seen_sid:
            _seen_sid.add(s)
            unique_mm_sids.append(s)
    mm_by_sid = await _prefetch_mm_billing(unique_mm_sids)

    tenant_ids_for_policy = list({*tids_usage, *wallet_tids})
    sem = asyncio.Semaphore(12)

    async def load_pol(tid: str) -> tuple[str, Dict[str, Any]]:
        async with sem:
            p = await _policy_snapshot_safe(tid, rds)
            return tid, p

    policy_by_tid: Dict[str, Dict[str, Any]] = {}
    if tenant_ids_for_policy:
        loaded = await asyncio.gather(*[load_pol(t) for t in tenant_ids_for_policy])
        policy_by_tid = {t: p for t, p in loaded}

    plan_breakdown = {"premium": 0, "standard": 0, "basic": 0}
    for _tid, pol in policy_by_tid.items():
        tier = str(pol.get("tier") or "")
        if tier == "Tier-1":
            plan_breakdown["premium"] += 1
        elif tier == "Tier-2":
            plan_breakdown["standard"] += 1
        elif tier == "Tier-3":
            plan_breakdown["basic"] += 1

    sid_to_label: Dict[str, tuple[str, str]] = {}
    stype_limit_sum: Dict[str, int] = defaultdict(int)
    stype_unit_label: Dict[str, str] = defaultdict(str)

    for pol in policy_by_tid.values():
        for s in pol.get("allowed_services") or []:
            if not isinstance(s, dict):
                continue
            sid = str(s.get("service_id") or "")
            if not sid:
                continue
            sname = str(s.get("service_name") or s.get("task_type") or sid)
            ut = str(s.get("unit_type") or "")
            sid_to_label[sid] = (sname, ut)
        qc = pol.get("quota_config") or {}
        for sl in qc.get("service_limits") or []:
            if not isinstance(sl, dict):
                continue
            st = str(sl.get("service_type") or "").strip().upper()
            if not st:
                continue
            stype_limit_sum[st] += int(sl.get("limit_value") or 0)
            uts = str(sl.get("unit_type") or "")
            if uts:
                stype_unit_label[st] = uts

    def _norm_sid_label(sid: str) -> tuple[str, str]:
        if sid in sid_to_label:
            return sid_to_label[sid][0], sid_to_label[sid][1]
        return sid, ""

    cost_consumed_display = 0.0
    service_usage: List[Dict[str, Any]] = []
    for sid, used, rec_c in svc_rows:
        sid_s = str(sid)
        pol_name, pol_ut = _norm_sid_label(sid_s)
        mm = mm_by_sid.get(sid_s)
        name, ut_svc = _mm_service_label(mm, sid_s, pol_name, pol_ut)
        u = float(used or 0)
        rc = float(rec_c or 0)
        rate = _mm_rate_from_entry(mm)
        cost_consumed_display += rc if rc > 0 else u * rate
        key = name.upper().replace(" ", "_")
        limit_total = int(stype_limit_sum.get(key, 0))
        if limit_total == 0:
            for st_key, lim in stype_limit_sum.items():
                if st_key in key or key in st_key:
                    limit_total = int(lim)
                    break
        if limit_total == 0:
            limit_total = int(max(u * 1.25, 1.0))
        ut = stype_unit_label.get(key, "") or ut_svc or "units"
        service_usage.append(
            {
                "service_name": name,
                "unit_type": ut,
                "used": u,
                "limit": float(limit_total),
            }
        )
    service_usage.sort(key=lambda x: x["used"], reverse=True)

    tenant_month_cost: Dict[str, float] = defaultdict(float)
    for tid, sid, units, rec_c in tsm_rows:
        sid_s = str(sid)
        mm = mm_by_sid.get(sid_s)
        u = float(units or 0)
        rc = float(rec_c or 0)
        rate = _mm_rate_from_entry(mm)
        tenant_month_cost[str(tid)] += rc if rc > 0 else u * rate
    for tid in tenant_ids_for_policy:
        tenant_month_cost.setdefault(str(tid), 0.0)
    top_sorted = sorted(tenant_month_cost.items(), key=lambda x: (-x[1], x[0]))[:20]

    top: List[Dict[str, Any]] = []
    for tid, cst in top_sorted:
        pol = policy_by_tid.get(tid, {})
        plan_label = str(pol.get("plan_name") or pol.get("tier") or "")
        tname = str(pol.get("tenant_name") or tid)
        wb = await _wallet_row(session, tid, pol)
        await session.refresh(wb)
        tpc = float(wb.total_plan_cost or 0)
        rem = float(_remaining_balance(wb))
        st_lbl = "Active"
        if tpc > 0 and rem <= 0:
            st_lbl = "Blocked"
        elif tpc > 0 and (rem / tpc) < 0.2:
            st_lbl = "Near limit"
        top.append(
            {
                "tenant_id": tid,
                "tenant_name": tname,
                "plan": plan_label or "—",
                "cost": cst,
                "status": st_lbl,
            }
        )

    return {
        "summary": {
            "total_requests_today": rt,
            "requests_vs_yesterday_percent": vs_y,
            "active_tenants": active_tenants,
            "plan_breakdown": plan_breakdown,
            "cost_consumed_this_month": float(cost_consumed_display),
            "blocked_requests": {
                "total": total_blocked,
                "quota_exceeded": quota_sub,
                "rate_limited": r_blk,
            },
        },
        "service_usage": service_usage,
        "top_tenants": top,
    }


@router.get("/wallet/{tenant_id}")
async def get_wallet(tenant_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    assert_wallet_access(request, tenant_id)
    rds = await get_redis()
    try:
        policy = await _policy_snapshot(tenant_id, rds)
    except HTTPException:
        policy = None
    wb = await _wallet_row(session, tenant_id, policy or {})
    await session.refresh(wb)
    rem = _remaining_balance(wb)
    return {
        "tenant_id": tenant_id,
        "balance": float(rem),
        "total_plan_cost": float(wb.total_plan_cost or 0),
        "total_used": float(wb.total_used or 0),
        "remaining": float(rem),
        "currency": wb.currency,
    }


@router.post("/wallet/{tenant_id}/topup")
async def topup_wallet(
    tenant_id: str,
    body: TopUpRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    assert_wallet_access(request, tenant_id)
    wb = await _wallet_row(session, tenant_id)
    wb.balance = Decimal(str(wb.balance)) + body.amount
    if wb.total_plan_cost and wb.total_plan_cost > 0:
        wb.total_plan_cost = Decimal(str(wb.total_plan_cost)) + body.amount
    session.add(
        WalletTransaction(
            tenant_id=tenant_id,
            amount=body.amount,
            type="credit",
            reference_id=str(uuid.uuid4()),
        )
    )
    await session.commit()
    await session.refresh(wb)
    return {"tenant_id": tenant_id, "balance": float(_remaining_balance(wb))}


@router.get("/quota/{tenant_id}/status")
async def quota_status(tenant_id: str, request: Request):
    assert_wallet_access(request, tenant_id)
    rds = await get_redis()
    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    hkey = f"quota:reqhour:{tenant_id}:{hour_bucket}"
    used = await rds.get(hkey)
    return {"tenant_id": tenant_id, "requests_this_hour": int(used or 0)}


@router.post("/quota/{tenant_id}/reset")
async def quota_reset(tenant_id: str, request: Request):
    assert_wallet_access(request, tenant_id)
    rds = await get_redis()
    await rds.delete(f"quota:reqday:{tenant_id}")
    keys = await rds.keys(f"quota:{tenant_id}:*")
    if keys:
        await rds.delete(*keys)
    return {"tenant_id": tenant_id, "reset": True}
