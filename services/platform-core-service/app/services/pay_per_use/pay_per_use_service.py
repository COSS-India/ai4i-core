from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_engine
from app.core.redis import get_redis, get_redis_client
from app.models.pay_per_use.quota_usage import QuotaUsage
from app.models.pay_per_use.subscription_plan import SubscriptionPlan
from app.models.pay_per_use.usage_record import UsageRecord
from app.models.pay_per_use.wallet import WalletBalance, WalletTransaction
from app.schemas.pay_per_use.pay_per_use import (
    CheckRequest,
    CheckResponse,
    RecordRequest,
    RecordResponse,
    TopUpRequest,
)
from app.utils.pay_per_use import (
    daily_block_counts,
    fetch_service_billing,
    incr_daily_block_counter,
    match_quota_limit,
    mm_rate_from_entry,
    mm_service_label,
    period_month,
    policy_snapshot_safe,
    prefetch_service_billing,
    remaining_balance,
    resolve_usage_rate,
    sliding_allow,
    wallet_row,
)

logger = logging.getLogger("pay-per-use-service")


# ── Startup helpers ───────────────────────────────────────────────────────────

async def fetch_mt_services_for_tier(tier: str, session: AsyncSession) -> List[Dict[str, Any]]:
    from app.models.service import Service
    result = await session.execute(
        select(Service).where(Service.is_published.is_(True))
    )
    return [
        {
            "service_id": svc.service_id,
            "service_name": svc.name,
            "cost_per_unit": float(svc.cost_per_unit) if svc.cost_per_unit is not None else 0.0,
            "billing_unit_type": svc.billing_unit_type or "",
            "tier": tier,
        }
        for svc in result.scalars().all()
    ]


async def warm_pricing_cache() -> None:
    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    for attempt in range(1, 4):
        try:
            async with session_factory() as session:
                result = await session.execute(select(SubscriptionPlan))
                plans = list(result.scalars().all())
                rds = get_redis_client()
                for plan in plans:
                    tier = plan.tier or ""
                    svcs = await fetch_mt_services_for_tier(tier, session)
                    for svc in svcs:
                        sid = str(svc.get("service_id") or "")
                        if not sid:
                            continue
                        cpu = float(svc.get("cost_per_unit") or 0)
                        await rds.set(f"pricing:{sid}:{tier}", str(cpu))

            logger.info("Warmed pricing cache for %d plans", len(plans))
            return
        except Exception as e:
            logger.warning("warm_pricing_cache attempt %d failed: %s", attempt, e)
            await asyncio.sleep(2 * attempt)


# ── Pay-per-use business logic ────────────────────────────────────────────────

async def check_usage(body: CheckRequest, session: AsyncSession, rds) -> CheckResponse:
    pol = await policy_snapshot_safe(body.tenant_id, rds)
    if not pol:
        return CheckResponse(allowed=False, reason="no_policy")

    rc = pol.get("rate_limit_config") or {}
    qc = pol.get("quota_config") or {}

    rph_key = int(rc.get("requests_per_hour_per_api_key") or 10**9)
    rph_tenant = int(rc.get("requests_per_hour_per_tenant") or 10**9)

    if not await sliding_allow(rds, f"rate:apikey:hour:{body.api_key_id}", rph_key, 3600.0):
        await incr_daily_block_counter(rds, "rate")
        raise HTTPException(status_code=429, detail={"allowed": False, "reason": "rate_limit_exceeded"})
    if not await sliding_allow(rds, f"rate:tenant:hour:{body.tenant_id}", rph_tenant, 3600.0):
        await incr_daily_block_counter(rds, "rate")
        raise HTTPException(status_code=429, detail={"allowed": False, "reason": "rate_limit_exceeded"})

    req_hour = int(qc.get("requests_per_hour") or 10**9)
    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    hkey = f"quota:reqhour:{body.tenant_id}:{hour_bucket}"
    used_h = int(await rds.incr(hkey))
    if used_h == 1:
        await rds.expire(hkey, 7200)
    if used_h > req_hour:
        await incr_daily_block_counter(rds, "quota")
        raise HTTPException(status_code=429, detail={"allowed": False, "reason": "quota_exceeded"})

    wb = await wallet_row(session, body.tenant_id, pol)
    await session.refresh(wb)
    rem = remaining_balance(wb)
    if rem <= 0:
        await incr_daily_block_counter(rds, "budget")
        raise HTTPException(status_code=402, detail={"allowed": False, "reason": "plan_budget_exhausted"})

    return CheckResponse(allowed=True)


