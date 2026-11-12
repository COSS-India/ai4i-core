"""Usage Viewer recipients of the programme report (AI4IDS-3623).

Only users the UI shows as Active get the report. The fake auth DB applies
each filter only if the SQL actually carries it, so dropping one from the
query fails a test here rather than passing silently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from app.services.usage_report.recipients import usage_viewer_emails


@dataclass
class _User:
    id: str
    email: str
    is_active: bool = True
    is_delete: bool = False
    is_tenant_active: Optional[bool] = True
    tenant_status: Optional[str] = "ACTIVE"  # None: no tenant (platform user)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _AuthDb:
    def __init__(self, users):
        self.users = users

    async def execute(self, stmt, params):
        sql = str(stmt)
        assert params == {"role": "USAGE VIEWER"}
        rows = []
        for u in self.users:
            if "u.is_active IS TRUE" in sql and not u.is_active:
                continue
            if "u.is_delete IS NOT TRUE" in sql and u.is_delete:
                continue
            if "u.is_tenant_active IS NOT FALSE" in sql and u.is_tenant_active is False:
                continue
            if ("status IN ('SUSPENDED', 'DEACTIVATED')" in sql
                    and u.tenant_status in ("SUSPENDED", "DEACTIVATED")):
                continue
            rows.append((u.id, f"enc:{u.email}"))
        return _Result(rows)


def _decrypt(token):
    return token.removeprefix("enc:") if token else None


@pytest.mark.asyncio
async def test_only_active_usage_viewers_get_the_report():
    db = _AuthDb([
        _User("1", "active@x.gov.in"),
        _User("2", "platform@x.gov.in", is_tenant_active=None, tenant_status=None),
        _User("3", "user-suspended@x.gov.in", is_active=False),
        _User("4", "deleted@x.gov.in", is_delete=True),
        _User("5", "tenant-locked@x.gov.in", is_tenant_active=False),
        _User("6", "tenant-suspended@x.gov.in", tenant_status="SUSPENDED"),
        _User("7", "tenant-deactivated@x.gov.in", tenant_status="DEACTIVATED"),
    ])
    assert await usage_viewer_emails(db, _decrypt) == ["active@x.gov.in", "platform@x.gov.in"]
