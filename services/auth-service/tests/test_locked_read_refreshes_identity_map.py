"""Live-DB regression for the stale-identity-map bug (vipuldeveloper review,
PR #1491, on ApplicationService.create_application).

Bug scenario: TenantRepository.get_by_id_for_update / ApplicationRepository.
get_by_id_for_update take a real ``SELECT ... FOR UPDATE`` lock, but without
forcing a refresh, SQLAlchemy's identity map hands back the SAME in-memory
object for a row already loaded earlier in the same AsyncSession — the lock
is genuinely acquired against the DB row, but the Python attributes on that
object still hold whatever was read at the FIRST (unlocked) load. A mocked
unit test can't reproduce this: two AsyncMocks configured with different
return values are never "the same object" the way a real session's identity
map makes them, so this only reproduces against a real AsyncSession.

Reproduces the reviewer's live repro directly: load unlocked, mutate the row
out from under the session via a second, independent connection (simulating
a concurrent admin's PATCH .../budget commit), then take the FOR UPDATE lock
and assert the attribute actually changed.

Setup/cleanup rows are committed for real on their own connections (a
concurrent writer on a genuinely separate connection can't see an
uncommitted INSERT — READ COMMITTED just matches 0 rows, silently). The
actual repro (unlocked read -> concurrent write -> locked read) all happens
inside ONE transaction that is never committed early, matching a real
request's session lifecycle: one Session, one transaction, no intermediate
commit to accidentally expire-and-refresh attributes for us.
"""

import asyncio
import os
from pathlib import Path

import pytest

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

# Must happen before app.core.pii_crypto's lru_cache'd _cipher() is ever
# called (the tenants.email column encrypts on write) — conftest.py doesn't
# load the real .env, so PII_ENCRYPTION_KEY is unset under pytest otherwise.
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if dotenv_values is not None and _ENV_PATH.exists():
    _early_env = dotenv_values(_ENV_PATH)
    if _early_env.get("PII_ENCRYPTION_KEY"):
        os.environ.setdefault("PII_ENCRYPTION_KEY", _early_env["PII_ENCRYPTION_KEY"])

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # noqa: E402

from app.models.application import Application, ApplicationStatus  # noqa: E402
from app.models.tenant import Tenant, TenantStatus  # noqa: E402
from app.repositories.application_repository import ApplicationRepository  # noqa: E402
from app.repositories.tenant_repository import TenantRepository  # noqa: E402


# NOT app.core.config.settings.get_database_url(): conftest.py sets
# DATABASE_URL=sqlite+aiosqlite:///test.db as a test default, and
# get_database_url() checks settings.database_url before the AUTH_DB_*
# fallback chain — under pytest that always wins, silently resolving to the
# sqlite test DB instead of the real dev Postgres instance. Same env-override
# trap as migration_registry.py's load_dotenv(override=True); same fix as
# test_migration_application_permissions_seed.py: read the .env file
# directly instead of going through the settings object.
def _db_url() -> str:
    if dotenv_values is None or not _ENV_PATH.exists():
        return ""
    env = dotenv_values(_ENV_PATH)
    required = ("AUTH_DB_HOST", "AUTH_DB_PORT", "AUTH_DB_USER", "AUTH_DB_PASSWORD", "AUTH_SERVICE_DB_NAME")
    if any(not env.get(k) for k in required):
        return ""
    return (
        f"postgresql+asyncpg://{env['AUTH_DB_USER']}:{env['AUTH_DB_PASSWORD']}"
        f"@{env['AUTH_DB_HOST']}:{env['AUTH_DB_PORT']}/{env['AUTH_SERVICE_DB_NAME']}"
    )


async def _db_reachable(url: str) -> bool:
    try:
        engine = create_async_engine(url)
        async with engine.connect():
            pass
        await engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture()
def db_url():
    url = _db_url()
    if not url:
        pytest.skip("no auth-service .env with AUTH_DB_* vars found")
    if not asyncio.run(_db_reachable(url)):
        pytest.skip(f"could not connect to dev DB at {url}")
    return url


