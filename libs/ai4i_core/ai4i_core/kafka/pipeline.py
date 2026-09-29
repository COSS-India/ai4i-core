"""The shared producer pipeline: validate, settings, gate, evaluate, details,
claim, recipients, publish.

* emit_state — one STATE event (admin actions: tier and budget).
* emit_state_bulk — a STATE fan-out claimed in one statement (QUOTA_LIMIT_UPDATED).
* emit_band_batch — BAND evaluations of one request or tick (usage and
  monitoring alerts): one cache read, then claims only for FIRE and RESET.
* refresh_settings / refresh_subscriptions — writers, after their commit.

Nothing here raises into the caller; every failure is a failure-log row.
"""

import inspect
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from . import metrics
from .bands import band_for
from .cache import CacheRead
from .constants import (
    PLATFORM_TENANT_ID,
    Decision,
    FailureCode,
    FailureStage,
    NotificationName,
    NotificationScope,
    NotificationType,
    Operation,
    Severity,
)
from .keys import InvalidSubject, state_hash, utc_now, validate_subject
from .ledger import StateClaim, claim_band, claim_state, claim_state_bulk, decide, reread, reset_band
from .models import Band, LedgerRef, LedgerState, Measurement, Recipient, SettingsRow, TenantSubscriptions
from .publisher import Envelope
from .runtime import NotificationRuntime, get_runtime
from .settings import load_settings_snapshot, load_subscriptions_many
from .specs import NotificationSpec, get_spec

logger = logging.getLogger(__name__)

Details = Sequence[Any]
DetailsLoader = Callable[[], Union[Details, Awaitable[Details]]]


@dataclass(frozen=True)
class StateItem:
    """One pair of a STATE fan-out (emit_state_bulk)."""

    tenant_id: str
    subject: Mapping[str, str]
    new_state: Mapping[str, Any]
    details: Details
    tenant_name: Optional[str] = None


@dataclass(frozen=True)
class FireContext:
    """What a BAND item's details builder gets when its band fires."""

    name: NotificationName
    tenant_id: str
    subject: Mapping[str, str]
    band: Band
    observed: Measurement
    occurred_at: datetime


@dataclass(frozen=True)
class BandItem:
    """One BAND evaluation (emit_band_batch). details builds the email's
    positional values when the band fires."""

    name: NotificationName
    tenant_id: str
    subject: Mapping[str, str]
    observed: Measurement
    details: Optional[Callable[[FireContext], Union[Details, Awaitable[Details]]]] = None
    fallback_details: Details = ()


def _name_text(name) -> str:
    return name.value if hasattr(name, "value") else str(name)


def _decision(name, decision: Decision, n: int = 1) -> None:
    if n:
        metrics.DECISIONS.labels(_name_text(name), decision.value).inc(n)


def _enabled(row: SettingsRow, subs: Optional[TenantSubscriptions]) -> bool:
    if row.scope is NotificationScope.GLOBAL:
        return True
    return subs is not None and subs.entry(row.name).subscribed


def _gate_needs_subscription(row: SettingsRow) -> bool:
    """INSTITUTION rows need `subscribed`; a row with no role flag needs the
    tenant's extra recipients to know whether anyone is assigned."""
    if row.type is NotificationType.MONITORING:
        return False
    return row.scope is NotificationScope.INSTITUTION or not row.any_role_enabled()


def _someone_assigned(row: SettingsRow, subs: Optional[TenantSubscriptions]) -> bool:
    """A role flag is on, or the tenant listed extra recipients. Monitoring
    rows need a selected role; its users are resolved at send time."""
    if row.type is NotificationType.MONITORING:
        return row.any_role_enabled()
    return row.any_role_enabled() or bool(subs is not None and subs.entry(row.name).recipients)


