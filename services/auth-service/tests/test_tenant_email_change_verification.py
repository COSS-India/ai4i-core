"""Unit tests for Institution Admin email change on non-PENDING tenants (AI4IDS-3401).

update_tenant holds the change and sends the existing verify-email message to
the new address; /auth/verify-email (EMAIL_CHANGE token) applies it. Email
edits are locked while SUSPENDED/DEACTIVATED, and the pending address is
surfaced on reads via resolve_pending_emails.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jwt.exceptions import PyJWTError
from pydantic import ValidationError as PydanticValidationError

from app.core.constants import TokenType
from app.core.exceptions import DuplicateEntityError, TokenInvalidError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.repositories.verification_repository import VerificationRepository
from app.schemas.tenant import TenantUpdate
from app.services.auth_service import AuthService
from app.services.tenant_service import TenantService
from app.services.token_service import TokenPayload


def _tenant(
    email: str = "old@tenant.com", id: int = 1, status: TenantStatus = TenantStatus.ACTIVE
) -> Tenant:
    return Tenant(id=id, name="Acme", organisation="Acme", email=email, status=status)


def _user(email: str, tenant_id=1) -> User:
    return User(id=uuid4(), email=email, username=uuid4().hex[:12], tenant_id=tenant_id)


def _body(**fields) -> MagicMock:
    body = MagicMock()
    body.model_dump.return_value = fields
    return body


def _tenant_service() -> TenantService:
    tenant_repo = MagicMock()
    for name in ("get_by_id", "update", "commit", "refresh"):
        setattr(tenant_repo, name, AsyncMock())
    tenant_repo.get_by_email = AsyncMock(return_value=None)
    tenant_repo.get_by_organisation = AsyncMock(return_value=None)
    user_repo = MagicMock()
    user_repo.get_by_email = AsyncMock(return_value=None)
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=[])
    verifications = MagicMock()
    verifications.create = AsyncMock()
    verifications.deactivate_email_changes_for_tenant = AsyncMock()
    tokens = MagicMock()
    tokens.create_email_change_token.return_value = "change-token"
    svc = TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=verifications,
        credentials_repo=MagicMock(),
        token_service=tokens,
        email_client=MagicMock(),
    )
    svc.enforce_scope = AsyncMock()
    return svc


class TestTenantUpdateEmailFormat:
    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            TenantUpdate(email="not-an-email")


class TestUpdateTenantEmailChange:
    @pytest.mark.asyncio
    async def test_new_email_held_and_verification_sent(self) -> None:
        svc = _tenant_service()
        tenant = _tenant()
        admin = _user("old@tenant.com")
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: admin if e == "old@tenant.com" else None
        )

        with patch("app.services.tenant_service.enqueue_email") as enqueue, \
             patch("app.services.tenant_service.render_verify_email") as render:
            result = await svc.update_tenant(
                MagicMock(id=uuid4()), 1,
                _body(email="new@tenant.com", contact_name="Jane"),
                background_tasks=MagicMock(),
            )
            enqueue.call_args.args[2]()  # invoke the render factory

        staged = svc._tenants.update.await_args.args[1]
        assert "email" not in staged and staged["name"] == "Jane"  # other fields still saved
        assert admin.email == "old@tenant.com"                     # not applied yet
        svc._tokens.create_email_change_token.assert_called_once_with(
            user_id=str(admin.id), new_email="new@tenant.com", tenant_id=1, tenant_only=False
        )
        svc._verifications.deactivate_email_changes_for_tenant.assert_awaited_once_with(1)
        render.assert_called_once_with(admin, "change-token", to="new@tenant.com")
        assert result.pending_email == "new@tenant.com"
        assert result.verification_sent is True

    @pytest.mark.asyncio
    async def test_existing_institution_admin_applied_without_verification(self) -> None:
        svc = _tenant_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.get_by_email = AsyncMock(return_value=_user("other.admin@tenant.com"))

        with patch("app.services.tenant_service.enqueue_email") as enqueue:
            result = await svc.update_tenant(
                MagicMock(id=uuid4()), 1, _body(email="other.admin@tenant.com"),
                background_tasks=MagicMock(),
            )

        assert svc._tenants.update.await_args.args[1]["email"] == "other.admin@tenant.com"
        # A direct change still supersedes any earlier pending request.
        svc._verifications.deactivate_email_changes_for_tenant.assert_awaited_once_with(1)
        svc._tokens.create_email_change_token.assert_not_called()
        enqueue.assert_not_called()
        assert result.pending_email is None
        assert result.verification_sent is False

    @pytest.mark.asyncio
    async def test_no_contact_user_sends_tenant_only_verification(self) -> None:
        """tenant.email no longer maps to a user (contact's email edited or
        contact deleted): still verify, but only tenant.email will change."""
        svc = _tenant_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())  # no user for old email
        requester = MagicMock(id=uuid4())

        with patch("app.services.tenant_service.enqueue_email") as enqueue, \
             patch("app.services.tenant_service.render_verify_email") as render:
            result = await svc.update_tenant(requester, 1, _body(email="new@tenant.com"),
                                             background_tasks=MagicMock())
            enqueue.call_args.args[2]()

        assert "email" not in svc._tenants.update.await_args.args[1]
        svc._tokens.create_email_change_token.assert_called_once_with(
            user_id=str(requester.id), new_email="new@tenant.com", tenant_id=1, tenant_only=True
        )
        greeted, token = render.call_args.args
        assert greeted.full_name == "Acme" and token == "change-token"
        assert render.call_args.kwargs == {"to": "new@tenant.com"}
        assert result.pending_email == "new@tenant.com"
        assert result.verification_sent is True

    @pytest.mark.asyncio
    async def test_pending_tenant_does_not_repoint_to_existing_admin(self) -> None:
        """PENDING: the existing-admin shortcut is skipped (it would leave the
        contact's activation link live) — collision with the contact → 409."""
        svc = _tenant_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(status=TenantStatus.PENDING))
        contact, other_admin = _user("old@tenant.com"), _user("other.admin@tenant.com")
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: contact if e == "old@tenant.com" else other_admin
        )

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(MagicMock(id=uuid4()), 1, _body(email="other.admin@tenant.com"),
                                    background_tasks=MagicMock())
        assert exc.value.detail["code"] == "DUPLICATE_EMAIL"
        svc._tenants.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_of_another_tenant_is_not_treated_as_existing_admin(self) -> None:
        svc = _tenant_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.get_by_email = AsyncMock(return_value=_user("x@other.com", tenant_id=2))

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(MagicMock(id=uuid4()), 1, _body(email="x@other.com"),
                                    background_tasks=MagicMock())
        assert exc.value.detail["code"] == "DUPLICATE_EMAIL"
        svc._tenants.commit.assert_not_awaited()


