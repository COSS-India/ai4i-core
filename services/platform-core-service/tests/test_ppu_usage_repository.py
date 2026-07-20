"""Unit tests for PPUUsageRepository.get_tier_names()'s in-process TTL cache.

The cache lives at module scope (app.repositories.pay_per_use.ppu_usage_repository),
not on the instance, since PPUUsageRepository is constructed fresh per request. That
means state can leak between test functions unless it's reset — hence the autouse
fixture below.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.pay_per_use import ppu_usage_repository as repo_module
from app.repositories.pay_per_use.ppu_usage_repository import PPUUsageRepository


@pytest.fixture(autouse=True)
def _reset_tier_cache():
    """Ensure each test starts from a cold cache and leaves none behind."""
    repo_module._tier_cache = {}
    repo_module._tier_cache_loaded_at = None
    yield
    repo_module._tier_cache = {}
    repo_module._tier_cache_loaded_at = None


def _make_db(rows: list[SimpleNamespace]) -> AsyncMock:
    """Fake AsyncSession whose execute() returns rows shaped like the
    (PPUTier.id, PPUTier.name) tuples get_tier_names() selects."""
    db = AsyncMock()
    result = SimpleNamespace(all=lambda: rows)
    db.execute = AsyncMock(return_value=result)
    return db