async def _details(
    rt: NotificationRuntime, loader, argument, fallback: Details, *, name, row_id, tenant_id, subject
) -> List[Any]:
    """Best effort: a failing lookup uses the fallback and writes DETAILS_PARTIAL."""
    if loader is None:
        return list(fallback)
    if not callable(loader):
        return list(loader)
    try:
        value = loader(argument) if argument is not None else loader()
        if inspect.isawaitable(value):
            value = await value
        return list(value)
    except Exception as exc:
        await rt.failures.record(
            FailureStage.DETAILS, FailureCode.DETAILS_PARTIAL, notification_name=name, notification_id=row_id,
            tenant_id=tenant_id, subject=subject, operation=Operation.DETAILS_LOOKUP, error=exc,
        )
        return list(fallback)


async def _deliver(
    rt: NotificationRuntime,
    row: SettingsRow,
    *,
    tenant_id: str,
    subject: Mapping[str, str],
    event_id: uuid.UUID,
    occurred_at: datetime,
    details: Details,
    severity: Severity,
    band: Optional[Band] = None,
    observed: Optional[Measurement] = None,
    extra_user_ids: Sequence[str] = (),
    state_hash_value: Optional[str] = None,
    recipients: Optional[List[Recipient]] = None,
    tenant_name: Optional[str] = None,
) -> Optional[uuid.UUID]:
    """Recipients (unless given), then publish. The claim is already made."""
    failure = dict(
        notification_name=row.name, notification_id=row.id, tenant_id=tenant_id, subject=subject,
        event_id=event_id, state_hash=state_hash_value,
        observed=observed.to_json() if observed else None, band=band.value_unit() if band else None,
    )
    if recipients is None:
        try:
            async with rt.auth_session_factory() as session:
                if row.type is NotificationType.MONITORING:
                    recipients = await rt.recipients.for_roles(session, row.enabled_roles())
                else:
                    recipients, resolved_name = await rt.recipients.for_tenant(
                        session, tenant_id, row.recipient_roles, extra_user_ids
                    )
                    tenant_name = tenant_name or resolved_name
        except Exception as exc:
            await rt.failures.record(
                FailureStage.RECIPIENTS, FailureCode.RECIPIENTS_LOOKUP_FAILED,
                operation=Operation.RECIPIENTS_LOOKUP, error=exc, **failure,
            )
            return None
    if not recipients:
        await rt.failures.record(
            FailureStage.RECIPIENTS, FailureCode.NO_RECIPIENTS, operation=Operation.RECIPIENTS_LOOKUP,
            message="no active user matches the selected recipients", **failure,
        )
        return None
    envelope = Envelope(
        event_id=event_id,
        event_name=row.name,
        notification_type=row.type,
        tenant_id=tenant_id,
        tenant_name=None if row.type is NotificationType.MONITORING else tenant_name,
        subject=dict(subject),
        occurred_at=occurred_at,
        channels=row.channels,
        severity=severity,
        details=list(details),
        recipients=recipients,
        band=band,
        observed=observed,
        state_hash=state_hash_value,
    )
    sent = await rt.publisher.send(envelope, notification_id=row.id)
    return event_id if sent else None


# ── STATE ────────────────────────────────────────────────────────────────────


async def _validate(rt, name, tenant_id, subject, *, expect_state: bool) -> Tuple[Optional[NotificationSpec], Optional[Dict[str, str]]]:
    spec = get_spec(name)
    if spec is None or spec.is_state != expect_state:
        await rt.failures.record(
            FailureStage.VALIDATION, FailureCode.UNKNOWN_NOTIFICATION, notification_name=_name_text(name),
            tenant_id=tenant_id, operation=Operation.VALIDATE,
            message=f"{_name_text(name)!r} is not a known {'STATE' if expect_state else 'BAND'} notification",
        )
        return None, None
    try:
        if not str(tenant_id or "").strip():
            raise InvalidSubject("tenant id is empty")
        return spec, validate_subject(spec, subject)
    except InvalidSubject as exc:
        await rt.failures.record(
            FailureStage.VALIDATION, FailureCode.INVALID_SUBJECT, notification_name=spec.name, tenant_id=tenant_id,
            subject=subject if isinstance(subject, Mapping) else None, operation=Operation.VALIDATE, error=exc,
        )
        return spec, None