class TestEmailEditLockedStatuses:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("locked", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED])
    async def test_email_change_rejected(self, locked) -> None:
        svc = _tenant_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(status=locked))

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(MagicMock(id=uuid4()), 1, _body(email="new@tenant.com"),
                                    background_tasks=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "TENANT_EMAIL_EDIT_NOT_ALLOWED"
        svc._tenants.update.assert_not_awaited()
        svc._tokens.create_email_change_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_other_fields_still_editable_with_unchanged_email(self) -> None:
        """The Edit form echoes the current email back — that must not trip the lock."""
        svc = _tenant_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(status=TenantStatus.SUSPENDED))

        await svc.update_tenant(MagicMock(id=uuid4()), 1,
                                _body(email="OLD@tenant.com", contact_name="Jane"),
                                background_tasks=MagicMock())

        assert svc._tenants.update.await_args.args[1]["name"] == "Jane"
        svc._tenants.commit.assert_awaited_once()


class TestResolvePendingEmails:
    @pytest.mark.asyncio
    async def test_skips_pending_tenants(self) -> None:
        svc = _tenant_service()
        active = _tenant("a@one.com", id=1)
        onboarding = _tenant("b@two.com", id=2, status=TenantStatus.PENDING)
        svc._verifications.get_pending_email_changes = AsyncMock(return_value={1: "new@one.com"})

        result = await svc.resolve_pending_emails([active, onboarding])

        assert result == {1: "new@one.com"}
        svc._verifications.get_pending_email_changes.assert_awaited_once_with([1])

    def test_pending_email_masked_in_response(self) -> None:
        tenant = _tenant()
        tenant.created_at = datetime.now(timezone.utc)
        data = TenantService.build_tenant_response(tenant, pending_email="newperson@tenant.com")
        assert data["pending_email"] and data["pending_email"] != "newperson@tenant.com"
        assert "*" in data["pending_email"]


def _auth_service() -> AuthService:
    users = MagicMock()
    users.get_by_id = AsyncMock()
    users.get_by_email = AsyncMock(return_value=None)
    users.commit = AsyncMock()
    tenants = MagicMock()
    tenants.get_by_id = AsyncMock()
    tenants.get_by_email = AsyncMock(return_value=None)
    verifications = MagicMock()
    verifications.get_by_token = AsyncMock()
    verifications.deactivate = AsyncMock()
    return AuthService(
        user_repo=users,
        role_service=MagicMock(),
        token_service=MagicMock(),
        credentials_repo=MagicMock(),
        refresh_token_repo=MagicMock(),
        verification_repo=verifications,
        tenant_repo=tenants,
        email_client=MagicMock(),
        cache_service=MagicMock(),
    )


def _wire_token(
    svc: AuthService, owner: User, tenant: Tenant, new_email: str, tenant_only: bool = False
):
    svc._tokens.validate_token.return_value = TokenPayload(
        sub=str(owner.id), token_type=TokenType.EMAIL_CHANGE,
        tenant_id=str(tenant.id), email=new_email, tenant_only=tenant_only,
    )
    token_obj = MagicMock(is_active=True)
    svc._verifications.get_by_token = AsyncMock(return_value=token_obj)
    svc._users.get_by_id = AsyncMock(return_value=owner)
    svc._tenants.get_by_id = AsyncMock(return_value=tenant)
    return token_obj