async def record_usage(body: RecordRequest, session: AsyncSession, rds) -> RecordResponse:
    # Safe snapshot: strict policy_snapshot raises when multi-tenant plan API fails — then NMT/pipeline
    # never persists usage and dashboards stay empty. Fall back to {} and resolve rate from Redis/MM.
    pol = await policy_snapshot_safe(body.tenant_id, rds)
    tier = str(pol.get("tier") or "")
    rate = await resolve_usage_rate(pol, body.service_id, tier, rds, session)

    units = Decimal(str(body.units_consumed))
    cost = units * rate

    wb = await wallet_row(session, body.tenant_id, pol)
    await session.refresh(wb)
    rem = remaining_balance(wb)
    has_plan_data = bool(pol)

    # check_usage only guarantees rem > 0, not rem >= cost. If rem < nominal cost, recording
    # used to raise 402 here — NMT returned 200 but PayPerUseClient.record failed and no UsageRecord
    # was stored (dashboard looked "stuck"). Partial debit when wallet covers part of the charge.
    if rem <= 0:
        if has_plan_data:
            raise HTTPException(status_code=402, detail="Plan budget exhausted")
        logger.warning(
            "record_usage: insufficient wallet but no usable tenant plan snapshot — "
            "persisting usage row with zero debit for observability "
            "(tenant_id=%s service_id=%s units=%s rem=%s needed=%s)",
            body.tenant_id, body.service_id, units, rem, cost,
        )
        debit_cost = Decimal("0")
        debit_rate = Decimal("0")
    elif rem < cost:
        if has_plan_data:
            debit_cost = rem
            debit_rate = rate
            logger.info(
                "record_usage: partial debit tenant_id=%s service_id=%s units=%s "
                "nominal_cost=%s remaining=%s debit=%s",
                body.tenant_id, body.service_id, units, cost, rem, debit_cost,
            )
        else:
            logger.warning(
                "record_usage: insufficient wallet but no usable tenant plan snapshot — "
                "persisting usage row with zero debit for observability "
                "(tenant_id=%s service_id=%s units=%s rem=%s needed=%s)",
                body.tenant_id, body.service_id, units, rem, cost,
            )
            debit_cost = Decimal("0")
            debit_rate = Decimal("0")
    else:
        debit_cost = cost
        debit_rate = rate

    if debit_cost > 0:
        wb.total_used = Decimal(str(wb.total_used or 0)) + debit_cost
        # _remaining_balance falls back to wb.balance when total_plan_cost is 0
        # (top-up-only wallets), so the previous assignment was a no-op there.
        # Subtract directly so the wallet decrements in both the plan and no-plan paths.
        wb.balance = Decimal(str(wb.balance or 0)) - debit_cost
        session.add(WalletTransaction(
            tenant_id=body.tenant_id,
            amount=-debit_cost,
            type="debit",
            reference_id=str(uuid.uuid4()),
        ))

    session.add(UsageRecord(
        tenant_id=body.tenant_id,
        api_key_id=body.api_key_id,
        service_id=body.service_id,
        units_consumed=units,
        cost=debit_cost,
        rate_used=debit_rate,
        tier=tier or None,
    ))

    period = period_month()
    qu = await session.scalar(
        select(QuotaUsage).where(
            QuotaUsage.tenant_id == body.tenant_id,
            QuotaUsage.service_id == body.service_id,
            QuotaUsage.period == period,
        )
    )
    if qu is None:
        session.add(QuotaUsage(
            tenant_id=body.tenant_id,
            service_id=body.service_id,
            period=period,
            requests_used=1,
            units_used=units,
        ))
    else:
        qu.requests_used = int(qu.requests_used or 0) + 1
        qu.units_used = Decimal(str(qu.units_used or 0)) + units

    await rds.incrbyfloat(f"quota:{body.tenant_id}:{body.service_id}", float(units))
    await session.commit()
    await session.refresh(wb)

    return RecordResponse(
        recorded=True,
        cost=float(debit_cost),
        remaining_balance=float(remaining_balance(wb)),
    )


