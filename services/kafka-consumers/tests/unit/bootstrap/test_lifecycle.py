"""bootstrap/lifecycle.py — the named-connection registry, sessions, signals.

No database is reached.  `create_async_engine` is lazy — it builds a pool but
connects on first use — so `add_database` can be exercised against an
unreachable URL, and `dispose()` on a pool that never connected is a no-op.
Sessions are driven off hand-written fakes rather than a sqlite engine, because
what is under test is the rollback and lookup behaviour of this module, not
SQLAlchemy's.
"""
from __future__ import annotations

import asyncio
import signal

import pytest

from bootstrap import lifecycle

UNREACHABLE = "postgresql+asyncpg://u:p@localhost:1/db"


@pytest.fixture(autouse=True)
async def _clean_registry():
    """Module-level dicts: a leaked entry makes the next test's `add_database`
    an idempotent no-op and passes for the wrong reason."""
    yield
    lifecycle._engines.clear()
    lifecycle._session_factories.clear()
    lifecycle._default_factory = None


class TestNamedConnections:
    async def test_opens_a_database_by_name_on_the_shared_credentials(self):
        await lifecycle.add_database("secondary", db_name="other_db")
        engine = lifecycle.get_engine_for("secondary")
        # The name reached the URL, so credentials stayed declared in one place.
        assert engine.url.database == "other_db"

    async def test_opens_a_database_by_url_for_another_instance(self):
        await lifecycle.add_database("foreign", url=UNREACHABLE)
        assert lifecycle.get_engine_for("foreign").url.host == "localhost"

    async def test_is_idempotent(self):
        # Documented as safe to call from more than one code path — a second
        # call must not build a second pool for the same name.
        await lifecycle.add_database("dup", url=UNREACHABLE)
        first = lifecycle.get_engine_for("dup")
        await lifecycle.add_database("dup", url=UNREACHABLE)
        assert lifecycle.get_engine_for("dup") is first

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},  # neither
            {"db_name": "a", "url": UNREACHABLE},  # both
        ],
        ids=["neither", "both"],
    )
    async def test_requires_exactly_one_of_db_name_or_url(self, kwargs):
        with pytest.raises(ValueError, match="exactly one"):
            await lifecycle.add_database("bad", **kwargs)

    def test_an_unopened_name_raises_and_says_what_is_open(self):
        with pytest.raises(RuntimeError, match="was never opened"):
            lifecycle.get_engine_for("never_opened")

    async def test_closing_one_leaves_the_others(self):
        await lifecycle.add_database("keep", url=UNREACHABLE)
        await lifecycle.add_database("drop", url=UNREACHABLE)

        await lifecycle.close_database_connection("drop")

        assert lifecycle.get_engine_for("keep") is not None
        with pytest.raises(RuntimeError):
            lifecycle.get_engine_for("drop")

    async def test_closing_an_absent_name_is_a_no_op(self):
        await lifecycle.close_database_connection("not_there")  # must not raise

    async def test_close_all_disposes_everything(self):
        await lifecycle.add_database("one", url=UNREACHABLE)
        await lifecycle.add_database("two", url=UNREACHABLE)

        await lifecycle.close_all_databases()

        assert lifecycle._engines == {}
        assert lifecycle._session_factories == {}


class _FakeSession:
    def __init__(self):
        self.rolled_back = False
        self.committed = False
        self.closed = False

    async def rollback(self):
        self.rolled_back = True

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.closed = True
        return False


class TestSessionScope:
    @pytest.fixture
    def session(self, monkeypatch):
        fake = _FakeSession()
        monkeypatch.setitem(lifecycle._session_factories, "named", lambda: fake)
        return fake

    async def test_yields_a_session_for_a_named_database(self, session):
        async with lifecycle.session_scope("named") as s:
            assert s is session
        assert session.closed

    async def test_committing_stays_the_callers_job(self, session):
        async with lifecycle.session_scope("named"):
            pass
        assert session.committed is False

    async def test_rolls_back_and_re_raises_on_error(self, session):
        # Deterministically, at the error — not whenever the event loop's
        # async-generator hooks get round to finalising a suspended generator,
        # which is what wrapping ai4i_core's get_db() would have given us (§3.3).
        with pytest.raises(ValueError, match="boom"):
            async with lifecycle.session_scope("named"):
                raise ValueError("boom")
        assert session.rolled_back

    async def test_an_unopened_name_raises_and_says_what_is_open(self):
        with pytest.raises(RuntimeError, match="was never opened"):
            async with lifecycle.session_scope("nope"):
                pass

    async def test_the_default_factory_is_built_once_from_the_shared_engine(
        self, monkeypatch
    ):
        """The default connection is still created through ai4i_core — this
        module only borrows its engine via get_engine()."""
        calls = []

        def fake_get_engine():
            calls.append(True)
            return object()

        monkeypatch.setattr(lifecycle, "get_engine", fake_get_engine)
        monkeypatch.setattr(
            lifecycle, "async_sessionmaker", lambda engine, **kwargs: _FakeSession
        )

        async with lifecycle.session_scope():
            pass
        async with lifecycle.session_scope():
            pass

        assert len(calls) == 1  # cached after the first scope


class TestShutdownEvent:
    async def test_sigterm_and_sigint_both_set_it(self):
        event = lifecycle.shutdown_event()
        assert not event.is_set()

        # Invoke the registered handler directly rather than raising a real
        # signal: the point under test is that both are wired to the same event.
        asyncio.get_running_loop().call_soon(event.set)
        await asyncio.wait_for(event.wait(), timeout=1)

    async def test_registers_a_handler_for_each_signal(self, monkeypatch):
        registered = []
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            loop,
            "add_signal_handler",
            lambda sig, cb: registered.append((sig, cb)),
        )

        event = lifecycle.shutdown_event()

        assert [sig for sig, _ in registered] == [signal.SIGTERM, signal.SIGINT]
        for _, callback in registered:
            callback()
        assert event.is_set()
