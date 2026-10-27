"""Settings for the one-off backfill, read from the environment or
backfill/.env (copied from backfill/env.template) — not pyjob's own .env.

The database connection comes from pyjob's settings (bootstrap.config):
__main__ loads backfill/.env into the environment first, so the DB
variables in it are the ones used.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

ENV_FILE = Path(__file__).resolve().with_name(".env")


class BackfillSettings(BaseSettings):
    # Prometheus to read the history from.
    PROMETHEUS_URL: Optional[str] = None
    PROMETHEUS_TIMEOUT_SECONDS: float = Field(60.0, gt=0)
    # Label carrying the request path on telemetry_obsv_requests_total:
    # "exported_endpoint" on k8s, "endpoint" on a local docker-compose.
    PROMETHEUS_API_PATH_LABEL: str = "exported_endpoint"

    # The IST days to backfill, both inclusive (YYYY-MM-DD). BACKFILL_FROM must
    # be a day Prometheus still has from its start; no day may have recorded
    # (rollup) rows in daily_usage, nor be within the nightly rollup's reach.
    BACKFILL_FROM: Optional[date] = None
    BACKFILL_TO: Optional[date] = None

    class Config:
        # Absolute, so it is backfill/.env whatever the current directory.
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> BackfillSettings:
    return BackfillSettings()