async def get_tenant_usage(tenant_id: str, session: AsyncSession, rds) -> Dict[str, Any]:
    total_req = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(UsageRecord.tenant_id == tenant_id)
    )
    wb = await wallet_row(session, tenant_id)
    await session.refresh(wb)
    pol = await policy_snapshot_safe(tenant_id, rds)

    tpc = float(wb.total_plan_cost or 0)
    tu = float(wb.total_used or 0)
    rem = float(remaining_balance(wb))
    util_pct = round(100.0 * tu / tpc, 1) if tpc > 0 else 0.0

    qc = pol.get("quota_config") or {}
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
    for s in pol.get("allowed_services") or []:
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
            mm = await fetch_service_billing(sid_s, session)
            if mm:
                sname, ut = mm_service_label(mm, sid_s, sname, ut)
                try:
                    mm_cpu = float(mm.get("cost_per_unit") or 0)
                    if mm_cpu > 0:
                        rate_pu = mm_cpu
                except (TypeError, ValueError):
                    pass
        lim, ut_sl = match_quota_limit(sname, slist)
        if lim == 0:
            lim, ut_sl = match_quota_limit(sid_s, slist)
        ut = ut or ut_sl or "units"
        qpct = round(100.0 * units_used / lim, 1) if lim and lim > 0 else 0.0
        display_cost = recorded_cost if recorded_cost > 0 else round(units_used * rate_pu, 6)
        service_usage.append({
            "service_name": sname,
            "unit_type": ut,
            "units_used": units_used,
            "quota_limit": lim or 0,
            "quota_percent": qpct,
            "rate_per_unit": rate_pu,
            "total_cost": display_cost,
        })

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
        api_key_breakdown.append({
            "api_key_id": str(kid),
            "api_key_masked": masked,
            "requests": int(cnt or 0),
            "units_consumed": float(units or 0),
            "total_cost": float(cst or 0),
            "last_used": last_at.isoformat() if last_at else None,
        })

    near_quota = any((s.get("quota_percent") or 0) >= 80 for s in service_usage)
    low_budget = tpc > 0 and (rem / tpc) < 0.2
    tenant_status = "Active"
    if rem <= 0 or any((s.get("quota_percent") or 0) >= 100 for s in service_usage):
        tenant_status = "Blocked"
    elif near_quota or low_budget:
        tenant_status = "Near limit"

    return {
        "tenant_id": tenant_id,
        "tenant_name": str(pol.get("tenant_name") or tenant_id),
        "plan": {
            "plan_name": pol.get("plan_name", ""),
            "tier": pol.get("tier", ""),
            "cost": tpc or float(pol.get("plan_cost") or 0),
        },
        "wallet": {
            "total_plan_cost": tpc,
            "total_used": tu,
            "remaining": rem,
            "utilization_percent": util_pct,
        },
        "status": tenant_status,
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


async def get_tenant_api_key_usage(tenant_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
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
    return [
        {
            "api_key_id": str(kid),
            "api_key_masked": f"{str(kid)[:8]}***",
            "requests": int(cnt or 0),
            "units_consumed": float(units or 0),
            "total_cost": float(cst or 0),
            "last_used": last_at.isoformat() if last_at else None,
        }
        for kid, cnt, units, cst, last_at in by_key.all()
    ]


async def get_adopter_usage(session: AsyncSession, rds) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    y_start = today_start - timedelta(days=1)

    req_today = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(UsageRecord.created_at >= today_start)
    )
    req_yesterday = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(
            UsageRecord.created_at >= y_start,
            UsageRecord.created_at < today_start,
        )
    )
    rt = int(req_today or 0)
    ry = max(int(req_yesterday or 0), 1)
    vs_y = int(round(100.0 * (rt - ry) / ry))

    q_blk, r_blk, b_blk = await daily_block_counts(rds)
    quota_sub = q_blk + b_blk

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
    _seen: set[str] = set()
    for sid, _, _ in svc_rows:
        s = str(sid)
        if s not in _seen:
            _seen.add(s)
            unique_mm_sids.append(s)
    for _tid, sid, _, _ in tsm_rows:
        s = str(sid)
        if s not in _seen:
            _seen.add(s)
            unique_mm_sids.append(s)
    mm_by_sid = await prefetch_service_billing(unique_mm_sids, session)

    tenant_ids_for_policy = list({*tids_usage, *wallet_tids})
    sem = asyncio.Semaphore(12)

    async def load_pol(tid: str) -> tuple[str, Dict[str, Any]]:
        async with sem:
            p = await policy_snapshot_safe(tid, rds)
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
            sid_to_label[sid] = (
                str(s.get("service_name") or s.get("task_type") or sid),
                str(s.get("unit_type") or ""),
            )
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

    def _norm(sid: str) -> tuple[str, str]:
        if sid in sid_to_label:
            return sid_to_label[sid]
        return sid, ""

    cost_consumed_display = 0.0
    service_usage: List[Dict[str, Any]] = []
    for sid, used, rec_c in svc_rows:
        sid_s = str(sid)
        pol_name, pol_ut = _norm(sid_s)
        mm = mm_by_sid.get(sid_s)
        name, ut_svc = mm_service_label(mm, sid_s, pol_name, pol_ut)
        u = float(used or 0)
        rc = float(rec_c or 0)
        rate = mm_rate_from_entry(mm)
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
        service_usage.append({"service_name": name, "unit_type": ut, "used": u, "limit": float(limit_total)})
    service_usage.sort(key=lambda x: x["used"], reverse=True)

    tenant_month_cost: Dict[str, float] = defaultdict(float)
    for tid, sid, units, rec_c in tsm_rows:
        mm = mm_by_sid.get(str(sid))
        u = float(units or 0)
        rc = float(rec_c or 0)
        rate = mm_rate_from_entry(mm)
        tenant_month_cost[str(tid)] += rc if rc > 0 else u * rate
    for tid in tenant_ids_for_policy:
        tenant_month_cost.setdefault(str(tid), 0.0)

    top: List[Dict[str, Any]] = []
    for tid, cst in sorted(tenant_month_cost.items(), key=lambda x: (-x[1], x[0]))[:20]:
        pol = policy_by_tid.get(tid, {})
        wb = await wallet_row(session, tid, pol)
        await session.refresh(wb)
        tpc = float(wb.total_plan_cost or 0)
        rem = float(remaining_balance(wb))
        st_lbl = "Active"
        if tpc > 0 and rem <= 0:
            st_lbl = "Blocked"
        elif tpc > 0 and (rem / tpc) < 0.2:
            st_lbl = "Near limit"
        top.append({
            "tenant_id": tid,
            "tenant_name": str(pol.get("tenant_name") or tid),
            "plan": str(pol.get("plan_name") or pol.get("tier") or "—"),
            "cost": cst,
            "status": st_lbl,
        })

    return {
        "summary": {
            "total_requests_today": rt,
            "requests_vs_yesterday_percent": vs_y,
            "active_tenants": active_tenants,
            "plan_breakdown": plan_breakdown,
            "cost_consumed_this_month": float(cost_consumed_display),
            "blocked_requests": {
                "total": quota_sub + r_blk,
                "quota_exceeded": quota_sub,
                "rate_limited": r_blk,
            },
        },
        "service_usage": service_usage,
        "top_tenants": top,
    }


