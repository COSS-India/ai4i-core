import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from ai4i_core.bootstrap import get_redis_client
from ai4i_core.logging import get_logger
from confluent_kafka.cimpl import Message
from sqlalchemy import text

from bootstrap.lifecycle import session_scope
from consumers.payperuse_consumer import config as cfg
from consumers.payperuse_consumer._billing import (
    BillingWriteResult,
    ServicePricing,
    calculate_cost,
    deduct_balance_and_update_quota,
    fetch_tenant_budget_status,
    get_inference_type_id,
    get_service_pricing,
    _get_billing_data,
    _get_billed_key, _update_billing_on_cache,
)
from ai4i_core.kafka import (
    publish_event as publish_notification_event,
    is_notification_enabled,
    get_threshold_bands,
    get_notification_id,
    check_and_record_threshold,
    check_and_record_exhaustion,
    resolve_recipients,
)
from consumers.payperuse_consumer._thresholds import (
    crossed_bands,
    crossed_exhaustion,
    percent,
)

logger = get_logger(__name__)


def _to_float(val, fallback: float = 0.0) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return fallback


def _to_int(val, fallback: int = 0) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return fallback


def _get_otel_attributes(attrs: dict):
    tenant_id: str = str(attrs.get("tenantId") or "").strip()
    service_id: str = str(attrs.get("service_id") or "").strip()
    # Both LLM and Triton spans write real counts to input_tokens/output_tokens
    # (see trace/request_span.py and services/base/task_service.py).
    input_tokens: float = _to_float(attrs.get("input_tokens"))
    output_tokens: float = _to_float(attrs.get("output_tokens"))
    correlation_id: str = str(attrs.get("correlation_id") or "").strip()
    api_key_id: int = _to_int(attrs.get("api_key_id"))
    # Normalise to None so callers never have to guard against "" vs None.
    # validation.py ships X-Tier-ID="" for keyless-tier requests; that empty
    # string propagates here via the OTel span attribute.
    raw_tier = str(attrs.get("tier_id") or "").strip()
    tier_id: Optional[str] = raw_tier or None

    return tenant_id, service_id, input_tokens, output_tokens, correlation_id, api_key_id, tier_id


async def _is_already_billed(billed_key: str, correlation_id: str, span_id: str, msg: Message) -> bool | None:
    if not billed_key:
        return None
    try:
        redis = get_redis_client()
        already_billed = await redis.exists(billed_key)
        if already_billed:
            logger.warning(
                "Duplicate span detected — skipping billing offset=%d"
                " correlation_id=%s span_id=%s",
                msg.offset(), correlation_id, span_id,
            )
            return True
        return False
    except Exception as exc:
        # Redis unavailable: log and continue — billing correctness relies on
        # at-most-one consumer instance when Redis is down.
        logger.warning("Redis dedup check failed — proceeding without dedup: %s", exc)
        return None


async def _post_billing(
    wallet_exhausted: bool, quota_exhausted: bool, tenant_id, api_key_id: int, billing_unit_type: str
):
    """wallet_exhausted is scoped to exactly one API Key (its own
    budget_usage.api_key_budget_snap/api_key_budget_used) — notifying by
    api_key_id, not tenant_id, so it can't flip every sibling key under the
    same tenant. Skipped entirely when api_key_id is 0 (no Key on this span
    — a JWT-authenticated request, or the gateway not yet forwarding
    X-API-Key-ID): there's no key to flag. quota_exhausted stays tenant-wide
    — a tier's monthly quota is a tenant-level entitlement, not a per-key
    ceiling, so it's correct for it to affect every key under the tenant.

    This per-key flag is enforcement (blocks further requests on THIS key
    once ITS OWN allocation runs out) — a deliberately different, unrelated
    concept from the BUDGET_THRESHOLD/BUDGET_EXHAUSTED notification EVENTS
    (_publish_usage_crossing_events, fired earlier in _bill_usage), which
    are tenant-level: an individual key running out never fires those on
    its own, only the tenant's entire pooled budget being crossed/exhausted
    does. Do not "fix" this per-key push into a tenant-wide one to match —
    that would let one exhausted key silently block every sibling key's
    requests too, which is exactly what api_key_id-scoping this exists to
    prevent.



    No longer notifies about the tenant's budget effective window at all —
    /auth/validate now compares budget_effective_to directly from the
    key's own cached payload (see auth-service's validation.py:
    _cached_budget_window_is_expired) instead of trusting a boolean this
    consumer used to push here on every message. That push was wasteful
    (a tenant-wide Redis+DB write on nearly every billed message, most of
    which changed nothing) and still incomplete (a tenant whose spans never
    reach billing — no pricing row, or cost == 0, both early-return in
    _bill_usage above — would never get flagged no matter how expired).
    Comparing the stored date directly is both cheaper and correct for
    every tenant, billed or not."""
    if wallet_exhausted and api_key_id:
        await _notify_auth(
            f"/internal/ppu/api-key/{api_key_id}/budget-exhausted",
            {"exhausted": True},
        )

    if quota_exhausted:
        await _notify_auth(
            f"/internal/ppu/tenant/{tenant_id}/quota-exhausted",
            {"inference_name": billing_unit_type},
        )


