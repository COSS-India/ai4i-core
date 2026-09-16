"""created_by audit-trail coverage — a code-review finding that several
admin-triggered inserts (User via provision_user, UserRole via assign_role,
RolePermission via insert_role_permissions) never set created_by, unlike
Application/Tenant/APIKey which already did, and that some self-service
inserts (UserCredentials, RefreshToken) should match the established
persist_token_verification convention of self-referential created_by=user_id.

Each test here pins one insert site's created_by wiring so a later refactor
that drops the kwarg on its way through a call chain is caught immediately,
not discovered later by an actual audit-trail gap in production data.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

# Must happen before app.core.pii_crypto's lru_cache'd _cipher() is ever
# called (the tenants.email column encrypts on write) — conftest.py doesn't
# load the real .env, so PII_ENCRYPTION_KEY is unset under pytest otherwise.
# Same pattern as test_locked_read_refreshes_identity_map.py.
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if dotenv_values is not None and _ENV_PATH.exists():
    _early_env = dotenv_values(_ENV_PATH)
    if _early_env.get("PII_ENCRYPTION_KEY"):
        os.environ.setdefault("PII_ENCRYPTION_KEY", _early_env["PII_ENCRYPTION_KEY"])

from app.core.constants import RoleName  # noqa: E402
from app.models.role import RolePermission, UserRole  # noqa: E402
from app.models.tenant import Tenant, TenantStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.role_service import RoleService  # noqa: E402
from app.services.tenant_service import TenantService  # noqa: E402


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
    from sqlalchemy.ext.asyncio import create_async_engine

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


def _admin_user() -> User:
    return User(id=uuid4(), email="admin@example.invalid", username=uuid4().hex[:12])


def _active_tenant(id: int = 1) -> Tenant:
    return Tenant(
        id=id, name="Acme", organisation="Acme",
        email="test-contact@example.invalid", status=TenantStatus.ACTIVE,
    )


# ── TenantService.provision_user — User.created_by + assign_role(created_by=) ──

def _tenant_svc() -> TenantService:
    tenant_repo = AsyncMock()
    tenant_repo.get_by_email = AsyncMock(return_value=None)
    tenant_repo.get_by_organisation = AsyncMock(return_value=None)
    tenant_repo.create = AsyncMock()
    tenant_repo.refresh = AsyncMock()
    user_repo = AsyncMock()
    user_repo.email_exists = AsyncMock(return_value=False)
    user_repo.get_by_username = AsyncMock(return_value=None)
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=AsyncMock(),
        verification_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        token_service=AsyncMock(),
        email_client=AsyncMock(),
    )


class TestProvisionUserSetsCreatedBy:
    @pytest.mark.asyncio
    async def test_provision_user_sets_created_by_on_user_and_role_assignment(self) -> None:
        svc = _tenant_svc()
        admin = _admin_user()

        await svc.provision_user(
            email="invitee@example.invalid",
            username="invitee",
            tenant_id="1",
            role_name=RoleName.USER,
            created_by=admin.id,
        )

        svc._users.create.assert_awaited_once()
        created_user = svc._users.create.await_args.args[0]
        assert created_user.created_by == admin.id

        svc._roles.assign_role.assert_awaited_once_with(
            created_user.id, RoleName.USER, created_by=admin.id
        )

    @pytest.mark.asyncio
    async def test_provision_user_created_by_defaults_to_none(self) -> None:
        """No admin actor passed -> created_by stays None, not silently
        defaulted to something misleading."""
        svc = _tenant_svc()

        await svc.provision_user(
            email="invitee2@example.invalid",
            username="invitee2",
            tenant_id="1",
            role_name=RoleName.USER,
        )

        created_user = svc._users.create.await_args.args[0]
        assert created_user.created_by is None


class TestCreateTenantAndCreateTenantUserPassCreatedBy:
    @pytest.mark.asyncio
    async def test_create_tenant_passes_admin_id_to_provision_user(self) -> None:
        svc = _tenant_svc()
        svc.provision_user = AsyncMock()
        svc._allocate_unique_username = AsyncMock(return_value="jane.doe")
        admin = _admin_user()

        body = MagicMock()
        body.email = "contact@example.invalid"
        body.organisation = "Acme Corp"
        body.contact_name = "Jane Doe"
        body.phone_number = "+919876543210"
        body.plan_id = None
        body.tier_id = None
        body.allocated_budget = None
        body.budget_effective_from = None
        body.budget_effective_to = None

        await svc.create_tenant(body, admin, MagicMock())

        svc.provision_user.assert_awaited_once()
        assert svc.provision_user.await_args.kwargs["created_by"] == admin.id

    @pytest.mark.asyncio
    async def test_create_tenant_user_passes_admin_id_to_provision_user(self) -> None:
        svc = _tenant_svc()
        svc.enforce_scope = AsyncMock()
        svc._deny_moderator = AsyncMock()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_active_tenant())
        svc.provision_user = AsyncMock(return_value=("user-id-123", "setup-token-abc"))
        admin = _admin_user()

        body = MagicMock()
        body.email = "invitee3@example.invalid"
        body.full_name = "Invitee Three"
        body.phone_number = None
        body.role.value = "TENANT USER"
        body.role = MagicMock()
        body.role.value = "TENANT USER"

        from unittest.mock import patch

        with patch(
            "app.services.tenant_service.allocate_unique_username",
            new_callable=AsyncMock,
            return_value="invitee3",
        ):
            await svc.create_tenant_user(admin, 1, body, MagicMock())

        svc.provision_user.assert_awaited_once()
        assert svc.provision_user.await_args.kwargs["created_by"] == admin.id


class TestUpdateTenantUserRoleChangePassesCreatedBy:
    @pytest.mark.asyncio
    async def test_role_change_passes_admin_id_through_to_assign_role(self) -> None:
        svc = _tenant_svc()
        svc.enforce_scope = AsyncMock()
        svc._deny_moderator = AsyncMock()
        target = User(id=uuid4(), email="target@example.invalid", username="target", tenant_id=1)
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        svc._users.get_by_id_for_tenant = AsyncMock(return_value=target)
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()
        admin = _admin_user()

        body = MagicMock()
        body.model_dump.return_value = {"role": "TENANT_ADMIN"}

        await svc.update_tenant_user(admin, 1, target.id, body)

        svc._roles.assign_role.assert_awaited_once()
        _, kwargs = svc._roles.assign_role.await_args
        assert kwargs["created_by"] == admin.id


# ── RoleService.assign_role -> RoleRepository.assign_role(created_by=) ──

class TestRoleServiceAssignRolePropagatesCreatedBy:
    @pytest.mark.asyncio
    async def test_created_by_reaches_the_repository_call(self) -> None:
        role_repo = AsyncMock()
        role_repo.get_role_by_name = AsyncMock(return_value=MagicMock(id=5))
        role_repo.get_user_role_record = AsyncMock(return_value=None)
        svc = RoleService(
            role_repo=role_repo,
            tenant_repo=AsyncMock(),
            user_repo=AsyncMock(),
        )
        admin = _admin_user()
        target_user_id = uuid4()

        await svc.assign_role(target_user_id, RoleName.USER, created_by=admin.id)

        role_repo.assign_role.assert_awaited_once_with(target_user_id, 5, created_by=admin.id)


class TestAssignGuestInferenceServicesPropagatesCreatedBy:
    @pytest.mark.asyncio
    async def test_created_by_reaches_insert_role_permissions(self) -> None:
        role_repo = AsyncMock()
        perm = MagicMock(id=7, resource="nmt.inference", action="inference")
        role_repo.list_inference_permissions = AsyncMock(return_value=[perm])
        role_repo.get_role_by_name = AsyncMock(return_value=MagicMock(id=9))
        svc = RoleService(
            role_repo=role_repo,
            tenant_repo=AsyncMock(),
            user_repo=AsyncMock(),
        )
        admin = _admin_user()

        await svc.assign_guest_inference_services(["nmt.inference"], created_by=admin.id)

        role_repo.insert_role_permissions.assert_awaited_once()
        args, kwargs = role_repo.insert_role_permissions.await_args
        assert kwargs["created_by"] == admin.id


# ── RoleRepository.assign_role / insert_role_permissions actually set the field ──

class TestRoleRepositoryModelsCarryCreatedBy:
    def test_user_role_model_accepts_created_by(self) -> None:
        creator = uuid4()
        row = UserRole(user_id=uuid4(), role_id=1, created_by=creator)
        assert row.created_by == creator

    def test_role_permission_model_accepts_created_by(self) -> None:
        creator = uuid4()
        row = RolePermission(role_id=1, permission_id=2, created_by=creator)
        assert row.created_by == creator


# ── AuthService: self-registration / setup-link flows set created_by=user.id ──

def _auth_svc(**overrides) -> AuthService:
    kwargs = dict(
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        token_service=MagicMock(),
        credentials_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        verification_repo=AsyncMock(),
        tenant_repo=AsyncMock(),
        email_client=MagicMock(),
        cache_service=AsyncMock(),
    )
    kwargs.update(overrides)
    svc = AuthService(**kwargs)
    svc._tokens.create_verify_token.return_value = "verify-token"
    return svc


class TestRegisterSetsCredentialsCreatedBy:
    @pytest.mark.asyncio
    async def test_register_sets_credentials_created_by_to_self(self) -> None:
        svc = _auth_svc()
        svc._users.email_exists = AsyncMock(return_value=False)
        svc._users.list_usernames_in_collision_family = AsyncMock(return_value=[])
        svc._users.create = AsyncMock()
        svc._users.commit = AsyncMock()

        await svc.register(
            email="newuser@example.invalid",
            password="Str0ng!Passw0rd",
            confirm_password="Str0ng!Passw0rd",
        )

        svc._credentials.create.assert_awaited_once()
        creds = svc._credentials.create.await_args.args[0]
        created_user = svc._users.create.await_args.args[0]
        assert creds.created_by == created_user.id


class TestSetPasswordWithTokenSetsCredentialsCreatedBy:
    @pytest.mark.asyncio
    async def test_set_password_with_token_sets_credentials_created_by_to_self(self) -> None:
        svc = _auth_svc()
        target_user = User(
            id=uuid4(), email="invited@example.invalid", username="invited", is_active=False
        )
        svc._resolve_verified_token = AsyncMock(return_value=(MagicMock(), target_user))
        svc._assert_user_tenant_onboarding = AsyncMock()
        svc._activate_pending_tenant_for_contact_admin = AsyncMock()
        svc._verifications.deactivate = AsyncMock()
        svc._users.commit = AsyncMock()

        await svc.set_password_with_token(
            token="setup-token-abc",
            new_password="Str0ng!Passw0rd",
            confirm_password="Str0ng!Passw0rd",
        )

        svc._credentials.create.assert_awaited_once()
        creds = svc._credentials.create.await_args.args[0]
        assert creds.created_by == target_user.id


# ── RefreshTokenRepository.upsert: raw SQL insert, verified against a real DB ──

class TestRefreshTokenUpsertSetsCreatedBy:
    @pytest.mark.asyncio
    async def test_upsert_sets_created_by_on_first_insert(self, db_url) -> None:
        """A raw pg_insert().values() bypasses ORM-level default handling
        entirely — a mock can't tell us whether created_by is actually in
        the INSERT's column list, only a real row can."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from app.models.tenant import Tenant, TenantStatus
        from app.models.user import User as UserModel
        from app.repositories.refresh_token_repository import RefreshTokenRepository

        engine = create_async_engine(db_url)
        tenant_id = None
        user_id = None
        unique = uuid4().hex[:12]
        try:
            async with AsyncSession(engine, expire_on_commit=False) as setup:
                tenant = Tenant(
                    name="Refresh-Token Test Contact",
                    organisation=f"Refresh-Token Test Org {unique}",
                    email=f"refresh-token-test-{unique}@example.invalid",
                    status=TenantStatus.ACTIVE,
                )
                setup.add(tenant)
                await setup.flush()
                user = UserModel(
                    email=f"refresh-token-test-user-{unique}@example.invalid",
                    username=f"refresh-token-test-user-{unique}",
                    tenant_id=tenant.id,
                    is_active=True,
                )
                setup.add(user)
                await setup.commit()
                tenant_id = tenant.id
                user_id = user.id

            async with AsyncSession(engine) as session:
                repo = RefreshTokenRepository(session)
                token = await repo.upsert(user_id, "test-refresh-token-value")
                assert token.created_by == user_id
                await session.commit()
        finally:
            async with engine.begin() as cleanup:
                if user_id is not None:
                    await cleanup.execute(
                        text("DELETE FROM refresh WHERE user_id = :id"), {"id": user_id}
                    )
                    await cleanup.execute(
                        text("DELETE FROM users WHERE id = :id"), {"id": user_id}
                    )
                if tenant_id is not None:
                    await cleanup.execute(
                        text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
                    )
            await engine.dispose()