async def _settings_row(rt, read: CacheRead, spec: NotificationSpec, *, tenant_id=None, state_hash_value=None, message=None) -> Optional[SettingsRow]:
    if read.settings is None:
        await rt.failures.record(
            FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, notification_name=spec.name,
            tenant_id=tenant_id, operation=Operation.SETTINGS_FILL, error=read.settings_error,
            message=message, state_hash=state_hash_value,
        )
        return None
    row = read.settings.get(spec.name)
    if row is None:
        await rt.failures.record(
            FailureStage.VALIDATION, FailureCode.UNKNOWN_NOTIFICATION, notification_name=spec.name,
            tenant_id=tenant_id, operation=Operation.VALIDATE,
            message=f"{spec.name.value} is not in configs_notification_alert",
        )
    return row


async def emit_state(
    name,
    tenant_id: str,
    new_state: Mapping[str, Any],
    *,
    subject: Optional[Mapping[str, str]] = None,
    details: Union[Details, DetailsLoader, None] = None,
    fallback_details: Details = (),
) -> Optional[uuid.UUID]:
    """One STATE event, after the business change committed. Returns the
    event_id when it was handed to Kafka, else None (skipped, duplicate or
    failed — failures are in the failure log)."""
    rt = get_runtime()
    spec, subject = await _validate(rt, name, tenant_id, subject or {}, expect_state=True)
    if subject is None:
        return None
    tenant_id = str(tenant_id)
    fingerprint = state_hash(new_state)

    read = await rt.cache.read(tenant_ids=[tenant_id], context_name=spec.name)
    row = await _settings_row(rt, read, spec, tenant_id=tenant_id, state_hash_value=fingerprint)
    if row is None:
        return None
    subs = read.subscriptions.get(tenant_id)
    if subs is None:
        await rt.failures.record(
            FailureStage.SUBSCRIPTION, FailureCode.SUBSCRIPTION_UNAVAILABLE, notification_name=spec.name,
            notification_id=row.id, tenant_id=tenant_id, subject=subject, operation=Operation.SUBSCRIPTION_FILL,
            error=read.subscription_error, state_hash=fingerprint,
        )
        return None
    if not (_enabled(row, subs) and _someone_assigned(row, subs)):
        _decision(spec.name, Decision.SKIP)
        return None

    event_id = uuid.uuid4()
    occurred_at = utc_now()
    values = await _details(
        rt, details, None, fallback_details, name=spec.name, row_id=row.id, tenant_id=tenant_id, subject=subject
    )
    try:
        async with rt.core_session_factory() as session:
            won = await claim_state(session, row.id, tenant_id, subject, fingerprint, event_id)
            await session.commit()
    except Exception as exc:
        await rt.failures.record(
            FailureStage.LEDGER, FailureCode.LEDGER_WRITE_FAILED, notification_name=spec.name,
            notification_id=row.id, tenant_id=tenant_id, subject=subject,
            operation=Operation.LEDGER_CLAIM_STATE, error=exc, state_hash=fingerprint,
        )
        return None
    if not won:
        _decision(spec.name, Decision.DUPLICATE)
        return None
    _decision(spec.name, Decision.FIRE)
    return await _deliver(
        rt, row, tenant_id=tenant_id, subject=subject, event_id=event_id, occurred_at=occurred_at,
        details=values, severity=Severity.INFO, extra_user_ids=subs.entry(spec.name).recipients,
        state_hash_value=fingerprint,
    )