@dataclass
class BillingContext:
    tenant_id: str
    service_id: str
    input_tokens: float
    total_tokens: float
    correlation_id: str
    span_id: str
    billed_key: str
    is_already_billed: bool
    billing_month: str
    offset: int
    api_key_id: int = 0
    tier_id: Optional[str] = None


@dataclass
class BillingOutcome:
    pricing: ServicePricing
    billed_units: Decimal
    cost: Decimal
    wallet_exhausted: bool
    quota_exhausted: bool


def _resolve_billing_month(end_time_ns) -> str:
    if end_time_ns:
        return datetime.fromtimestamp(int(end_time_ns) / 1e9, tz=timezone.utc).strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")


_IST = ZoneInfo("Asia/Kolkata")


def _alert_datetime_ist(dt: datetime) -> str:
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD's "when the alert fired" value
    (design doc §9.5), already formatted for display — e.g.
    "2026-09-10 16:52 IST" — so the consumer never has to parse or convert
    occurred_at itself."""
    return dt.astimezone(_IST).strftime("%Y-%m-%d %H:%M") + " IST"


def _display_pct(pct: Decimal) -> Decimal:
    """Clamp a usage percentage to 100 for DISPLAY only (design doc §9.5's
    QUOTA_THRESHOLD/BUDGET_THRESHOLD current_value). A single debit can push
    used past snap (e.g. concurrent requests racing past the ceiling before
    either sees the other's write), so the raw percent(post) can read well
    over 100 — "2900%" in an alert email reads as a bug, not "you're very
    over budget". crossed_bands/crossed_exhaustion in _thresholds.py must
    keep using the raw, uncapped pre_pct/post_pct (this is display-only,
    called after band-crossing/exhaustion are already decided)."""
    return min(pct, Decimal(100))


def _first_of_next_month(billing_month: str) -> str:
    """QUOTA_EXHAUSTED's "Resets on" date (design doc §9.5): quota resets at
    the start of the month after the one it exhausted in, mirroring
    platform-core-service's tier_service._first_of_next_month for the same
    concept on the QUOTA_LIMIT_UPDATED side."""
    year, month = (int(part) for part in billing_month.split("-"))
    if month == 12:
        return f"{year + 1}-01-01"
    return f"{year}-{month + 1:02d}-01"


async def _fetch_tier_name(db, tier_id: Optional[str]) -> str:
    """Best-effort tier name for QUOTA_EXHAUSTED's details[0] — falls back to
    the raw id (still meaningful to an operator, just not as pretty) rather
    than failing the whole publish over a lookup miss."""
    if tier_id is None:
        return ""
    try:
        row = (await db.execute(text("SELECT name FROM tiers WHERE id = CAST(:tid AS uuid)"), {"tid": tier_id})).first()
        return row.name if row is not None else tier_id
    except Exception:
        return tier_id


async def _prepare_billing_context(msg: Message) -> Optional[BillingContext]:
    data: dict | None = _get_billing_data(msg)
    if not data:
        return None

    span_id: str = (data.get("context", {})).get("span_id", "").strip()

    # Deduplicate on correlation_id + span_id, not correlation_id alone.
    # correlation_id is the application-level request identifier injected by
    # RequestMiddleware — stable across Kafka redeliveries of the *same* span,
    # which is what makes it useful for dedup. But a single request can emit
    # multiple ai-inference spans sharing one correlation_id (e.g. TTS chunks
    # text >400 chars into several per_item Triton calls, each its own span —
    # see tts_service.py). Keying on correlation_id alone would make every
    # chunk after the first look like a duplicate of it and get skipped,
    # silently under-billing the request. span_id disambiguates chunks while
    # correlation_id still catches true redeliveries of the same span. The
    # exporter (trace/setup.py) already drops spans with span_id==0, so every
    # span_id reaching this consumer is valid and unique.
    attrs = data.get("attributes", {})
    # tenantId is camelCase in OTel attributes (set by ai4i_core.context middleware).
    tenant_id, service_id, input_tokens, output_tokens, correlation_id, api_key_id, tier_id = _get_otel_attributes(
        attrs)
    billed_key: str = _get_billed_key(correlation_id, span_id)

    is_already_billed = await _is_already_billed(billed_key, correlation_id, span_id, msg)
    if is_already_billed or is_already_billed is None:
        return None

    # Skip billing for JWT / non-API-key requests. authType is set by RequestMiddleware
    # from the X-Auth-Type header injected by APISIX after token validation.
    # Only "api_key" requests are subject to PPU billing. If authType is absent
    # (older spans without this attribute), billing proceeds as before.
    auth_type: str = str(attrs.get("authType", "")).strip()
    if auth_type and auth_type != "api_key":
        logger.debug(
            "Skipping billing for non-API-key request | auth_type=%r offset=%d span_id=%s",
            auth_type, msg.offset(), span_id,
        )
        return None

    total_tokens: float = input_tokens + output_tokens

    logger.debug(
        "Billing fields extracted | offset=%d tenant_id=%r service_id=%r"
        " input_tokens=%s output_tokens=%s total_tokens=%s span_id=%s",
        msg.offset(), tenant_id, service_id, input_tokens, output_tokens, total_tokens, span_id,
    )

    if not (tenant_id and service_id and total_tokens):
        logger.warning(
            "Missing required billing fields — skipping offset=%d"
            " (tenant_id=%r service_id=%r total_tokens=%s)",
            msg.offset(), tenant_id, service_id, total_tokens,
        )
        return None

    if tier_id is None:
        # Normal for api_key requests whose cached auth payload has no tier
        # (validation.py ships X-Tier-ID="" in that case). Budget is still
        # deducted (resources were consumed); quota upsert is skipped because
        # there is no tier to look up — see deduct_balance_and_update_quota.
        logger.warning(
            "api_key span missing tier_id — budget deducted, quota upsert skipped"
            " | offset=%d tenant=%s api_key_id=%s",
            msg.offset(), tenant_id, api_key_id,
        )

    billing_month = _resolve_billing_month(data.get("end_time"))
    logger.debug("Billing month resolved | tenant=%s billing_month=%s", tenant_id, billing_month)

    return BillingContext(
        tenant_id=tenant_id,
        service_id=service_id,
        input_tokens=input_tokens,
        total_tokens=total_tokens,
        correlation_id=correlation_id,
        span_id=span_id,
        billed_key=billed_key,
        is_already_billed=is_already_billed,
        billing_month=billing_month,
        offset=msg.offset(),
        api_key_id=api_key_id,
        tier_id=tier_id,
    )


async def _resolve_recipients(db, auth_db, name: str, tenant_id) -> list[str]:
    """Shared helper for every event in _publish_usage_crossing_events —
    db is this consumer's own session (ai4iplatform_core, where
    configs_notification_alert/tenant_notification_subscription live);
    auth_db is the second, named connection opened for the same reason
    fetch_tenant_budget_status needs it (ai4iplatform_auth, where
    users/roles live)."""
    notification_id = await get_notification_id(db, name)
    if notification_id is None or auth_db is None:
        return []
    return await resolve_recipients(db, auth_db, notification_id=notification_id, tenant_id=str(tenant_id))


async def _publish_usage_crossing_events(
    db, auth_db, ctx: BillingContext, write: BillingWriteResult, cost: Decimal, billed_units: Decimal,
    inference_name: str, budget_threshold_enabled: bool, budget_exhausted_enabled: bool,
) -> None:
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD/QUOTA_EXHAUSTED/BUDGET_EXHAUSTED —
    fired post-commit, per-message. Best-effort: every failure is caught
    inside publish(); this function itself is not wrapped so a bug here
    surfaces in logs rather than being silently eaten, but it must never be
    allowed to affect billing correctness (called only after the commit
    above).

    pre = post - this_debit (for the BUDGET side; see below) is exact
    without a second query ONLY because this consumer group runs a single
    replica — ARCHITECTURE.md §8 pins it there. That is a platform-wide
    deployment constraint, not a per-partition one: tenant_budget.used is a
    fresh SUM over every API key under the tenant (see
    fetch_tenant_budget_status), pooled across whichever Kafka partitions
    those keys' spans landed on (spans carry no tenant-aware partition key
    — see trace/setup.py's exporter, which sends with no `key=` at all — so
    two keys under the same tenant can and do land on different
    partitions). "This consumer processes one message at a time per
    partition" is true, but it only ever made the OLD, per-key version of
    this read exact (a single API key's own budget_usage row can only be
    touched by whichever one partition its spans are on). It says nothing
    about a tenant-pooled read: with more than one replica, a sibling
    instance's commit for a *different* key under the *same* tenant can
    land in between this instance's own commit and this SUM, inflating
    pre_pct and silently skipping whichever threshold band falls between
    the true and the overstated pre_pct — the ledger only remembers the
    highest band reached, so a skipped band is never recovered by a later
    message. See ARCHITECTURE.md §8/§11 for why this is a *second*,
    independent prerequisite for raising replicas — the write-time guard
    and reconciliation job §11 already lists guard against a different
    hazard (duplicate billing from a repeated span) and do not cover this
    one (a notification that was never published, for two distinct spans
    each billed exactly once).

    ledger_notification_alert (design doc §5-7) is checked/updated with
    check_and_record_threshold/check_and_record_exhaustion before each
    publish — the atomic DB-level dedup guard (highest band reached /
    on-off exhausted flag), not just the in-memory is_notification_enabled
    pre-check.

    Both BUDGET and QUOTA crossings are tenant-level events, never a single
    API key's/Application's own allocation running out on its own (design
    change — see fetch_tenant_budget_status's docstring for BUDGET; QUOTA
    was already tenant-level, since quota_usage is keyed by tenant_id, not
    api_key_id, and every key under a tenant shares that tenant's one
    active tier). This is distinct from — and does not change — the
    per-key budget-exhausted ENFORCEMENT flag _post_billing pushes to
    auth-service, which still blocks that one key's own requests once its
    own individual allocation runs out; that is an access-control decision,
    not a notification one.

    budget_threshold_enabled/budget_exhausted_enabled are passed in already
    resolved (_bill_usage checks them before deciding whether to open the
    second, "auth" DB connection at all) rather than read again here — both
    are in-memory cache reads, but fetch_tenant_budget_status is two real
    cross-database queries, and auth_db is None whenever the caller skipped
    opening that connection because neither flag was set."""
    if auth_db is not None and (budget_threshold_enabled or budget_exhausted_enabled):
        tenant_budget = await fetch_tenant_budget_status(auth_db, db, str(ctx.tenant_id))
        if tenant_budget is not None and tenant_budget.snap is not None:
            post_pct = percent(tenant_budget.used, tenant_budget.snap)
            pre_pct = percent(tenant_budget.used - cost, tenant_budget.snap)
            if post_pct is not None and pre_pct is not None:
                # No api_key_id (or anything else) in subject — there is exactly
                # one budget crossing per tenant now, not one per key, so the
                # dedup ledger needs nothing more specific than event_name +
                # tenant_id to identify "this" crossing.
                budget_subject = {}
                if budget_threshold_enabled:
                    bands = await get_threshold_bands(db, "BUDGET_THRESHOLD")
                    # Only the HIGHEST band this debit newly crossed, not every
                    # one of them — a jump from 59% straight to 82% (bands
                    # 70/80/90) must send exactly one email, for 80, not two
                    # (70 then 80). The ledger's dedup (check_and_record_
                    # threshold) only compares "does this new value differ
                    # from what's stored" — it has no notion of "highest" on
                    # its own, so calling it once per crossed band (ascending)
                    # would fire once per band in the same message. Design doc
                    # §6 Pattern 1 and this function's own docstring already
                    # describe "highest band reached" as the intended
                    # behaviour; this is what actually makes that true.
                    crossed = crossed_bands(pre_pct, post_pct, bands)
                    if crossed:
                        band = max(crossed)
                        fired = await check_and_record_threshold(
                            db, "BUDGET_THRESHOLD", str(ctx.tenant_id), budget_subject, band
                        )
                        if fired:
                            alert_at = datetime.now(timezone.utc)
                            recipients = await _resolve_recipients(db, auth_db, "BUDGET_THRESHOLD", ctx.tenant_id)
                            publish_notification_event(
                                event_name="BUDGET_THRESHOLD",
                                tenant_id=str(ctx.tenant_id),
                                subject=budget_subject,
                                details=[
                                    str(band),
                                    _alert_datetime_ist(alert_at),
                                    f"{_display_pct(post_pct):.0f}%",
                                ],
                                occurred_at=alert_at.isoformat(),
                                recipients=recipients,
                            )
                if budget_exhausted_enabled and crossed_exhaustion(pre_pct, post_pct):
                    # budget_snap (the ceiling) in the exhaustion subject too:
                    # it moves whenever the tenant's pooled key allocations
                    # change (a budget top-up/top-down, or a key/Application
                    # being added, resized or revoked — see
                    # fetch_tenant_budget_status), so a change in that
                    # ceiling gets its own row instead of colliding with the
                    # already-recorded True from before the change —
                    # without this, re-exhausting after a top-up would never
                    # re-fire, since the same {value: True} would already be
                    # stored.
                    budget_exhaustion_subject = {"budget_snap": str(tenant_budget.snap)}
                    fired = await check_and_record_exhaustion(
                        db, "BUDGET_EXHAUSTED", str(ctx.tenant_id), budget_exhaustion_subject
                    )
                    if fired:
                        recipients = await _resolve_recipients(db, auth_db, "BUDGET_EXHAUSTED", ctx.tenant_id)
                        publish_notification_event(
                            event_name="BUDGET_EXHAUSTED",
                            tenant_id=str(ctx.tenant_id),
                            subject=budget_exhaustion_subject,
                            details=["INR", str(tenant_budget.snap)],
                            recipients=recipients,
                        )

    if write.quota_recorded and write.quota_used is not None and write.quota_snap is not None:
        post_pct = percent(write.quota_used, write.quota_snap)
        pre_pct = percent(write.quota_used - billed_units, write.quota_snap)
        if post_pct is not None and pre_pct is not None:
            subject = {"model_task_type": inference_name}
            if await is_notification_enabled(db, "QUOTA_THRESHOLD", str(ctx.tenant_id)):
                bands = await get_threshold_bands(db, "QUOTA_THRESHOLD")
                # Same "highest band only" fix as BUDGET_THRESHOLD above —
                # see that block's comment for why.
                crossed = crossed_bands(pre_pct, post_pct, bands)
                if crossed:
                    band = max(crossed)
                    fired = await check_and_record_threshold(db, "QUOTA_THRESHOLD", str(ctx.tenant_id), subject, band)
                    if fired:
                        alert_at = datetime.now(timezone.utc)
                        recipients = await _resolve_recipients(db, auth_db, "QUOTA_THRESHOLD", ctx.tenant_id)
                        publish_notification_event(
                            event_name="QUOTA_THRESHOLD",
                            tenant_id=str(ctx.tenant_id),
                            subject=subject,
                            details=[
                                str(band),
                                _alert_datetime_ist(alert_at),
                                f"{_display_pct(post_pct):.0f}% ({inference_name.upper()})",
                            ],
                            occurred_at=alert_at.isoformat(),
                            recipients=recipients,
                        )
            if crossed_exhaustion(pre_pct, post_pct) and await is_notification_enabled(
                db, "QUOTA_EXHAUSTED", str(ctx.tenant_id)
            ):
                # billing_month in the exhaustion subject: quota resets at
                # the start of each month (design doc §6.4's epoch
                # semantics for quota rows), so October's exhaustion must
                # not collide with the {value: True} September already
                # recorded — otherwise re-exhausting next month would
                # never re-fire.
                quota_exhaustion_subject = {**subject, "billing_month": ctx.billing_month}
                fired = await check_and_record_exhaustion(
                    db, "QUOTA_EXHAUSTED", str(ctx.tenant_id), quota_exhaustion_subject
                )
                if fired:
                    tier_name = await _fetch_tier_name(db, write.tier_id)
                    reset_date = _first_of_next_month(ctx.billing_month)
                    recipients = await _resolve_recipients(db, auth_db, "QUOTA_EXHAUSTED", ctx.tenant_id)
                    publish_notification_event(
                        event_name="QUOTA_EXHAUSTED",
                        tenant_id=str(ctx.tenant_id),
                        subject=quota_exhaustion_subject,
                        details=[
                            tier_name,
                            [f"{inference_name.upper()}: Quota Limit {write.quota_snap:,.0f}, Resets on {reset_date}"],
                        ],
                        recipients=recipients,
                    )


