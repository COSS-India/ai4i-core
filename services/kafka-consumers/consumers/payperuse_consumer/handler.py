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
    BandItem,
    FailureCode,
    FailureStage,
    FireContext,
    Measurement,
    NotificationName,
    Operation,
    ThresholdUnit,
    budget_subject,
    emit_band_batch,
    format_amount,
    get_notification_runtime,
    names_that_can_fire,
    notifications_configured,
    quota_subject,
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
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD's "when the alert fired" value,
    already formatted for display — e.g. "28 Sep 2026, 03:45 PM IST" — so
    the consumer never has to parse or convert occurred_at itself."""
    return dt.astimezone(_IST).strftime("%d %b %Y, %I:%M %p") + " IST"


def _display_pct(pct: Decimal) -> Decimal:
    """Clamp a usage percentage to 100 for DISPLAY only (design doc §9.5's
    QUOTA_THRESHOLD/BUDGET_THRESHOLD current_value). A single debit can push
    used past snap (e.g. concurrent requests racing past the ceiling before
    either sees the other's write), so the raw percent can read well over
    100 — "2900%" in an alert email reads as a bug, not "you're very over
    budget". The pipeline still evaluates the raw, uncapped value."""
    return min(pct, Decimal(100))


def percent(used: Optional[Decimal], snap: Optional[Decimal]) -> Optional[Decimal]:
    """used/snap as a 0-100 percentage; None when there's no ceiling to
    measure against (unlimited/no row)."""
    if used is None or snap is None or snap == 0:
        return None
    return (used / snap) * 100


def _band_text(value: Decimal) -> str:
    return f"{value.normalize():f}"


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
    """Q-D3: tier name for QUOTA_EXHAUSTED's details[0]; the raw id when the
    tier row is gone. A failing query raises, so the pipeline sends the
    fallback details and writes a DETAILS_PARTIAL row."""
    if tier_id is None:
        return ""
    row = (await db.execute(text("SELECT name FROM tiers WHERE id = CAST(:tid AS uuid)"), {"tid": tier_id})).first()
    return row.name if row is not None else tier_id


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


_BUDGET_NAMES = (NotificationName.BUDGET_THRESHOLD, NotificationName.BUDGET_EXHAUSTED)
_QUOTA_NAMES = (NotificationName.QUOTA_THRESHOLD, NotificationName.QUOTA_EXHAUSTED)


def _threshold_details(suffix: str = ""):
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD: [band, alert time IST, current %]."""
    def build(context: FireContext) -> list:
        return [
            _band_text(context.band.value),
            _alert_datetime_ist(context.occurred_at),
            f"{_display_pct(context.observed.value):.0f}%{suffix}",
        ]
    return build


def _quota_limit_line(inference_name: str, quota_snap: Decimal, billing_month: str) -> str:
    return f"{inference_name.upper()}: Quota Limit {quota_snap:,.0f}, Resets on {_first_of_next_month(billing_month)}"


def _quota_exhausted_details(db, tier_id: Optional[str], inference_name: str, quota_snap: Decimal, billing_month: str):
    """QUOTA_EXHAUSTED: [tier name, ["ASR: Quota Limit 1,000, Resets on YYYY-MM-01"]]."""
    async def build(context: FireContext) -> list:
        tier_name = await _fetch_tier_name(db, tier_id)
        return [tier_name, [_quota_limit_line(inference_name, quota_snap, billing_month)]]
    return build


async def _budget_items(ctx: BillingContext, core_db) -> list[BandItem]:
    """BUDGET_THRESHOLD/BUDGET_EXHAUSTED on the tenant's pooled budget
    (tenant-level, never one API key's own allocation). The budget position
    is two cross-database queries, so it is read only when one of the two
    could actually fire for this tenant (enabled, bands, someone assigned)."""
    names = await names_that_can_fire(_BUDGET_NAMES, ctx.tenant_id)
    if not names:
        return []
    try:
        async with session_scope(name="auth") as auth_db:
            tenant_budget = await fetch_tenant_budget_status(auth_db, core_db, str(ctx.tenant_id))
    except Exception as exc:
        # Never into billing: the span is already committed, and a raise
        # here would retry (and re-bill) it.
        for name in names:
            await get_notification_runtime().failures.record(
                FailureStage.SOURCE, FailureCode.TENANT_LOOKUP_FAILED, notification_name=name,
                tenant_id=str(ctx.tenant_id), operation=Operation.TENANT_LOOKUP, error=exc,
            )
        return []
    if tenant_budget is None or tenant_budget.snap is None:
        return []
    observed = percent(tenant_budget.used, tenant_budget.snap)
    if observed is None:
        return []
    measurement = Measurement(value=observed, unit=ThresholdUnit.PERCENT)
    subject = budget_subject(tenant_budget.snap, tenant_budget.effective_from, tenant_budget.effective_to)
    details = {
        NotificationName.BUDGET_THRESHOLD: _threshold_details(),
        NotificationName.BUDGET_EXHAUSTED: lambda _: ["INR", format_amount(tenant_budget.snap)],
    }
    return [
        BandItem(name=name, tenant_id=str(ctx.tenant_id), subject=subject, observed=measurement, details=details[name])
        for name in names
    ]


def _quota_items(db, ctx: BillingContext, write: BillingWriteResult, inference_name: str) -> list[BandItem]:
    """QUOTA_THRESHOLD/QUOTA_EXHAUSTED on this month's quota row for the
    task type; billing_month in the subject makes each month its own
    ledger row."""
    if not (write.quota_recorded and inference_name):
        return []
    observed = percent(write.quota_used, write.quota_snap)
    if observed is None:
        return []
    measurement = Measurement(value=observed, unit=ThresholdUnit.PERCENT)
    subject = quota_subject(ctx.billing_month, inference_name)
    details = {
        NotificationName.QUOTA_THRESHOLD: _threshold_details(f" ({inference_name.upper()})"),
        NotificationName.QUOTA_EXHAUSTED: _quota_exhausted_details(
            db, write.tier_id, inference_name, write.quota_snap, ctx.billing_month
        ),
    }
    fallback = {
        NotificationName.QUOTA_EXHAUSTED: (
            write.tier_id or "", [_quota_limit_line(inference_name, write.quota_snap, ctx.billing_month)]
        ),
    }
    return [
        BandItem(
            name=name, tenant_id=str(ctx.tenant_id), subject=subject, observed=measurement,
            details=details[name], fallback_details=fallback.get(name, ()),
        )
        for name in _QUOTA_NAMES
    ]


async def _publish_usage_crossing_events(
    db, ctx: BillingContext, write: BillingWriteResult, inference_name: str,
) -> None:
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD/QUOTA_EXHAUSTED/BUDGET_EXHAUSTED —
    after the billing commit, per message. The shared pipeline
    (ai4i_core.kafka.emit_band_batch) owns the gate, the BAND dedup (highest
    band reached per ledger row, claimed atomically), recipients and the
    publish; it never raises into billing — every failure is a
    notification_alert_failure_log row.

    Only the post-debit value is evaluated: the ledger remembers the band
    already sent, so a jump from 59% to 82% (bands 70/80/90) sends exactly
    one email, for 80, and no pre-debit value is needed.

    Both BUDGET and QUOTA are tenant-level events. This is distinct from the
    per-key budget-exhausted ENFORCEMENT flag _post_billing pushes to
    auth-service, which blocks one key's own requests once its own
    allocation runs out."""
    if not notifications_configured():
        return
    items = await _budget_items(ctx, db) + _quota_items(db, ctx, write, inference_name)
    if items:
        await emit_band_batch(items)


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

    await _publish_usage_crossing_events(db, ctx, write, pricing.task_type)

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