async def emit_state_bulk(name, items: Sequence[StateItem], *, summary: str = "") -> List[uuid.UUID]:
    """A STATE fan-out (every tenant x changed task type): one cache read,
    one bulk claim (Q-L5), one recipient query (Q-R2). `summary` (e.g. the
    tier id and change list) is the message of a failure row that covers the
    whole fan-out. Returns the event ids handed to Kafka."""
    rt = get_runtime()
    spec = get_spec(name)
    if spec is None or not spec.is_state:
        await _validate(rt, name, None, {}, expect_state=True)
        return []

    valid: List[Tuple[StateItem, Dict[str, str]]] = []
    for item in items:
        _, subject = await _validate(rt, spec.name, item.tenant_id, item.subject, expect_state=True)
        if subject is not None:
            valid.append((item, subject))
    if not valid:
        return []

    tenants = list(dict.fromkeys(str(item.tenant_id) for item, _ in valid))
    read = await rt.cache.read(tenant_ids=tenants, context_name=spec.name)
    row = await _settings_row(rt, read, spec, message=summary or None)
    if row is None:
        return []
    if read.subscription_error is not None and any(t not in read.subscriptions for t in tenants):
        await rt.failures.record(
            FailureStage.SUBSCRIPTION, FailureCode.SUBSCRIPTION_UNAVAILABLE, notification_name=spec.name,
            notification_id=row.id, operation=Operation.SUBSCRIPTION_FILL, error=read.subscription_error,
            message=summary or None,
        )
        return []

    claims: List[StateClaim] = []
    by_event: Dict[uuid.UUID, StateItem] = {}
    for item, subject in valid:
        subs = read.subscriptions.get(str(item.tenant_id))
        if not (_enabled(row, subs) and _someone_assigned(row, subs)):
            _decision(spec.name, Decision.SKIP)
            continue
        claim = StateClaim(str(item.tenant_id), subject, state_hash(item.new_state), uuid.uuid4())
        claims.append(claim)
        by_event[claim.event_id] = item
    if not claims:
        return []

    occurred_at = utc_now()
    try:
        async with rt.core_session_factory() as session:
            won = await claim_state_bulk(session, row.id, claims)
            await session.commit()
    except Exception as exc:
        await rt.failures.record(
            FailureStage.LEDGER, FailureCode.LEDGER_WRITE_FAILED, notification_name=spec.name,
            notification_id=row.id, operation=Operation.LEDGER_CLAIM_STATE_BULK, error=exc,
            message=summary or None,
        )
        return []
    _decision(spec.name, Decision.DUPLICATE, len(claims) - len(won))
    _decision(spec.name, Decision.FIRE, len(won))
    if not won:
        return []

    fired_tenants = list(dict.fromkeys(claim.tenant_id for claim in won))
    extras = {
        tenant: read.subscriptions[tenant].entry(spec.name).recipients
        for tenant in fired_tenants if tenant in read.subscriptions
    }
    try:
        async with rt.auth_session_factory() as session:
            by_tenant = await rt.recipients.for_tenants(session, fired_tenants, row.recipient_roles, extras)
    except Exception as exc:
        for claim in won:
            await rt.failures.record(
                FailureStage.RECIPIENTS, FailureCode.RECIPIENTS_LOOKUP_FAILED, notification_name=spec.name,
                notification_id=row.id, tenant_id=claim.tenant_id, subject=claim.subject,
                event_id=claim.event_id, operation=Operation.RECIPIENTS_LOOKUP, error=exc,
                state_hash=claim.state_hash,
            )
        return []

    sent: List[uuid.UUID] = []
    for claim in won:
        item = by_event[claim.event_id]
        event_id = await _deliver(
            rt, row, tenant_id=claim.tenant_id, subject=claim.subject, event_id=claim.event_id,
            occurred_at=occurred_at, details=item.details, severity=Severity.INFO,
            state_hash_value=claim.state_hash, recipients=by_tenant.get(claim.tenant_id, []),
            tenant_name=item.tenant_name,
        )
        if event_id is not None:
            sent.append(event_id)
    return sent


