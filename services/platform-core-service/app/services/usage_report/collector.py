"""Collects the Usage Viewer report's figures for one period (AI4IDS-3278).

Only figures the platform tracks are collected. Availability, P95 latency,
fallback rate, provider count and financial-year totals are not tracked,
so the email and PDF leave them out.

Every figure comes from one collect() run, so the email summary and the
attached PDF always agree (a single ReportData feeds both).

Request figures are API-key inference traffic, the population the Usage
Dashboard counts, from Prometheus. Spend in the period comes from
usage_events / daily_usage (the dashboard's period source), which only
starts when usage recording began; allocation, lifetime spend and remaining
budget are current balances (tenants.allocated_budget, budget_usage).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Optional, TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.pay_per_use.usage_repository import UsageRepository
from app.services.metering_service import MeteringService
from app.services.usage_report.period import ReportPeriod
from app.utils.metering_promql_builder import (
    SERVICE_BREAKDOWN_CONFIG,
    AbsoluteRange,
    retention_edge,
)
from app.utils.usage_period import UsagePeriod

logger = logging.getLogger(__name__)

T = TypeVar("T")

TOP_N = 5
NEARING_LIMIT_PCT = 80.0   # "institutions nearing limit": this much of their allocation used
EXHAUSTED_PCT = 100.0


def task_display_name(task: Optional[str]) -> str:
    cfg = SERVICE_BREAKDOWN_CONFIG.get(task or "")
    return cfg["display_name"] if cfg else (task or "Unknown").upper()


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


@dataclass
class RankedModel:
    name: str
    task: str
    share_pct: float


@dataclass
class RankedInstitution:
    name: str
    share_pct: float
    main_tasks: list[str]


@dataclass
class InstitutionSpend:
    name: str
    spent: Decimal
    used_pct: float


@dataclass
class BudgetSummary:
    """Current balances, across institutions with a budget on file."""
    allocated: Decimal
    spent: Decimal
    remaining: Decimal
    exhausted: int
    nearing_limit: int
    top_by_spend: list[InstitutionSpend]

    @property
    def used_pct(self) -> Optional[float]:
        return float(self.spent / self.allocated * 100) if self.allocated > 0 else None


@dataclass
class PeriodSpend:
    """Spend recorded in the period. ``since`` is set when usage recording
    began inside the period, so the amount covers only part of it.
    covered_days is None for a sub-day period (no per-day burn rate)."""
    amount: Decimal
    since: Optional[datetime]
    covered_days: Optional[int]

    @property
    def burn_rate(self) -> Optional[Decimal]:
        return None if self.covered_days is None else self.amount / self.covered_days


@dataclass
class ReportData:
    period: ReportPeriod
    generated_at: datetime
    # Platform health
    total_requests: Optional[int] = None
    prev_total_requests: Optional[int] = None
    server_errors: Optional[int] = None
    # Model portfolio
    total_models: Optional[int] = None
    models_by_task: dict[str, int] = field(default_factory=dict)
    active_models: Optional[int] = None
    top_models: list[RankedModel] = field(default_factory=list)
    # Adoption
    total_institutions: Optional[int] = None
    new_institutions: Optional[int] = None
    active_institutions: Optional[int] = None
    prev_active_institutions: Optional[int] = None
    dormant_institutions: Optional[int] = None
    total_applications: Optional[int] = None
    active_applications: Optional[int] = None
    requests_by_task: list[tuple[str, int]] = field(default_factory=list)
    top_institutions: list[RankedInstitution] = field(default_factory=list)
    # Budget
    budget: Optional[BudgetSummary] = None
    period_spend: Optional[PeriodSpend] = None
    # Names of figures that failed to load (logged; shown as unavailable)
    failed: list[str] = field(default_factory=list)

    @property
    def days(self) -> Optional[int]:
        """Whole days in the period; None for a sub-day period."""
        return self.period.day_count

    @property
    def error_rate_pct(self) -> Optional[float]:
        if self.server_errors is None or not self.total_requests:
            return None
        return self.server_errors / self.total_requests * 100

    @property
    def requests_change_pct(self) -> Optional[float]:
        if self.total_requests is None or not self.prev_total_requests:
            return None
        return (self.total_requests - self.prev_total_requests) / self.prev_total_requests * 100

    @property
    def active_institutions_change(self) -> Optional[int]:
        if self.active_institutions is None or self.prev_active_institutions is None:
            return None
        return self.active_institutions - self.prev_active_institutions

    @property
    def inactive_models(self) -> Optional[int]:
        if self.total_models is None or self.active_models is None:
            return None
        return max(0, self.total_models - self.active_models)

    @property
    def avg_daily_requests(self) -> Optional[float]:
        if self.total_requests is None or self.days is None:
            return None
        return self.total_requests / self.days


def _range(period: UsagePeriod) -> AbsoluteRange:
    return AbsoluteRange(start=period.start, end=period.end)


class UsageReportCollector:
    """Each auth/core session is a single AsyncSession, which is not safe for
    concurrent use, so every figure is fetched sequentially."""

    def __init__(self, metering: MeteringService, auth_db: AsyncSession, core_db: AsyncSession) -> None:
        self._metering = metering
        self._auth_db = auth_db
        self._core_db = core_db

    async def collect(self, report_period: ReportPeriod, now: Optional[datetime] = None) -> ReportData:
        """Raises ValueError for a period that hasn't ended or that Prometheus no
        longer fully retains — either would report silently wrong numbers."""
        now = now or datetime.now(timezone.utc)
        period = report_period.usage_period(now)
        await self._metering.refresh_retention()
        edge = retention_edge(now)
        if period.start < edge:
            raise ValueError(
                f"{report_period.label} starts before the oldest retained metering data "
                f"({edge:%Y-%m-%d}); its request figures would be incomplete"
            )
        prev = report_period.previous().usage_period(now)
        prev_retained = prev.start >= edge
        data = ReportData(period=report_period, generated_at=now)
        rng = _range(period)

        data.total_requests = await self._try(data, "total_requests", self._metering.inference_request_total(rng))
        data.server_errors = await self._try(data, "error_rate", self._metering.server_error_total(rng))
        if prev_retained:
            data.prev_total_requests = await self._try(
                data, "requests_vs_previous", self._metering.inference_request_total(_range(prev))
            )

        await self._collect_models(data, rng)
        await self._collect_adoption(data, period, prev, prev_retained)
        data.budget = await self._try(data, "budget", self._budget_summary())
        data.period_spend = await self._try(
            data, "period_spend", self._period_spend(period, subdaily=not report_period.whole_days)
        )
        return data

    # ── sections ────────────────────────────────────────────────────────────

    async def _collect_models(self, data: ReportData, rng: AbsoluteRange) -> None:
        data.total_models = await self._try(data, "total_models", self._registry_count())
        by_task = await self._try(data, "models_by_task", self._metering.registry_model_counts_by_task())
        if by_task is not None:
            data.models_by_task = {task_display_name(task): n for task, n in by_task.items()}
        breakdown = await self._try(
            data, "model_usage", self._metering.model_breakdown(tenant=None, time_range=rng)
        )
        if breakdown is not None and not breakdown["model_totals"] and data.total_requests:
            # model_breakdown returns empty instead of raising when Prometheus
            # fails; requests with no model at all means that, not "0 models used".
            logger.warning("usage report: model_usage unavailable (no model rows for %s requests)",
                           data.total_requests)
            data.failed.append("model_usage")
            breakdown = None
        if breakdown is not None:
            kpis = MeteringService.model_consumption_kpis(breakdown["services"], breakdown["model_totals"])
            data.active_models = kpis["active_models"]
            _, ranked, _ = MeteringService.model_consumption_ranking(breakdown["model_totals"], TOP_N)
            data.top_models = [
                RankedModel(m["model_name"], task_display_name(m.get("task_type")), m["consumption_pct"])
                for m in ranked
            ]

    async def _collect_adoption(
        self, data: ReportData, period: UsagePeriod, prev: UsagePeriod, prev_retained: bool
    ) -> None:
        data.total_institutions = await self._try(
            data, "total_institutions",
            self._scalar("SELECT COUNT(*) FROM tenants WHERE created_at < :end", end=period.end),
        )
        data.new_institutions = await self._try(
            data, "new_institutions",
            self._scalar(
                "SELECT COUNT(*) FROM tenants WHERE created_at >= :start AND created_at < :end",
                start=period.start, end=period.end,
            ),
        )
        data.total_applications = await self._try(
            data, "total_applications",
            self._scalar("SELECT COUNT(*) FROM applications WHERE created_at < :end", end=period.end),
        )

        active_ids = await self._try(data, "active_institutions", self._metering.active_tenant_ids(_range(period)))
        prev_ids = None
        if prev_retained:
            prev_ids = await self._try(
                data, "active_institutions_previous", self._metering.active_tenant_ids(_range(prev))
            )
        if active_ids is not None:
            data.active_institutions = len(active_ids)
        if prev_ids is not None:
            data.prev_active_institutions = len(prev_ids)
        if active_ids is not None and prev_ids is not None:
            data.dormant_institutions = await self._try(
                data, "dormant_institutions", self._dormant_count(active_ids | prev_ids, prev.start)
            )

        data.active_applications = await self._try(
            data, "active_applications", self._metering.active_application_count(_range(period))
        )

        usage = await self._try(data, "institution_usage", self._metering.tenant_task_usage(_range(period)))
        if usage is not None:
            data.requests_by_task = sorted(
                ((task_display_name(t), n) for t, n in usage["task_totals"].items()),
                key=lambda x: x[1], reverse=True,
            )
            grand = usage["grand_total"]
            data.top_institutions = [
                RankedInstitution(
                    name=t["tenant"],
                    share_pct=t["total"] / grand * 100 if grand else 0.0,
                    main_tasks=[
                        task_display_name(task)
                        for task, _ in sorted(t["tasks"].items(), key=lambda x: x[1], reverse=True)[:2]
                    ],
                )
                for t in usage["tenants"][:TOP_N]
            ]

    # ── queries ─────────────────────────────────────────────────────────────

    async def _registry_count(self) -> int:
        """registry_model_count() returns None instead of raising when the DB
        query fails; raise here so the figure is recorded as failed, not shown
        as N/A in a report sent without --allow-partial."""
        count = await self._metering.registry_model_count()
        if count is None:
            raise RuntimeError("model registry unavailable")
        return count

    async def _scalar(self, sql: str, **params) -> int:
        return int((await self._auth_db.execute(text(sql), params)).scalar() or 0)

    async def _dormant_count(self, recently_active: set[str], onboarded_before: datetime) -> int:
        """ACTIVE institutions onboarded before the previous period that had no
        requests in either this period or the previous one."""
        rows = await self._auth_db.execute(
            text("SELECT id FROM tenants WHERE status = 'ACTIVE' AND created_at < :before"),
            {"before": onboarded_before},
        )
        return sum(1 for (tid,) in rows.all() if str(tid) not in recently_active)

    async def _budget_summary(self) -> BudgetSummary:
        rows = (
            await self._auth_db.execute(
                text(
                    "SELECT id, organisation FROM tenants "
                    "WHERE allocated_budget IS NOT NULL AND status <> 'DEACTIVATED'"
                )
            )
        ).all()
        names = {str(r.id): r.organisation for r in rows}
        budgets = await UsageRepository(self._core_db).get_tenant_budgets(None, list(names), self._auth_db)
        allocated = spent = remaining = Decimal("0")
        exhausted = nearing = 0
        spends: list[InstitutionSpend] = []
        for tenant_id, b in budgets.items():
            allocated += b.budget_limit
            spent += b.spent
            remaining += b.available_balance
            used_pct = (
                float(b.spent / b.budget_limit * 100) if b.budget_limit > 0
                else (100.0 if b.spent > 0 else 0.0)
            )
            if used_pct >= EXHAUSTED_PCT:
                exhausted += 1
            elif used_pct >= NEARING_LIMIT_PCT:
                nearing += 1
            spends.append(InstitutionSpend(names.get(tenant_id, tenant_id), b.spent, used_pct))
        top = sorted((s for s in spends if s.spent > 0), key=lambda s: s.spent, reverse=True)[:TOP_N]
        return BudgetSummary(allocated, spent, remaining, exhausted, nearing, top)

    async def _period_spend(self, period: UsagePeriod, subdaily: bool = False) -> Optional[PeriodSpend]:
        """None when usage recording had not started by the end of the period."""
        repo = UsageRepository(self._core_db)
        data_from = await repo.get_usage_data_from(period)
        if data_from is None:
            return None
        rows = await repo.get_period_usage(period)
        amount = sum((_decimal(r.cost) for r in rows), Decimal("0"))
        covered_from = max(period.start, data_from)
        covered_days = None if subdaily else max(1, math.ceil((period.end - covered_from).total_seconds() / 86_400))
        return PeriodSpend(amount, data_from if data_from > period.start else None, covered_days)

    # ── helpers ─────────────────────────────────────────────────────────────

    async def _try(self, data: ReportData, name: str, coro: Awaitable[T]) -> Optional[T]:
        """One figure failing (Prometheus down, a DB error) leaves it unavailable
        instead of aborting the report. A failed query aborts its session's
        transaction, so roll back before the next query reuses it."""
        try:
            return await coro
        except Exception:
            logger.warning("usage report: %s unavailable", name, exc_info=True)
            data.failed.append(name)
            for session in (self._auth_db, self._core_db):
                try:
                    await session.rollback()
                except Exception:
                    logger.warning("usage report: rollback after %s failed", name, exc_info=True)
            return None
