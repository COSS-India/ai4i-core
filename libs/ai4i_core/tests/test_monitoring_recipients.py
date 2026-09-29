"""ai4i_core.kafka.recipients.RecipientResolver.for_roles (Q-R3)

MONITORING recipients are resolved from the row's selected roles on every
send, never from a list frozen when the row was last saved — so a user who
gains ADMIN/MODERATOR after the save is included, and one who loses the role
or is deactivated is dropped, with no re-save in between.

The fake auth DB applies the active / not-deleted filters only if the SQL
actually carries them, so dropping either filter from the query fails a test
here rather than passing silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

import pytest

from ai4i_core.kafka.recipients import RecipientResolver


@dataclass
class _User:
    id: str
    email: str
    roles: Set[str]
    full_name: str = ""
    is_active: bool = True
    is_delete: bool = False


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return list(self._rows)


@dataclass
class _AuthDb:
    users: List[_User] = field(default_factory=list)
    calls: int = 0

    async def execute(self, stmt, params):
        self.calls += 1
        sql = str(stmt)
        rows = []
        for u in self.users:
            if not set(params["roles"]) & u.roles:
                continue
            if "is_active IS TRUE" in sql and not u.is_active:
                continue
            if "is_delete IS NOT TRUE" in sql and u.is_delete:
                continue
            rows.append({"id": u.id, "email": f"enc:{u.email}", "full_name": u.full_name})
        return _Result(rows)


def _resolver():
    return RecipientResolver(lambda token: token.removeprefix("enc:") if token else None)


@pytest.mark.asyncio
async def test_every_active_holder_of_a_selected_role_is_resolved_once():
    db = _AuthDb([
        _User("1", "a@x.io", {"ADMIN"}, "Asha"),
        _User("2", "m@x.io", {"MODERATOR"}),
        _User("3", "both@x.io", {"ADMIN", "MODERATOR"}),
        _User("4", "t@x.io", {"TENANT ADMIN"}),
    ])
    out = await _resolver().for_roles(db, ["ADMIN", "MODERATOR"])
    assert [r.email for r in out] == ["a@x.io", "both@x.io", "m@x.io"]
    assert out[0].name == "Asha"


@pytest.mark.asyncio
async def test_inactive_and_deleted_users_are_dropped():
    db = _AuthDb([
        _User("1", "a@x.io", {"ADMIN"}),
        _User("2", "off@x.io", {"ADMIN"}, is_active=False),
        _User("3", "gone@x.io", {"ADMIN"}, is_delete=True),
    ])
    assert [r.email for r in await _resolver().for_roles(db, ["ADMIN"])] == ["a@x.io"]


@pytest.mark.asyncio
async def test_a_role_granted_or_revoked_after_the_save_shows_on_the_next_send():
    admin = _User("1", "a@x.io", {"ADMIN"})
    newcomer = _User("2", "new@x.io", set())
    db = _AuthDb([admin, newcomer])
    resolver = _resolver()
    assert [r.email for r in await resolver.for_roles(db, ["ADMIN"])] == ["a@x.io"]

    newcomer.roles.add("ADMIN")
    admin.roles.clear()
    assert [r.email for r in await resolver.for_roles(db, ["ADMIN"])] == ["new@x.io"]


@pytest.mark.asyncio
async def test_no_or_non_monitoring_roles_resolve_to_nobody_without_a_query():
    db = _AuthDb([_User("1", "t@x.io", {"TENANT ADMIN"})])
    assert await _resolver().for_roles(db, []) == []
    assert await _resolver().for_roles(db, ["TENANT ADMIN"]) == []
    assert db.calls == 0
