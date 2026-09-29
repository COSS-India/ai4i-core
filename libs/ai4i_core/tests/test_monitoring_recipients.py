"""ai4i_core.kafka.recipients.resolve_monitoring_recipients

MONITORING recipients are resolved from configs_notification_alert.
recipient_roles on every call (send time), never from a list frozen when the
row was last PATCHed — so a user who gains ADMIN/MODERATOR after the save is
included, and one who loses the role or is deactivated is dropped, with no
re-save in between.

Both databases are faked. The fake auth DB applies the active / not-deleted
filters only if the SQL actually carries them, so dropping either filter
from the query fails a test here rather than passing silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Dict, List, Set

import pytest

from ai4i_core.kafka import recipients


@pytest.fixture(autouse=True)
def _decrypt():
    recipients.configure(lambda token: token.removeprefix("enc:") if token else None)
    yield
    recipients._decrypt_email = None


@dataclass
class _User:
    email: str
    roles: Set[str]
    is_active: bool = True
    is_delete: bool = False

    @property
    def token(self) -> str:
        return f"enc:{self.email}"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


@dataclass
class _CoreDb:
    """configs_notification_alert rows: id -> (type, recipient_roles)."""

    rows: Dict[int, tuple]

    async def execute(self, stmt, params):
        sql = str(stmt)
        assert "FROM configs_notification_alert" in sql, sql
        row = self.rows.get(params["notification_id"])
        if row is None or ("type::text = 'MONITORING'" in sql and row[0] != "MONITORING"):
            return _Result([])
        return _Result([SimpleNamespace(recipient_roles=row[1])])


@dataclass
class _AuthDb:
    users: List[_User]
    queries: List[dict] = field(default_factory=list)

    async def execute(self, stmt, params):
        sql = str(stmt)
        self.queries.append(params)
        wanted = set(params["roles"])
        tokens = []
        for user in self.users:
            if not user.roles & wanted:
                continue
            if "u.is_active IS TRUE" in sql and not user.is_active:
                continue
            if "u.is_delete IS NOT TRUE" in sql and user.is_delete:
                continue
            tokens.append(user.token)
        # DISTINCT u.email in the real query.
        return _Result([SimpleNamespace(email=t) for t in dict.fromkeys(tokens)])


async def _resolve(core_db, auth_db, notification_id=10):
    return await recipients.resolve_monitoring_recipients(
        core_db, auth_db, notification_id=notification_id
    )


@pytest.mark.asyncio
class TestResolvedAtSendTime:
    async def test_new_admin_is_included_and_deactivated_admin_dropped_without_a_resave(self):
        # Review scenario. The row was saved once with ADMIN selected; after
        # that, a new Adopter Admin is added and an existing one is
        # deactivated. No PATCH happens in between — the next send must
        # still reflect both changes.
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": True, "MODERATOR": False})})
        a1 = _User("a1@x.com", {"ADMIN"})
        a2 = _User("a2@x.com", {"ADMIN"})
        auth_db = _AuthDb(users=[a1, a2])

        assert await _resolve(core_db, auth_db) == ["a1@x.com", "a2@x.com"]

        auth_db.users.append(_User("a3@x.com", {"ADMIN"}))
        a2.is_active = False

        assert await _resolve(core_db, auth_db) == ["a1@x.com", "a3@x.com"]

    async def test_user_whose_role_was_revoked_is_dropped(self):
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": False, "MODERATOR": True})})
        mod = _User("m@x.com", {"MODERATOR"})
        auth_db = _AuthDb(users=[mod])
        assert await _resolve(core_db, auth_db) == ["m@x.com"]

        mod.roles = set()
        assert await _resolve(core_db, auth_db) == []

    async def test_soft_deleted_user_is_dropped(self):
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": True})})
        auth_db = _AuthDb(users=[_User("gone@x.com", {"ADMIN"}, is_delete=True)])
        assert await _resolve(core_db, auth_db) == []

    async def test_role_selection_is_read_on_every_call(self):
        # Changing recipient_roles takes effect on the next send — there is
        # nothing else to rebuild.
        roles = {"ADMIN": True, "MODERATOR": False}
        core_db = _CoreDb(rows={10: ("MONITORING", roles)})
        auth_db = _AuthDb(users=[_User("a@x.com", {"ADMIN"}), _User("m@x.com", {"MODERATOR"})])
        assert await _resolve(core_db, auth_db) == ["a@x.com"]

        roles["MODERATOR"] = True
        assert await _resolve(core_db, auth_db) == ["a@x.com", "m@x.com"]


@pytest.mark.asyncio
class TestRoleSelection:
    async def test_user_holding_both_roles_is_listed_once(self):
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": True, "MODERATOR": True})})
        auth_db = _AuthDb(users=[_User("both@x.com", {"ADMIN", "MODERATOR"})])
        assert await _resolve(core_db, auth_db) == ["both@x.com"]

    async def test_no_role_selected_returns_empty_without_querying_users(self):
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": False, "MODERATOR": False})})
        auth_db = _AuthDb(users=[_User("a@x.com", {"ADMIN"})])
        assert await _resolve(core_db, auth_db) == []
        assert auth_db.queries == []

    async def test_only_admin_and_moderator_are_ever_queried(self):
        # A stray key (never writable through the monitoring PATCH, but
        # defend anyway) must not widen the audience to tenant users.
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": True, "TENANT ADMIN": True})})
        auth_db = _AuthDb(users=[_User("a@x.com", {"ADMIN"}), _User("t@x.com", {"TENANT ADMIN"})])
        assert await _resolve(core_db, auth_db) == ["a@x.com"]
        assert auth_db.queries == [{"roles": ["ADMIN"]}]

    async def test_non_monitoring_notification_id_resolves_to_nobody(self):
        core_db = _CoreDb(rows={2: ("ALERT", {"ADMIN": True})})
        auth_db = _AuthDb(users=[_User("a@x.com", {"ADMIN"})])
        assert await _resolve(core_db, auth_db, notification_id=2) == []

    async def test_unknown_notification_id_resolves_to_nobody(self):
        core_db = _CoreDb(rows={})
        auth_db = _AuthDb(users=[_User("a@x.com", {"ADMIN"})])
        assert await _resolve(core_db, auth_db, notification_id=999) == []


@pytest.mark.asyncio
class TestBestEffort:
    async def test_lookup_failure_returns_empty_not_raises(self):
        class _Down:
            async def execute(self, stmt, params):
                raise ConnectionError("auth db down")

        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": True})})
        assert await _resolve(core_db, _Down()) == []

    async def test_undecryptable_recipient_is_skipped_others_still_sent(self):
        recipients.configure(
            lambda token: (_ for _ in ()).throw(ValueError("bad")) if "bad" in token else token.removeprefix("enc:")
        )
        core_db = _CoreDb(rows={10: ("MONITORING", {"ADMIN": True})})
        auth_db = _AuthDb(users=[_User("ok@x.com", {"ADMIN"}), _User("bad@x.com", {"ADMIN"})])
        assert await _resolve(core_db, auth_db) == ["ok@x.com"]