async def _bill_usage(db, ctx: BillingContext) -> Optional[BillingOutcome]:
    pricing: ServicePricing | None = await get_service_pricing(db, ctx.service_id)
    if pricing is None:
        logger.warning(
            "No pricing found for service_id=%s — skipping billing for tenant=%s",
            ctx.service_id, ctx.tenant_id,
        )
        return None

    logger.debug(
        "Pricing resolved | service_id=%s task_type=%r"
        " unit_rate=%s cost_per_unit=%s unit_size=%s",
        ctx.service_id, pricing.task_type,
        pricing.unit_rate, pricing.cost_per_unit, pricing.unit_size,
    )

    # Only llm bills on input+output (real prompt/completion tokens from the
    # model's own API response). Every other inference type is input-only —
    # output_tokens is still recorded on the span for trace/observability
    # purposes, but must not count toward cost or quota here. task_type is
    # sourced from mm_services (via get_service_pricing), so it must be
    # configured correctly on the service for billing to be accurate.
    billed_units = Decimal(str(ctx.total_tokens if pricing.task_type.lower() == "llm" else ctx.input_tokens))

    cost = calculate_cost(billed_units, pricing)
    if cost == 0:
        logger.warning(
            "Zero cost for service_id=%s — skipping billing for tenant=%s"
            " (unit_rate=%s cost_per_unit=%s unit_size=%s)",
            ctx.service_id, ctx.tenant_id,
            pricing.unit_rate, pricing.cost_per_unit, pricing.unit_size,
        )
        return None

    logger.debug("Cost calculated | tenant=%s cost=%s billed_units=%s", ctx.tenant_id, cost, billed_units)

    # Fused single round-trip: balance deduction + quota upsert (see
    # deduct_balance_and_update_quota's docstring). It can't tell "task_type
    # unset" apart from "genuinely not entitled" on its own — both look like
    # zero matching ppu_tier_quotas rows to it — so that distinction is
    # applied here instead, same as the old _check_quota's early return.
    # The quota upsert joins and conflicts on this id, so
    # an unresolved name means no quota row is written at all — handled below by
    # failing open rather than by reading that as exhaustion.
    inference_type_id = await get_inference_type_id(db, pricing.task_type)
    if pricing.task_type and inference_type_id is None:
        logger.error(
            "Task type %r is not in the inference_types catalogue — quota NOT "
            "enforced for tenant=%s service=%s. Add it via POST /inference-types.",
            pricing.task_type, ctx.tenant_id, ctx.service_id,
            extra={
                "event": "ppu.inference_type.unresolved",
                "task_type": pricing.task_type,
                "tenant_id": ctx.tenant_id,
                "service_id": ctx.service_id,
            },
        )

    write = await deduct_balance_and_update_quota(
        db,
        tenant_id=ctx.tenant_id,
        billing_month=ctx.billing_month,
        units=billed_units,
        cost=cost,
        api_key_id=ctx.api_key_id,
        tier_id=ctx.tier_id,
        inference_type_id=inference_type_id,
    )

    if write.tier_id is None:
        # deduct_balance_and_update_quota already logged the warning; no
        # active assignment means nothing was written to either table. The
        # tenant can't be served this tasktype right now — mark quota (not
        # wallet) exhausted so quota_guard blocks further requests, the same
        # signal used for any other quota-exhausted case.
        wallet_exhausted = False
        quota_exhausted = True
    else:
        logger.debug(
            "Balance deducted | tenant=%s tier_id=%s budget_used=%s exhausted=%s",
            ctx.tenant_id, write.tier_id, write.api_key_budget_used, write.budget_exhausted,
        )
        wallet_exhausted = write.budget_exhausted

        if not pricing.task_type or inference_type_id is None:
            # Two ways to get here, both "we cannot judge this tenant's quota":
            # the service has no task_type configured, or its task_type is not in
            # the catalogue. Fail OPEN. Reading the absent quota row as
            # exhaustion would 429 every tenant on an otherwise-working tier,
            # which is the regression this branch exists to prevent. The budget
            # deduction above still ran, so nothing is billed for free — only the
            # quota ceiling goes unenforced, and the ERROR above says so.
            logger.debug(
                "Quota update skipped | tenant=%s tier_id=%s task_type=%r type_id=%s",
                ctx.tenant_id, write.tier_id, pricing.task_type, inference_type_id,
            )
            quota_exhausted = False
        elif write.quota_recorded:
            logger.debug(
                "Quota usage upserted | tenant=%s inference=%s billing_month=%s"
                " units=%s quota_exhausted=%s",
                ctx.tenant_id, pricing.task_type, ctx.billing_month, billed_units, write.quota_exhausted,
            )
            quota_exhausted = write.quota_exhausted
        else:
            logger.debug(
                "Quota check: tasktype not mapped to tier | tenant=%s tier_id=%s"
                " inference=%s quota_exhausted=%s",
                ctx.tenant_id, write.tier_id, pricing.task_type, write.quota_exhausted,
            )
            quota_exhausted = write.quota_exhausted

    # Commit DB changes before any HTTP calls to avoid holding row locks
    # across slow or failing auth-service requests. A no-op (no rows touched)
    # when write.tier_id was None above.
    await db.commit()
    logger.debug("DB commit successful | tenant=%s offset=%d", ctx.tenant_id, ctx.offset)

    # Both are in-memory cache reads (notification_settings_cache) — cheap
    # to check before deciding whether the second, named "auth" connection
    # is worth opening at all. fetch_tenant_budget_status reads
    # tenants.allocated_budget and this tenant's api_key ids from
    # ai4iplatform_auth for the BUDGET side; recipient resolution
    # (ai4i_core.kafka.recipients — this tenant's ADMIN/TENANT ADMIN users)
    # needs it for EVERY event now, including QUOTA_THRESHOLD/QUOTA_EXHAUSTED,
    # so it's also opened whenever a quota row was even written, not just
    # when a BUDGET flag is on.
    budget_threshold_enabled = await is_notification_enabled(db, "BUDGET_THRESHOLD", str(ctx.tenant_id))
    budget_exhausted_enabled = await is_notification_enabled(db, "BUDGET_EXHAUSTED", str(ctx.tenant_id))
    if budget_threshold_enabled or budget_exhausted_enabled or write.quota_recorded:
        async with session_scope(name="auth") as auth_db:
            await _publish_usage_crossing_events(
                db, auth_db, ctx, write, cost, billed_units, pricing.task_type,
                budget_threshold_enabled, budget_exhausted_enabled,
            )
    else:
        await _publish_usage_crossing_events(
            db, None, ctx, write, cost, billed_units, pricing.task_type,
            budget_threshold_enabled, budget_exhausted_enabled,
        )

    return BillingOutcome(
        pricing=pricing,
        billed_units=billed_units,
        cost=cost,
        wallet_exhausted=wallet_exhausted,
        quota_exhausted=quota_exhausted,
    )


