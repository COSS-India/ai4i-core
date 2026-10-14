"""The report's data sources, built in one place for the scheduled run
(scheduler.run_scheduled_report) and the manual script
(app.scripts.send_usage_report): Prometheus, the core and auth databases,
and the collector over them.

The service's own lifespan isn't running in the script, so the database
helpers are imported when called — after the caller has initialised them.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.usage_report.collector import UsageReportCollector
from app.utils.prometheus_client import PrometheusClient


@dataclass(frozen=True)
class ReportSources:
    collector: UsageReportCollector
    prometheus: PrometheusClient
    core_db: AsyncSession
    auth_db: AsyncSession


@asynccontextmanager
async def report_sources(http_client) -> AsyncIterator[ReportSources]:
    """Raises RuntimeError when Prometheus or the auth DB isn't configured:
    the report can't be built without either."""
    from app.core.config import settings
    from app.core.database import get_auth_session_factory, get_primary_session_factory
    from app.repositories.model_management.model_repository import ModelRepository
    from app.repositories.model_management.service_repository import ServiceRepository
    from app.services.metering_service import MeteringService

    if not settings.prometheus_url:
        raise RuntimeError("PROMETHEUS_URL is not set; request figures cannot be collected")
    auth_factory = get_auth_session_factory()
    if auth_factory is None:
        raise RuntimeError("AUTH_DB_NAME is not set; institutions, budgets and recipients live in the auth DB")
    prometheus = PrometheusClient(settings.prometheus_url, http_client, timeout=settings.prometheus_timeout)
    async with get_primary_session_factory()() as core_db, auth_factory() as auth_db:
        metering = MeteringService(prometheus, auth_db, ServiceRepository(core_db), ModelRepository(core_db))
        yield ReportSources(UsageReportCollector(metering, auth_db, core_db), prometheus, core_db, auth_db)
