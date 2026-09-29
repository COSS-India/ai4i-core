"""_seed_notification_subscriptions_for_new_tenant — MONITORING catalog rows
are platform-level (no tenant), so a new tenant must not get a
tenant_notification_subscription row for any of them.

The seed reads configs_notification_alert with raw SQL against
platform-core's database, so the fake below can't evaluate the WHERE
clause — it pins the exclusion in the SELECT text and checks that only the
ids that SELECT returns are inserted.
"""
from unittest.mock import MagicMock

import pytest

from app.services.tenant_service import _seed_notification_subscriptions_for_new_tenant


class _PlatformCoreDb:
    def __init__(self, catalog_ids):
        self.catalog_ids = catalog_ids
        self.selects = []
        self.inserted_ids = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if sql.lstrip().upper().startswith("SELECT"):
            self.selects.append(sql)
            result.scalars.return_value.all.return_value = list(self.catalog_ids)
        else:
            self.inserted_ids.append(params["notification_id"])
        return result

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_select_excludes_monitoring_rows_as_text():
    db = _PlatformCoreDb(catalog_ids=[1, 2])
    await _seed_notification_subscriptions_for_new_tenant(db, tenant_id=7, admin_user_id="42")

    [select_sql] = db.selects
    # ::text so the query still runs against a DB whose enum doesn't have
    # MONITORING yet — comparing the enum column to an unknown label errors,
    # and the seed's catch-all would then silently skip EVERY row.
    assert "type::text <> 'MONITORING'" in select_sql
    assert db.inserted_ids == [1, 2]
    assert db.commits == 1