async def handle_ppu_usage(msg: Message) -> None:
    ctx = await _prepare_billing_context(msg)
    if ctx is None:
        return

    async with session_scope() as db:
        outcome = await _bill_usage(db, ctx)

    if outcome is None:
        return

    # Mark span as billed in Redis after DB commit so a crash before this point
    # causes a retry (over-billing risk) rather than silent data loss. Marked
    # unconditionally (including the no-tier case in _bill_usage) so a Kafka
    # redelivery of the same span doesn't re-fire the auth-service notification.
    await _update_billing_on_cache(ctx.is_already_billed, ctx.billed_key, ctx.correlation_id)

    logger.info(
        "Billing applied | tenant=%s service=%s billed_units=%s cost=%s exhausted=%s",
        ctx.tenant_id, ctx.service_id, outcome.billed_units, outcome.cost, outcome.wallet_exhausted,
    )
    await _post_billing(
        outcome.wallet_exhausted, outcome.quota_exhausted, ctx.tenant_id, ctx.api_key_id, outcome.pricing.task_type
    )


_NOTIFY_AUTH_MAX_ATTEMPTS = 3
_NOTIFY_AUTH_BACKOFF_BASE_S = 0.5
# Full per-attempt timeout: the quota-exhausted path (set_quota_exhausted_for_tenant)
# is not a constant-time flag write — it walks every key in the tenant — so a
# large tenant genuinely needs the whole 5s, and an attempt timing out doesn't
# mean the write itself failed (it may land after we've moved on). The
# budget-exhausted path is now per-key (set_budget_exhausted_for_key) and
# doesn't need this, but both share the same call path. Shortening this would
# time out attempts that were about to succeed and just relabel that as
# "enforcement flag NOT set". Bound the *total* time some other way (see
# _NOTIFY_AUTH_DEADLINE_S) instead of starving individual attempts.
_NOTIFY_AUTH_TIMEOUT_S = 5.0
# Overall deadline across all attempts of one _notify_auth call, checked only
# between attempts (never mid-flight, so an in-progress attempt always keeps
# its full 5s). main.py's consumer processes one message at a time, and
# _post_billing can call this twice (wallet + quota) — without a cap, 3 slow
# (5s) attempts x2 calls would hold that single message for 33s. This bounds
# a slow-auth-service run to ~2 attempts (~10.5s) per call; a fast-failing
# one (connection refused, etc.) still gets all 3 attempts, since that only
# costs ~1.5s of backoff.
_NOTIFY_AUTH_DEADLINE_S = 10.0