class TestConfirmTenantEmailChange:
    @pytest.mark.asyncio
    async def test_verify_email_applies_change(self) -> None:
        svc = _auth_service()
        tenant, admin = _tenant(), _user("old@tenant.com")
        token_obj = _wire_token(svc, admin, tenant, "new@tenant.com")

        email_changed = await svc.verify_email_token("tok")

        assert email_changed is True
        assert tenant.email == "new@tenant.com"
        assert admin.email == "new@tenant.com"
        svc._verifications.deactivate.assert_awaited_once_with(token_obj)
        svc._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_when_tenant_email_moved_on(self) -> None:
        svc = _auth_service()
        tenant, admin = _tenant("someone.else@tenant.com"), _user("old@tenant.com")
        _wire_token(svc, admin, tenant, "new@tenant.com")

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refused_while_tenant_suspended(self) -> None:
        svc = _auth_service()
        tenant, admin = _tenant(status=TenantStatus.SUSPENDED), _user("old@tenant.com")
        _wire_token(svc, admin, tenant, "new@tenant.com")

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        assert tenant.email == "old@tenant.com"
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_address_taken_since_request_raises_409(self) -> None:
        svc = _auth_service()
        tenant, admin = _tenant(), _user("old@tenant.com")
        _wire_token(svc, admin, tenant, "new@tenant.com")
        svc._users.get_by_email = AsyncMock(return_value=_user("new@tenant.com", tenant_id=7))

        with pytest.raises(DuplicateEntityError):
            await svc.verify_email_token("tok")
        assert tenant.email == "old@tenant.com"
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tenant_only_updates_tenant_email_alone(self) -> None:
        svc = _auth_service()
        tenant = _tenant("orphan@tenant.com")
        requester = _user("admin@platform.com", tenant_id=None)
        _wire_token(svc, requester, tenant, "new@tenant.com", tenant_only=True)
        # A same-tenant user holding the address is harmless when no login moves.
        svc._users.get_by_email = AsyncMock(return_value=_user("new@tenant.com", tenant_id=1))

        assert await svc.verify_email_token("tok") is True

        assert tenant.email == "new@tenant.com"
        assert requester.email == "admin@platform.com"  # no user re-aligned
        svc._users.get_by_id.assert_not_awaited()
        svc._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tenant_only_cross_tenant_holder_raises_409(self) -> None:
        svc = _auth_service()
        tenant = _tenant("orphan@tenant.com")
        requester = _user("admin@platform.com", tenant_id=None)
        _wire_token(svc, requester, tenant, "new@tenant.com", tenant_only=True)
        svc._users.get_by_email = AsyncMock(return_value=_user("new@tenant.com", tenant_id=7))

        with pytest.raises(DuplicateEntityError):
            await svc.verify_email_token("tok")
        assert tenant.email == "orphan@tenant.com"

    @pytest.mark.asyncio
    async def test_used_link_rejected(self) -> None:
        svc = _auth_service()
        tenant, admin = _tenant(), _user("old@tenant.com")
        token_obj = _wire_token(svc, admin, tenant, "new@tenant.com")
        token_obj.is_active = False

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")


_CLAIMS = {
    "setup": {"type": TokenType.SETUP, "email": "old@tenant.com"},
    "t1": {"type": TokenType.EMAIL_CHANGE, "email": "new@one.com", "tenant_id": "1"},
    "t2": {"type": TokenType.EMAIL_CHANGE, "email": "new@two.com", "tenant_id": "2"},
}


def _decode(token, kid):
    if token == "bad":
        raise PyJWTError("bad signature")
    return _CLAIMS[token]


def _repo(rows) -> VerificationRepository:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    ))
    db.flush = AsyncMock()
    return VerificationRepository(db)


@patch("app.repositories.verification_repository._decode_stored_token", side_effect=_decode)
@patch("app.repositories.verification_repository.jwt.get_unverified_header",
       return_value={"kid": "k1"})
class TestEmailChangeTokenLookup:
    @pytest.mark.asyncio
    async def test_pending_maps_requested_tenants_only(self, *_) -> None:
        rows = [MagicMock(token=t, created_by=uuid4()) for t in ("setup", "bad", "t1", "t2")]
        assert await _repo(rows).get_pending_email_changes([1, 3]) == {1: "new@one.com"}

    @pytest.mark.asyncio
    async def test_no_tenants_skips_query(self, *_) -> None:
        repo = _repo([])
        assert await repo.get_pending_email_changes([]) == {}
        repo._db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deactivate_for_tenant_leaves_other_tokens(self, *_) -> None:
        rows = {t: MagicMock(token=t, created_by=uuid4(), is_active=True) for t in ("setup", "t1", "t2")}
        await _repo(list(rows.values())).deactivate_email_changes_for_tenant(1)
        assert rows["t1"].is_active is False
        assert rows["t2"].is_active is True and rows["setup"].is_active is True