# ── BAND ─────────────────────────────────────────────────────────────────────


@dataclass
class _Evaluation:
    item: BandItem
    spec: NotificationSpec
    ref: LedgerRef
    row: Optional[SettingsRow] = None
    subs: Optional[TenantSubscriptions] = None
    band: Optional[Band] = None
    decision: Decision = Decision.SKIP
    event_id: Optional[uuid.UUID] = None
    details: Details = ()


async def emit_band_batch(items: Sequence[BandItem]) -> List[uuid.UUID]:
    """BAND evaluations of one billed span or monitoring tick. One cache read
    for all items (L1, then one Redis pipeline, then one Q-L1); claims only
    for FIRE (Q-L2) and RESET (Q-L3); one Redis pipeline for every ledger
    change; then recipients and publish per fired item. Returns the event
    ids handed to Kafka."""
    rt = get_runtime()
    evaluations: List[_Evaluation] = []
    for item in items:
        spec = get_spec(item.name)
        if spec is not None and spec.platform_scoped:
            tenant_id = PLATFORM_TENANT_ID
        else:
            tenant_id = "" if item.tenant_id is None else str(item.tenant_id)
        spec, subject = await _validate(rt, item.name, tenant_id, item.subject, expect_state=False)
        if subject is None:
            continue
        evaluations.append(_Evaluation(item, spec, LedgerRef.of(spec.name, tenant_id, subject)))
    if not evaluations:
        return []

    # Settings in L1 narrow the read to enabled types (and L1 subscriptions to
    # the gate); the subscription is read only when the gate needs it.
    snapshot = rt.cache.peek_settings()
    if snapshot is not None:
        candidates = []
        tenants = []
        for e in evaluations:
            row = snapshot.get(e.spec.name)
            if row is None or not row.bands:
                continue
            if e.spec.platform_scoped or not _gate_needs_subscription(row):
                subs = None if e.spec.platform_scoped else rt.cache.peek_subscriptions(e.ref.tenant_id)
            else:
                subs = rt.cache.peek_subscriptions(e.ref.tenant_id)
                if subs is None:
                    tenants.append(e.ref.tenant_id)
                    candidates.append(e)
                    continue
            if _enabled(row, subs) and _someone_assigned(row, subs):
                candidates.append(e)
            else:
                _decision(e.spec.name, Decision.SKIP)
        if not candidates:
            return []
    else:
        candidates = evaluations
        tenants = [e.ref.tenant_id for e in candidates if not e.spec.platform_scoped]
    read = await rt.cache.read(
        tenant_ids=tenants, ledger_refs=[e.ref for e in candidates], context_name=evaluations[0].spec.name
    )
    if read.settings is None:
        for name in dict.fromkeys(e.spec.name for e in candidates):
            await rt.failures.record(
                FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, notification_name=name,
                operation=Operation.SETTINGS_FILL, error=read.settings_error,
            )
        return []

    now = utc_now()
    active: List[_Evaluation] = []
    for e in candidates:
        row = read.settings.get(e.spec.name)
        if row is None or not row.bands:
            continue
        subs = None
        if not e.spec.platform_scoped:
            subs = read.subscriptions.get(e.ref.tenant_id) or rt.cache.peek_subscriptions(e.ref.tenant_id)
            if subs is None and _gate_needs_subscription(row):
                await rt.failures.record(
                    FailureStage.SUBSCRIPTION, FailureCode.SUBSCRIPTION_UNAVAILABLE, notification_name=e.spec.name,
                    notification_id=row.id, tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict,
                    operation=Operation.SUBSCRIPTION_FILL, error=read.subscription_error,
                )
                continue
        if not (_enabled(row, subs) and _someone_assigned(row, subs)):
            continue
        state = read.ledger.get(e.ref.key)
        if state is None:
            await rt.failures.record(
                FailureStage.LEDGER, FailureCode.LEDGER_READ_FAILED, notification_name=e.spec.name,
                notification_id=row.id, tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict,
                operation=Operation.LEDGER_READ, error=read.ledger_error,
            )
            continue
        e.row, e.subs = row, subs
        e.band = band_for(e.item.observed.value, row.bands)
        e.decision = decide(e.spec, e.band, state, now, rt.config.notif_monitor_cooldown_s)
        if e.decision in (Decision.FIRE, Decision.RESET):
            active.append(e)
        else:
            _decision(e.spec.name, e.decision)
    if not active:
        return []

    # A FIRE on a GLOBAL row with a role flag did not need the subscription
    # for the gate; its extra recipients are read now, before the claim.
    missing = [e for e in active if e.decision is Decision.FIRE and not e.spec.platform_scoped and e.subs is None]
    if missing:
        subs_read = await rt.cache.read(
            tenant_ids=[e.ref.tenant_id for e in missing], context_name=missing[0].spec.name
        )
        for e in missing:
            e.subs = subs_read.subscriptions.get(e.ref.tenant_id)
            if e.subs is None:
                await rt.failures.record(
                    FailureStage.SUBSCRIPTION, FailureCode.SUBSCRIPTION_UNAVAILABLE, notification_name=e.spec.name,
                    notification_id=e.row.id, tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict,
                    operation=Operation.SUBSCRIPTION_FILL, error=subs_read.subscription_error,
                )
        active = [e for e in active if e.spec.platform_scoped or e.decision is not Decision.FIRE or e.subs is not None]
        if not active:
            return []

    for e in active:
        if e.decision is Decision.FIRE:
            e.event_id = uuid.uuid4()
            context = FireContext(e.spec.name, e.ref.tenant_id, e.ref.subject_dict, e.band, e.item.observed, now)
            e.details = await _details(
                rt, e.item.details, context, e.item.fallback_details, name=e.spec.name, row_id=e.row.id,
                tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict,
            )

    changed: Dict[str, LedgerState] = {}
    refreshed: Dict[str, LedgerState] = {}
    fired: List[_Evaluation] = []
    try:
        async with rt.core_session_factory() as session:
            for e in active:
                try:
                    if e.decision is Decision.FIRE:
                        state = await claim_band(session, e.row.id, e.ref, e.band.value, e.event_id)
                        await session.commit()
                        if state is not None:
                            _decision(e.spec.name, Decision.FIRE)
                            changed[e.ref.key] = state
                            fired.append(e)
                        else:
                            _decision(e.spec.name, Decision.DUPLICATE)
                            refreshed[e.ref.key] = await reread(session, e.row.id, e.ref)
                            await session.commit()
                    else:
                        state = await reset_band(session, e.row.id, e.ref, rt.config.notif_monitor_cooldown_s)
                        await session.commit()
                        if state is not None:
                            _decision(e.spec.name, Decision.RESET)
                            changed[e.ref.key] = state
                        else:
                            # Another pod re-armed or re-fired it: refresh the cache.
                            _decision(e.spec.name, Decision.DUPLICATE)
                            refreshed[e.ref.key] = await reread(session, e.row.id, e.ref)
                            await session.commit()
                except Exception as exc:
                    await session.rollback()
                    await rt.failures.record(
                        FailureStage.LEDGER, FailureCode.LEDGER_WRITE_FAILED, notification_name=e.spec.name,
                        notification_id=e.row.id, tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict,
                        operation=Operation.LEDGER_CLAIM_BAND if e.decision is Decision.FIRE else Operation.LEDGER_RESET,
                        error=exc, observed=e.item.observed.to_json(),
                        band=e.band.value_unit() if e.band else None,
                    )
    except Exception as exc:
        # The session itself could not be opened.
        for e in active:
            if e.ref.key not in changed and e.ref.key not in refreshed:
                await rt.failures.record(
                    FailureStage.LEDGER, FailureCode.LEDGER_WRITE_FAILED, notification_name=e.spec.name,
                    notification_id=e.row.id, tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict,
                    operation=Operation.LEDGER_CLAIM_BAND, error=exc, observed=e.item.observed.to_json(),
                    band=e.band.value_unit() if e.band else None,
                )

    if changed or refreshed:
        names = list(dict.fromkeys(e.spec.name.value for e in active if e.ref.key in changed))
        await rt.cache.write_ledger(changed, refreshed, names)

    sent: List[uuid.UUID] = []
    for e in fired:
        event_id = await _deliver(
            rt, e.row, tenant_id=e.ref.tenant_id, subject=e.ref.subject_dict, event_id=e.event_id,
            occurred_at=now, details=e.details, severity=e.band.severity, band=e.band,
            observed=e.item.observed,
            extra_user_ids=e.subs.entry(e.spec.name).recipients if e.subs is not None else (),
        )
        if event_id is not None:
            sent.append(event_id)
    return sent