async def _notify_auth(path: str, body: dict) -> None:
    """POST to auth-service internal endpoint to update API key Redis flags.

    Retries transport errors and 5xx/429 responses with exponential backoff
    (0.5s/1s) — this call is the only thing that flips /auth/validate's
    budget/quota-exhausted Redis flag (see routes/validation.py::
    _validate_api_key). A 4xx other than 429 (e.g. a malformed tenant_id,
    see app/routes/internal.py) is a permanent misconfiguration, not a
    transient failure, so it fails fast instead of burning the whole retry
    budget on something that can never succeed.

    This narrows the enforcement gap, it doesn't close it: whichever way
    this gives up — retries exhausted, deadline spent, or a permanent
    rejection — the flag stays unset. By then the span is already marked
    billed in Redis (see handle_ppu_usage), so a Kafka redelivery of *this*
    span won't re-fire the notification — recovery still depends on this
    tenant's next billed request re-triggering it. A durable fix (a
    persisted outbox retried by a background job, or a periodic
    reconciliation job comparing wallet balances to Redis flags) is tracked
    as separate follow-up work, not attempted here.

    One AsyncClient is reused across attempts (shared connection pool)
    rather than opened fresh per attempt.
    """
    url = f"{cfg.get_settings().AUTH_SERVICE_URL}{path}"
    deadline = asyncio.get_running_loop().time() + _NOTIFY_AUTH_DEADLINE_S
    async with httpx.AsyncClient(timeout=_NOTIFY_AUTH_TIMEOUT_S) as client:
        for attempt in range(1, _NOTIFY_AUTH_MAX_ATTEMPTS + 1):
            try:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                return
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status < 500 and status != 429:
                    # Alert-worthy, same phrasing as the exhausted-retries path below:
                    # this is the worse of the two give-up modes — it fails identically
                    # on every attempt, so it never self-heals the way a transient
                    # failure does (a later billed request naturally retries that one).
                    logger.error(
                        "auth-service rejected notification with permanent %d error — "
                        "budget/quota enforcement flag NOT set | url=%s body=%s",
                        status, url, body,
                    )
                    return
                last_exc = exc
            except Exception as exc:
                last_exc = exc

            if attempt == _NOTIFY_AUTH_MAX_ATTEMPTS or asyncio.get_running_loop().time() >= deadline:
                # Log and continue — billing event must not fail over a notification
                # error. Alert-worthy: the exhaustion flag was NOT set, so enforcement
                # for this tenant silently lapses until their next billed request.
                logger.error(
                    "Failed to notify auth-service after %d attempt(s) — budget/quota "
                    "enforcement flag NOT set | url=%s body=%s error=%s",
                    attempt, url, body, last_exc,
                )
                return
            logger.warning(
                "auth-service notify failed, retrying (attempt %d/%d) | url=%s error=%s",
                attempt, _NOTIFY_AUTH_MAX_ATTEMPTS, url, last_exc,
            )
            await asyncio.sleep(_NOTIFY_AUTH_BACKOFF_BASE_S * (2 ** (attempt - 1)))