class TestTenantLockedReadRefreshesIdentityMap:
    @pytest.mark.asyncio
    async def test_get_by_id_for_update_sees_a_concurrent_commit(self, db_url) -> None:
        engine = create_async_engine(db_url)
        writer_engine = create_async_engine(db_url)
        tenant_id = None
        try:
            async with AsyncSession(engine, expire_on_commit=False) as setup_session:
                tenant = Tenant(
                    name="Locked-Read Test Contact",
                    organisation="Locked-Read Test Org",
                    email="locked-read-test@example.invalid",
                    status=TenantStatus.ACTIVE,
                    allocated_budget=None,
                )
                setup_session.add(tenant)
                await setup_session.commit()
                tenant_id = tenant.id

            async with AsyncSession(engine) as session:
                async with session.begin():
                    repo = TenantRepository(session)

                    # Unlocked read — populates the identity map, exactly
                    # like ApplicationService._load_tenant_or_404.
                    loaded = await repo.get_by_id(tenant_id)
                    assert loaded.allocated_budget is None

                    # A concurrent PATCH .../budget commits for real, on a
                    # genuinely separate connection, between the two reads.
                    async with writer_engine.begin() as writer_conn:
                        await writer_conn.execute(
                            text(
                                "UPDATE tenants SET allocated_budget = :budget WHERE id = :id"
                            ),
                            {"budget": "777.00", "id": tenant_id},
                        )

                    # The locked read must see the committed revision.
                    locked = await repo.get_by_id_for_update(tenant_id)

                    assert locked is loaded, (
                        "test invalid if these aren't the same identity-mapped "
                        "object — that's the exact condition this bug depends on"
                    )
                    assert str(locked.allocated_budget) == "777.00", (
                        "get_by_id_for_update returned a lock without refreshing "
                        "attributes from the just-locked row — the exact bug the "
                        "reviewer found live"
                    )
        finally:
            if tenant_id is not None:
                async with writer_engine.begin() as cleanup_conn:
                    await cleanup_conn.execute(
                        text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
                    )
            await engine.dispose()
            await writer_engine.dispose()


class TestApplicationLockedReadRefreshesIdentityMap:
    @pytest.mark.asyncio
    async def test_get_by_id_for_update_sees_a_concurrent_commit(self, db_url) -> None:
        engine = create_async_engine(db_url)
        writer_engine = create_async_engine(db_url)
        tenant_id = None
        application_id = None
        try:
            async with AsyncSession(engine, expire_on_commit=False) as setup_session:
                tenant = Tenant(
                    name="App Locked-Read Test Contact",
                    organisation="App Locked-Read Test Org",
                    email="app-locked-read-test@example.invalid",
                    status=TenantStatus.ACTIVE,
                    allocated_budget=None,
                )
                setup_session.add(tenant)
                await setup_session.flush()

                application = Application(
                    tenant_id=tenant.id,
                    name="Locked-Read Test App",
                    status=ApplicationStatus.ACTIVE,
                    allocated_budget=None,
                )
                setup_session.add(application)
                await setup_session.commit()
                tenant_id = tenant.id
                application_id = application.id

            async with AsyncSession(engine) as session:
                async with session.begin():
                    repo = ApplicationRepository(session)

                    loaded = await repo.get_by_id(application_id)
                    assert loaded.allocated_budget is None

                    # Simulates a concurrent tenant-budget revision cascading
                    # a recomputed ceiling into this Application row — same
                    # shape api_key_service.create_api_key reads afterward.
                    async with writer_engine.begin() as writer_conn:
                        await writer_conn.execute(
                            text(
                                "UPDATE applications SET allocated_budget = :budget "
                                "WHERE id = :id"
                            ),
                            {"budget": "1000.00", "id": application_id},
                        )

                    locked = await repo.get_by_id_for_update(application_id)

                    assert locked is loaded
                    assert str(locked.allocated_budget) == "1000.00", (
                        "ApplicationRepository.get_by_id_for_update returned a "
                        "lock without refreshing attributes — the same bug "
                        "class api_key_service.create_api_key would silently "
                        "inherit for its allocated_budget derivation"
                    )
        finally:
            async with writer_engine.begin() as cleanup_conn:
                if application_id is not None:
                    await cleanup_conn.execute(
                        text("DELETE FROM applications WHERE id = :id"),
                        {"id": application_id},
                    )
                if tenant_id is not None:
                    await cleanup_conn.execute(
                        text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
                    )
            await engine.dispose()
            await writer_engine.dispose()