async def names_that_can_fire(names: Sequence, tenant_id: str) -> List[NotificationName]:
    """The BAND notifications among `names` that could fire for this tenant
    right now: enabled for it, with active bands and someone assigned. Uses
    the cache only (no ledger read), so a producer can skip computing an
    expensive observed value nobody would receive. The subscription is read
    only when the gate needs it."""
    rt = get_runtime()
    tenant = str(tenant_id)
    specs = [spec for spec in (get_spec(n) for n in names) if spec is not None and spec.is_band]
    if not specs:
        return []
    snapshot = rt.cache.peek_settings()
    needs_subs = any(
        not spec.platform_scoped
        and (snapshot is None or ((row := snapshot.get(spec.name)) is not None and row.bands and _gate_needs_subscription(row)))
        for spec in specs
    )
    read = await rt.cache.read(tenant_ids=[tenant] if needs_subs else [], context_name=specs[0].name)
    if read.settings is None:
        for spec in specs:
            await rt.failures.record(
                FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, notification_name=spec.name,
                tenant_id=tenant, operation=Operation.SETTINGS_FILL, error=read.settings_error,
            )
        return []
    subs = read.subscriptions.get(tenant) or rt.cache.peek_subscriptions(tenant)
    result = []
    for spec in specs:
        row = read.settings.get(spec.name)
        if row is None or not row.bands:
            continue
        row_subs = None if spec.platform_scoped else subs
        if row_subs is None and not spec.platform_scoped and _gate_needs_subscription(row):
            await rt.failures.record(
                FailureStage.SUBSCRIPTION, FailureCode.SUBSCRIPTION_UNAVAILABLE, notification_name=spec.name,
                notification_id=row.id, tenant_id=tenant, operation=Operation.SUBSCRIPTION_FILL,
                error=read.subscription_error,
            )
            continue
        if _enabled(row, row_subs) and _someone_assigned(row, row_subs):
            result.append(spec.name)
    return result


# ── Writers ──────────────────────────────────────────────────────────────────


async def refresh_settings(names: Sequence) -> None:
    """After a catalog commit: rebuild the snapshot (Q-S1), SET it, PUBLISH
    SETTINGS, update this process's L1."""
    rt = get_runtime()
    name_values = [_name_text(n) for n in names]
    async with rt.core_session_factory() as session:
        snapshot = await load_settings_snapshot(session)
    await rt.cache.write_settings(snapshot, name_values)


async def refresh_subscriptions(tenant_ids: Sequence[str]) -> None:
    """After a subscription commit (or new-tenant seeding): rebuild each
    tenant's value (Q-S2/Q-S3), SET it, PUBLISH SUBSCRIPTION."""
    rt = get_runtime()
    ids = [str(t) for t in tenant_ids]
    if not ids:
        return
    async with rt.core_session_factory() as session:
        values = await load_subscriptions_many(session, ids)
    await rt.cache.write_subscriptions([values[tenant] for tenant in ids])
