"""Application-level usage for the Metering Dashboard's Applications tab.

Two kinds of spend, side by side:
- all-time (spendBudget/remainingBudget): budget_usage, keyed by api_key_id
  only, with no time dimension — so billingPeriod is always "lifetime";
- the selected period (periodSpend): usage_events or daily_usage (see
  period_usage.period_source).
Identity/allocation (tenants/applications/api_key) lives in auth-service, read
here via the auth_db cross-DB session — same pattern as
UsageService._resolve_tenant_names.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError
from app.repositories.pay_per_use.application_usage_repository import (
    ApplicationUsageRepository,
)
from app.schemas.pay_per_use.application_usage import (
    ApiKeyUsageItem,
    ApplicationUsageDetailResponse,
    ApplicationUsageListItem,
    ApplicationUsageListResponse,
    ApplicationUsageSummaryResponse,
    ApplicationUsageTotals,
    MoneyPercent,
)
from app.utils.usage_period import UsagePeriod


def _pct(amount: Decimal, denominator: Decimal) -> float:
    if not denominator:
        return 0.0
    return float(amount / denominator * 100)


def _money_percent(amount: Decimal, denominator: Decimal) -> MoneyPercent:
    return MoneyPercent(amount=float(amount), percentage=_pct(amount, denominator))


def _mask_key(api_key: str) -> str:
    return api_key[-4:] if api_key else ""


def _to_tenant_pk(tenant_id: str) -> Optional[int]:
    """tenants.id/applications.tenant_id are Integer columns; asyncpg (unlike
    psycopg2) won't coerce a string bind param, so this must be cast before
    binding — same guard _resolve_tenant_names uses (.isdigit())."""
    return int(tenant_id) if tenant_id and tenant_id.isdigit() else None


class ApplicationUsageService:
    def __init__(self, repo: ApplicationUsageRepository) -> None:
        self._repo = repo

    @staticmethod
    async def _load_tenant_budget(tenant_id: str, auth_db: Optional[AsyncSession]) -> Decimal:
        # auth_db is None only when the feature/dependency isn't configured — a
        # legitimate degrade-to-zero case. A query that raises once auth_db exists
        # is a real failure (connection drop, aborted transaction) and must NOT be
        # swallowed here: unlike _resolve_tenant_names (which degrades a display
        # name to an ID — harmless), swallowing this would silently turn real
        # money into a false zero. Let it propagate; the global exception handler
        # turns it into a proper 500 instead of a misleading 200/404.
        tenant_pk = _to_tenant_pk(tenant_id)
        if not auth_db or tenant_pk is None:
            return Decimal("0")
        result = await auth_db.execute(
            text("SELECT allocated_budget FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": tenant_pk},
        )
        row = result.first()
        return row[0] if row and row[0] is not None else Decimal("0")

    @staticmethod
    async def _load_tenant_applications(
        tenant_id: str, auth_db: Optional[AsyncSession]
    ) -> list[dict]:
        # See _load_tenant_budget: only "not configured" degrades gracefully here;
        # a real query failure must propagate, not be reported as "zero applications".
        tenant_pk = _to_tenant_pk(tenant_id)
        if not auth_db or tenant_pk is None:
            return []
        result = await auth_db.execute(
            text(
                "SELECT id, name, domain, allocated_percentage, allocated_budget, status "
                "FROM applications WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_pk},
        )
        return [dict(row._mapping) for row in result.all()]

    @staticmethod
    async def _load_application_api_keys(
        application_ids: list[int], auth_db: Optional[AsyncSession]
    ) -> list[dict]:
        # See _load_tenant_budget: only "not configured"/"nothing to look up"
        # degrades gracefully here; a real query failure must propagate.
        if not auth_db or not application_ids:
            return []
        result = await auth_db.execute(
            text(
                "SELECT id, application_id, key_name, api_key, allocated_percentage, "
                "allocated_budget, is_active FROM api_key WHERE application_id = ANY(:app_ids)"
            ),
            {"app_ids": application_ids},
        )
        return [dict(row._mapping) for row in result.all()]

    async def _spend_by_application(
        self, applications: list[dict], auth_db: Optional[AsyncSession], period: UsagePeriod,
    ) -> tuple[dict[int, Decimal], dict[int, Decimal], dict[int, list[dict]]]:
        """(all-time spend per application_id, spend in ``period`` per
        application_id, api_keys per application_id). Each key dict also
        carries its own "_spend" (all-time) and "_period_spend" (recorded
        only); an application's period spend adds the Prometheus backfill's
        estimates, which have no key."""
        app_ids = [app["id"] for app in applications]
        api_keys = await self._load_application_api_keys(app_ids, auth_db)
        key_ids = [k["id"] for k in api_keys]
        spend_by_key = await self._repo.get_spend_by_api_key_ids(key_ids)
        period_spend_by_key = await self._repo.get_period_spend_by_api_key_ids(period, key_ids)
        backfilled = await self._repo.get_backfill_period_spend(period, app_ids)

        keys_by_app: dict[int, list[dict]] = {app_id: [] for app_id in app_ids}
        spend_by_app: dict[int, Decimal] = {app_id: Decimal("0") for app_id in app_ids}
        period_spend_by_app: dict[int, Decimal] = {
            app_id: backfilled.get(app_id, Decimal("0")) for app_id in app_ids
        }
        for key in api_keys:
            key["_spend"] = spend_by_key.get(key["id"], Decimal("0"))
            key["_period_spend"] = period_spend_by_key.get(key["id"], Decimal("0"))
            keys_by_app[key["application_id"]].append(key)
            spend_by_app[key["application_id"]] += key["_spend"]
            period_spend_by_app[key["application_id"]] += key["_period_spend"]
        return spend_by_app, period_spend_by_app, keys_by_app

    async def _period_block(self, period: UsagePeriod):
        return period.to_schema(
            await self._repo.get_usage_data_from(period), await self._repo.get_recorded_from(),
        )

    async def get_summary(
        self, tenant_id: str, period: UsagePeriod, auth_db: Optional[AsyncSession]
    ) -> ApplicationUsageSummaryResponse:
        tenant_budget = await self._load_tenant_budget(tenant_id, auth_db)
        applications = await self._load_tenant_applications(tenant_id, auth_db)
        spend_by_app, period_spend_by_app, _ = await self._spend_by_application(
            applications, auth_db, period
        )

        allocated_amount = sum(
            (app["allocated_budget"] or Decimal("0")) for app in applications
        ) or Decimal("0")
        spend_amount = sum(spend_by_app.values(), Decimal("0"))
        remaining_amount = allocated_amount - spend_amount
        period_spend = sum(period_spend_by_app.values(), Decimal("0"))

        return ApplicationUsageSummaryResponse(
            period=await self._period_block(period),
            totalApplications=len(applications),
            allocatedBudget=_money_percent(allocated_amount, tenant_budget),
            spendBudget=_money_percent(spend_amount, tenant_budget),
            remainingBudget=_money_percent(remaining_amount, tenant_budget),
            periodSpend=_money_percent(period_spend, tenant_budget),
            billingPeriod="lifetime",
        )

    async def get_application_list(
        self,
        tenant_id: str,
        period: UsagePeriod,
        auth_db: Optional[AsyncSession],
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> ApplicationUsageListResponse:
        """Sorted by spend in the period (application id as the tie-break,
        so pages stay stable), then paginated."""
        tenant_budget = await self._load_tenant_budget(tenant_id, auth_db)
        applications = await self._load_tenant_applications(tenant_id, auth_db)
        spend_by_app, period_spend_by_app, _ = await self._spend_by_application(
            applications, auth_db, period
        )

        items = []
        for app in applications:
            allocated_amount = app["allocated_budget"] or Decimal("0")
            spend_amount = spend_by_app.get(app["id"], Decimal("0"))
            remaining_amount = allocated_amount - spend_amount
            items.append(
                ApplicationUsageListItem(
                    applicationId=app["id"],
                    name=app["name"],
                    domain=app["domain"],
                    allocatedBudget=_money_percent(allocated_amount, tenant_budget),
                    spendBudget=_money_percent(spend_amount, allocated_amount),
                    remainingBudget=_money_percent(remaining_amount, allocated_amount),
                    periodSpend=_money_percent(
                        period_spend_by_app.get(app["id"], Decimal("0")), allocated_amount
                    ),
                )
            )

        items.sort(
            key=lambda i: (i.periodSpend.amount, i.applicationId),
            reverse=(sort_order == "desc"),
        )
        total = len(items)
        return ApplicationUsageListResponse(
            period=await self._period_block(period), data=items[offset : offset + limit], total=total,
        )

    async def get_application_detail(
        self,
        application_id: int,
        tenant_id: str,
        period: UsagePeriod,
        auth_db: Optional[AsyncSession],
    ) -> ApplicationUsageDetailResponse:
        tenant_budget = await self._load_tenant_budget(tenant_id, auth_db)
        applications = await self._load_tenant_applications(tenant_id, auth_db)
        application = next((a for a in applications if a["id"] == application_id), None)
        if application is None:
            raise EntityNotFoundError(f"Application {application_id}")

        spend_by_app, period_spend_by_app, keys_by_app = await self._spend_by_application(
            [application], auth_db, period
        )
        allocated_amount = application["allocated_budget"] or Decimal("0")
        spend_amount = spend_by_app.get(application_id, Decimal("0"))
        remaining_amount = allocated_amount - spend_amount
        period_spend = period_spend_by_app.get(application_id, Decimal("0"))

        api_key_items = []
        for key in keys_by_app.get(application_id, []):
            key_allocated = key["allocated_budget"] or Decimal("0")
            key_spend = key["_spend"]
            key_remaining = key_allocated - key_spend
            api_key_items.append(
                ApiKeyUsageItem(
                    keyId=key["id"],
                    keyName=key["key_name"],
                    maskedKey=_mask_key(key["api_key"]),
                    isActive=key["is_active"],
                    # % of the parent application's total budget assigned to this key,
                    # not the institution's — matches api_key.allocated_percentage
                    # (api_key_service.py:547: allocated_budget = application.allocated_budget
                    # * allocated_percentage / 100).
                    allocatedBudget=_money_percent(key_allocated, allocated_amount),
                    spendBudget=_money_percent(key_spend, key_allocated),
                    remainingBudget=_money_percent(key_remaining, key_allocated),
                    periodSpend=_money_percent(key["_period_spend"], key_allocated),
                )
            )

        return ApplicationUsageDetailResponse(
            period=await self._period_block(period),
            applicationId=application["id"],
            applicationName=application["name"],
            domain=application["domain"],
            allocatedBudget=_money_percent(allocated_amount, tenant_budget),
            spendBudget=_money_percent(spend_amount, allocated_amount),
            remainingBudget=_money_percent(remaining_amount, allocated_amount),
            periodSpend=_money_percent(period_spend, allocated_amount),
            apiKeys=api_key_items,
            totals=ApplicationUsageTotals(
                allocatedBudget=float(allocated_amount),
                spendBudget=float(spend_amount),
                remainingBudget=float(remaining_amount),
                periodSpend=float(period_spend),
            ),
        )