async def get_wallet(tenant_id: str, session: AsyncSession, rds) -> Dict[str, Any]:
    pol = await policy_snapshot_safe(tenant_id, rds)
    wb = await wallet_row(session, tenant_id, pol)
    await session.refresh(wb)
    rem = remaining_balance(wb)
    return {
        "tenant_id": tenant_id,
        "balance": float(rem),
        "total_plan_cost": float(wb.total_plan_cost or 0),
        "total_used": float(wb.total_used or 0),
        "remaining": float(rem),
        "currency": wb.currency,
    }


async def topup_wallet(tenant_id: str, body: TopUpRequest, session: AsyncSession) -> Dict[str, Any]:
    wb = await wallet_row(session, tenant_id)
    wb.balance = Decimal(str(wb.balance)) + body.amount
    if wb.total_plan_cost and wb.total_plan_cost > 0:
        wb.total_plan_cost = Decimal(str(wb.total_plan_cost)) + body.amount
    session.add(WalletTransaction(
        tenant_id=tenant_id,
        amount=body.amount,
        type="credit",
        reference_id=str(uuid.uuid4()),
    ))
    await session.commit()
    await session.refresh(wb)
    return {"tenant_id": tenant_id, "balance": float(remaining_balance(wb))}


async def get_quota_status(tenant_id: str, rds) -> Dict[str, Any]:
    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    hkey = f"quota:reqhour:{tenant_id}:{hour_bucket}"
    used = await rds.get(hkey)
    return {"tenant_id": tenant_id, "requests_this_hour": int(used or 0)}


async def reset_quota(tenant_id: str, rds) -> Dict[str, Any]:
    await rds.delete(f"quota:reqday:{tenant_id}")
    keys = await rds.keys(f"quota:{tenant_id}:*")
    if keys:
        await rds.delete(*keys)
    return {"tenant_id": tenant_id, "reset": True}
