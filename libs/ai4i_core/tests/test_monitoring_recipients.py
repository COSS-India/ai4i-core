"""ai4i_core.kafka.recipients.RecipientResolver (Q-R1, Q-R2, Q-R3)

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

from ai4i_core.kafka.constants import NotificationScope
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


# ── Decrypt failure: one bad email never drops the event for the others ──


class _Mappings(list):
    def all(self):
        return list(self)


class _RowsDb:
    """Returns fixed rows for any query — for_tenant / for_tenants."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt, params):
        rows = self.rows

        class _R:
            def mappings(self):
                return _Mappings(rows)

        return _R()


def _strict_resolver():
    def decrypt(token):
        if "bad" in token:
            raise ValueError("cannot decrypt")
        return token.removeprefix("enc:")

    return RecipientResolver(decrypt)


@pytest.mark.asyncio
async def test_undecryptable_recipient_is_skipped_for_roles_others_still_resolved():
    db = _AuthDb([_User("1", "ok@x.io", {"ADMIN"}), _User("2", "bad@x.io", {"ADMIN"})])
    assert [r.email for r in await _strict_resolver().for_roles(db, ["ADMIN"])] == ["ok@x.io"]


@pytest.mark.asyncio
async def test_undecryptable_recipient_is_skipped_for_tenant_others_still_resolved():
    db = _RowsDb([
        {"id": 1, "email": "enc:ok@x.io", "full_name": "Ok", "tenant_name": "Acme"},
        {"id": 2, "email": "enc:bad@x.io", "full_name": "Bad", "tenant_name": "Acme"},
    ])
    people, tenant_name = await _strict_resolver().for_tenant(db, "7", NotificationScope.GLOBAL)
    assert [r.email for r in people] == ["ok@x.io"]
    assert tenant_name == "Acme"


def test_tenant_name_is_the_institution_not_the_contact():
    """tenant_name fills every tenant email's subject and headline: it must be
    tenants.organisation (the institution), never tenants.name (the contact)."""
    from ai4i_core.kafka.recipients import _ONE_TENANT_SQL

    assert "t.organisation FROM tenants t" in _ONE_TENANT_SQL.text
    assert "t.name FROM tenants" not in _ONE_TENANT_SQL.text


# ── for_tenant / for_tenants: scope decides ADMIN, not a stored role flag ──


@pytest.mark.asyncio
async def test_for_tenant_global_scope_includes_platform_admin():
    db = _RowsDb([
        {"id": 1, "email": "enc:admin@x.io", "full_name": "Admin", "tenant_name": "Acme"},
    ])
    people, _ = await _resolver().for_tenant(db, "7", NotificationScope.GLOBAL)
    assert [r.email for r in people] == ["admin@x.io"]


@pytest.mark.asyncio
async def test_for_tenant_institution_scope_still_queries_but_excludes_admin_role():
    # The fake DB doesn't filter by include_admin itself (that's Postgres's
    # job in production); this pins that INSTITUTION scope is what tells
    # the query not to want an ADMIN row at all, via include_admin=False.
    captured = {}

    class _CapturingDb(_RowsDb):
        async def execute(self, stmt, params):
            captured.update(params)
            return await super().execute(stmt, params)

    db = _CapturingDb([])
    await _resolver().for_tenant(db, "7", NotificationScope.INSTITUTION)
    assert captured["include_admin"] is False
    assert captured["include_tenant_admin"] is True


@pytest.mark.asyncio
async def test_for_tenant_global_scope_passes_include_admin_true():
    captured = {}

    class _CapturingDb(_RowsDb):
        async def execute(self, stmt, params):
            captured.update(params)
            return await super().execute(stmt, params)

    db = _CapturingDb([])
    await _resolver().for_tenant(db, "7", NotificationScope.GLOBAL)
    assert captured["include_admin"] is True
    assert captured["include_tenant_admin"] is True


# ── for_tenants: per-tenant grouping (Q-R2) ──


def _tenant_row(tenant_id, role, user_id, email):
    return {"tenant_id": tenant_id, "role": role, "user_id": user_id, "email": f"enc:{email}", "full_name": ""}


@pytest.mark.asyncio
async def test_for_tenants_global_scope_keeps_platform_admin_and_extras_on_their_own_tenant():
    db = _RowsDb([
        _tenant_row("1", "ADMIN", "a", "admin@x.io"),
        _tenant_row("7", "TENANT ADMIN", "t7", "ta7@x.io"),
        _tenant_row("8", "TENANT ADMIN", "t8", "ta8@x.io"),
        _tenant_row("7", "USER", "u7", "extra7@x.io"),
        _tenant_row("8", "USER", "u8", "extra8@x.io"),
    ])
    out = await _resolver().for_tenants(
        db, ["7", "8"], NotificationScope.GLOBAL, {"7": ["u7"], "8": ["u8"]}
    )
    assert [r.email for r in out["7"]] == ["admin@x.io", "extra7@x.io", "ta7@x.io"]
    assert [r.email for r in out["8"]] == ["admin@x.io", "extra8@x.io", "ta8@x.io"]


@pytest.mark.asyncio
async def test_for_tenants_institution_scope_excludes_platform_admin():
    db = _RowsDb([
        _tenant_row("1", "ADMIN", "a", "admin@x.io"),
        _tenant_row("7", "TENANT ADMIN", "t7", "ta7@x.io"),
    ])
    out = await _resolver().for_tenants(db, ["7"], NotificationScope.INSTITUTION, {})
    assert [r.email for r in out["7"]] == ["ta7@x.io"]


@pytest.mark.asyncio
async def test_for_tenants_extra_listed_by_another_tenant_is_not_leaked():
    # u8 is tenant 7's user row but only tenant 8's subscription lists it.
    db = _RowsDb([_tenant_row("7", "USER", "u8", "someone@x.io")])
    out = await _resolver().for_tenants(db, ["7", "8"], NotificationScope.INSTITUTION, {"8": ["u8"]})
    assert out == {"7": [], "8": []}


@pytest.mark.asyncio
async def test_for_tenants_unselected_roles_are_left_out_and_duplicates_collapse():
    db = _RowsDb([
        _tenant_row("1", "ADMIN", "a", "admin@x.io"),
        _tenant_row("7", "TENANT ADMIN", "t7", "ta7@x.io"),
        _tenant_row("7", "TENANT ADMIN", "t7", "ta7@x.io"),
    ])
    out = await _resolver().for_tenants(db, ["7"], NotificationScope.INSTITUTION, {})
    assert [r.email for r in out["7"]] == ["ta7@x.io"]


@pytest.mark.asyncio
async def test_for_tenants_no_tenants_runs_no_query():
    db = _AuthDb()
    assert await _resolver().for_tenants(db, [], NotificationScope.GLOBAL, {}) == {}
    assert db.calls == 0
