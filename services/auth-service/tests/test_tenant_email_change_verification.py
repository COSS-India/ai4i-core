"""Unit tests for Institution Admin email change on non-PENDING tenants (AI4IDS-3401).

update_tenant stores the new address in tenants.pending_email (until the link
expires) and sends the email_change message; /auth/verify-email (EMAIL_CHANGE
token) applies it and hands the contact account over (old password and
sessions revoked, setup link to the new address). Email edits are locked while
SUSPENDED/DEACTIVATED, for the Default Organisation, and when the contact is a
platform administrator.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError as PydanticValidationError

from app.core.constants import TokenType
from app.core.exceptions import DuplicateEntityError, TokenInvalidError, ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.schemas.tenant import TenantUpdate
from app.services.auth_service import AuthService
from app.services.tenant_service import TenantService
from app.services.token_service import TokenPayload


def _tenant(
    email: str = "old@tenant.com",
    id: int = 1,
    status: TenantStatus = TenantStatus.ACTIVE,
    pending_email=None,
    organisation: str = "Acme",
    pending_expires_in: timedelta = timedelta(hours=1),
) -> Tenant:
    return Tenant(id=id, name="Acme", organisation=organisation, email=email, status=status,
                  pending_email=pending_email,
                  pending_email_expires_at=(datetime.now(timezone.utc) + pending_expires_in
                                            if pending_email else None))


def _user(email: str, tenant_id=1, is_active: bool = True) -> User:
    return User(id=uuid4(), email=email, username=uuid4().hex[:12], tenant_id=tenant_id,
                is_active=is_active)


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


def _staged(svc: TenantService) -> dict:
    return svc._tenants.update.await_args.args[1]


class TestTenantUpdateEmailFormat:
    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            TenantUpdate(email="not-an-email")


class TestUpdateTenantEmailChange:
    @pytest.mark.asyncio
    async def test_new_email_held_and_verification_sent(self) -> None:
        svc = _tenant_service()
        admin = _user("old@tenant.com")
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: admin if e == "old@tenant.com" else None
        )
        requester = MagicMock(id=uuid4())

        with patch("app.services.tenant_service.enqueue_email") as enqueue, \
             patch("app.services.tenant_service.render_email_change") as render:
            _, link_sent = await svc.update_tenant(
                requester, 1,
                _body(email="new@tenant.com", contact_name="Jane"),
                background_tasks=MagicMock(),
            )
            enqueue.call_args.args[2]()  # invoke the render factory

        staged = _staged(svc)
        assert "email" not in staged and staged["name"] == "Jane"  # other fields still saved
        assert staged["pending_email"] == "new@tenant.com"
        assert staged["pending_email_expires_at"] > datetime.now(timezone.utc)
        assert admin.email == "old@tenant.com"                     # not applied yet
        svc._tokens.create_email_change_token.assert_called_once_with(
            user_id=str(requester.id), new_email="new@tenant.com", tenant_id=1
        )
        render.assert_called_once_with(
            "new@tenant.com", "Acme", "change-token", sends_setup_link=True
        )
        assert link_sent is True

    @pytest.mark.asyncio
    async def test_existing_institution_admin_applied_without_verification(self) -> None:
        svc = _tenant_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(pending_email="older@tenant.com"))
        svc._users.get_by_email = AsyncMock(return_value=_user("other.admin@tenant.com"))

        with patch("app.services.tenant_service.enqueue_email") as enqueue:
            _, link_sent = await svc.update_tenant(
                MagicMock(id=uuid4()), 1, _body(email="other.admin@tenant.com"),
                background_tasks=MagicMock(),
            )

        assert _staged(svc)["email"] == "other.admin@tenant.com"
        assert _staged(svc)["pending_email"] is None  # earlier request dropped
        assert _staged(svc)["pending_email_expires_at"] is None
        svc._tokens.create_email_change_token.assert_not_called()
        enqueue.assert_not_called()
        assert link_sent is False

    @pytest.mark.asyncio
    async def test_deactivated_admin_does_not_qualify_for_direct_change(self) -> None:
        """A deactivated Tenant Admin is not an existing admin — verify instead."""
        svc = _tenant_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        contact = _user("old@tenant.com")
        inactive_admin = _user("former.admin@tenant.com", is_active=False)
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: contact if e == "old@tenant.com" else inactive_admin
        )

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(MagicMock(id=uuid4()), 1,
                                    _body(email="former.admin@tenant.com"),
                                    background_tasks=MagicMock())
        # Verify path would move the contact onto an address another user holds.
        assert exc.value.detail["code"] == "DUPLICATE_EMAIL"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_contact_user_still_sends_verification(self) -> None:
        """tenant.email no longer maps to a user (contact's email edited or
        contact deleted): still verify, but only tenant.email will change."""
        svc = _tenant_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())  # no user for old email
        requester = MagicMock(id=uuid4())

        with patch("app.services.tenant_service.enqueue_email") as enqueue, \
             patch("app.services.tenant_service.render_email_change") as render:
            _, link_sent = await svc.update_tenant(requester, 1, _body(email="new@tenant.com"),
                                                   background_tasks=MagicMock())
            enqueue.call_args.args[2]()

        assert "email" not in _staged(svc)
        assert _staged(svc)["pending_email"] == "new@tenant.com"
        svc._tokens.create_email_change_token.assert_called_once_with(
            user_id=str(requester.id), new_email="new@tenant.com", tenant_id=1
        )
        render.assert_called_once_with(
            "new@tenant.com", "Acme", "change-token", sends_setup_link=False
        )
        assert link_sent is True

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


class TestProtectedContacts:
    @pytest.mark.asyncio
    async def test_default_organisation_email_cannot_change(self) -> None:
        """Its contact is the seeded platform admin - never hand that over."""
        svc = _tenant_service()
        svc._tenants.get_by_id = AsyncMock(
            return_value=_tenant("admin@ai4inclusion.org", organisation="Default Organisation")
        )

        with pytest.raises(ValidationError) as exc:
            await svc.update_tenant(MagicMock(id=uuid4()), 1, _body(email="new@tenant.com"),
                                    background_tasks=MagicMock())
        assert exc.value.code == "DEFAULT_ORG_PROTECTED"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_organisation_other_fields_still_editable(self) -> None:
        svc = _tenant_service()
        svc._tenants.get_by_id = AsyncMock(
            return_value=_tenant("admin@ai4inclusion.org", organisation="Default Organisation")
        )

        await svc.update_tenant(MagicMock(id=uuid4()), 1,
                                _body(email="admin@ai4inclusion.org", contact_name="Ops"),
                                background_tasks=MagicMock())
        assert _staged(svc)["name"] == "Ops"

    @pytest.mark.asyncio
    async def test_platform_admin_contact_rejected(self) -> None:
        svc = _tenant_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        contact = _user("old@tenant.com")
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: contact if e == "old@tenant.com" else None
        )

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(MagicMock(id=uuid4()), 1, _body(email="new@tenant.com"),
                                    background_tasks=MagicMock())
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "TENANT_EMAIL_EDIT_NOT_ALLOWED"
        svc._tokens.create_email_change_token.assert_not_called()


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

        assert _staged(svc)["name"] == "Jane"
        assert "pending_email" not in _staged(svc)
        svc._tenants.commit.assert_awaited_once()


class TestPendingEmailInResponse:
    def test_pending_email_returned_masked(self) -> None:
        tenant = _tenant(pending_email="newperson@tenant.com")
        tenant.created_at = datetime.now(timezone.utc)
        data = TenantService.build_tenant_response(tenant)
        assert data["pending_email"] and "*" in data["pending_email"]
        assert data["pending_email"] != "newperson@tenant.com"

    def test_expired_request_not_shown_as_pending(self) -> None:
        tenant = _tenant(pending_email="newperson@tenant.com",
                         pending_expires_in=timedelta(seconds=-1))
        tenant.created_at = datetime.now(timezone.utc)
        assert TenantService.build_tenant_response(tenant)["pending_email"] is None


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
    credentials = MagicMock()
    credentials.get_by_user_id = AsyncMock(return_value=MagicMock(name="creds"))
    credentials.delete = AsyncMock()
    refresh_tokens = MagicMock()
    refresh_tokens.delete_by_user_id = AsyncMock()
    cache = MagicMock()
    cache.revoke_all_sessions = AsyncMock()
    roles = MagicMock()
    roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
    return AuthService(
        user_repo=users,
        role_service=roles,
        token_service=MagicMock(),
        credentials_repo=credentials,
        refresh_token_repo=refresh_tokens,
        verification_repo=verifications,
        tenant_repo=tenants,
        email_client=MagicMock(),
        cache_service=cache,
    )


def _wire_token(svc: AuthService, tenant: Tenant, new_email: str, contact=None, holder=None):
    """``contact`` is returned for tenant.email, ``holder`` for the new address."""
    svc._tokens.validate_token.return_value = TokenPayload(
        sub=str(uuid4()), token_type=TokenType.EMAIL_CHANGE,
        tenant_id=str(tenant.id), email=new_email,
    )
    token_obj = MagicMock(is_active=True)
    svc._verifications.get_by_token = AsyncMock(return_value=token_obj)
    svc._tenants.get_by_id = AsyncMock(return_value=tenant)
    by_email = {tenant.email: contact, new_email: holder}
    svc._users.get_by_email = AsyncMock(side_effect=lambda e: by_email.get(e))
    return token_obj


_REISSUE = "app.services.auth_service.reissue_setup_token"
_ENQUEUE = "app.services.auth_service.enqueue_email"


class TestConfirmTenantEmailChange:
    @pytest.mark.asyncio
    async def test_applies_change_and_hands_account_over(self) -> None:
        svc = _auth_service()
        tenant = _tenant(pending_email="new@tenant.com")
        admin = _user("old@tenant.com")
        token_obj = _wire_token(svc, tenant, "new@tenant.com", contact=admin)
        creds = svc._credentials.get_by_user_id.return_value

        with patch(_REISSUE, new=AsyncMock(return_value="setup-token")) as reissue, \
             patch(_ENQUEUE) as enqueue, \
             patch("app.services.auth_service.render_setup_link") as render:
            email_changed = await svc.verify_email_token("tok", background_tasks=MagicMock())
            enqueue.call_args.args[2]()

        assert email_changed is True
        assert tenant.email == "new@tenant.com" and tenant.pending_email is None
        assert tenant.pending_email_expires_at is None
        assert admin.email == "new@tenant.com"
        svc._verifications.deactivate.assert_awaited_once_with(token_obj)
        # Outgoing admin loses password and every session.
        svc._credentials.delete.assert_awaited_once_with(creds)
        svc._refresh_tokens.delete_by_user_id.assert_awaited_once_with(admin.id)
        svc._cache.revoke_all_sessions.assert_awaited_once_with(str(admin.id))
        # Incoming admin gets a setup link at the new address.
        assert reissue.await_args.args[0] is admin
        render.assert_called_once_with(admin, "setup-token")
        svc._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_superseded_link_rejected(self) -> None:
        """A newer request replaced pending_email — the older link is dead."""
        svc = _auth_service()
        tenant = _tenant(pending_email="newer@tenant.com")
        _wire_token(svc, tenant, "new@tenant.com", contact=_user("old@tenant.com"))

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        assert tenant.email == "old@tenant.com"
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_request_rejected(self) -> None:
        svc = _auth_service()
        tenant = _tenant(pending_email="new@tenant.com", pending_expires_in=timedelta(seconds=-1))
        _wire_token(svc, tenant, "new@tenant.com", contact=_user("old@tenant.com"))

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        assert tenant.email == "old@tenant.com"

    @pytest.mark.asyncio
    async def test_link_rejected_after_change_applied_directly(self) -> None:
        """A direct change clears pending_email, so the old link no longer matches."""
        svc = _auth_service()
        tenant = _tenant("other.admin@tenant.com", pending_email=None)
        _wire_token(svc, tenant, "new@tenant.com", contact=_user("other.admin@tenant.com"))

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        assert tenant.email == "other.admin@tenant.com"

    @pytest.mark.asyncio
    async def test_platform_admin_never_handed_over(self) -> None:
        """Roles changed after the request: confirmation still refuses."""
        svc = _auth_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        tenant = _tenant(pending_email="new@tenant.com")
        admin = _user("old@tenant.com")
        _wire_token(svc, tenant, "new@tenant.com", contact=admin)

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        assert admin.email == "old@tenant.com"
        svc._credentials.delete.assert_not_awaited()
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refused_while_tenant_suspended(self) -> None:
        svc = _auth_service()
        tenant = _tenant(status=TenantStatus.SUSPENDED, pending_email="new@tenant.com")
        _wire_token(svc, tenant, "new@tenant.com", contact=_user("old@tenant.com"))

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")
        assert tenant.email == "old@tenant.com"
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_address_taken_since_request_raises_409(self) -> None:
        svc = _auth_service()
        tenant = _tenant(pending_email="new@tenant.com")
        _wire_token(svc, tenant, "new@tenant.com", contact=_user("old@tenant.com"),
                    holder=_user("new@tenant.com", tenant_id=7))

        with pytest.raises(DuplicateEntityError):
            await svc.verify_email_token("tok")
        assert tenant.email == "old@tenant.com"
        svc._credentials.delete.assert_not_awaited()
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_contact_updates_tenant_email_alone(self) -> None:
        """tenant.email maps to no user of this tenant: nothing to hand over."""
        svc = _auth_service()
        tenant = _tenant("orphan@tenant.com", pending_email="new@tenant.com")
        # Same address in another tenant is not this tenant's contact.
        stranger = _user("orphan@tenant.com", tenant_id=9)
        # A same-tenant user holding the new address is harmless when no login moves.
        _wire_token(svc, tenant, "new@tenant.com", contact=stranger,
                    holder=_user("new@tenant.com", tenant_id=1))

        with patch(_REISSUE, new=AsyncMock()) as reissue, patch(_ENQUEUE) as enqueue:
            assert await svc.verify_email_token("tok", background_tasks=MagicMock()) is True

        assert tenant.email == "new@tenant.com" and tenant.pending_email is None
        assert stranger.email == "orphan@tenant.com"  # no user re-aligned
        svc._credentials.delete.assert_not_awaited()
        svc._cache.revoke_all_sessions.assert_not_awaited()
        reissue.assert_not_awaited()
        enqueue.assert_not_called()
        svc._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_contact_cross_tenant_holder_raises_409(self) -> None:
        svc = _auth_service()
        tenant = _tenant("orphan@tenant.com", pending_email="new@tenant.com")
        _wire_token(svc, tenant, "new@tenant.com", holder=_user("new@tenant.com", tenant_id=7))

        with pytest.raises(DuplicateEntityError):
            await svc.verify_email_token("tok")
        assert tenant.email == "orphan@tenant.com"

    @pytest.mark.asyncio
    async def test_used_link_rejected(self) -> None:
        svc = _auth_service()
        tenant = _tenant(pending_email="new@tenant.com")
        token_obj = _wire_token(svc, tenant, "new@tenant.com", contact=_user("old@tenant.com"))
        token_obj.is_active = False

        with pytest.raises(TokenInvalidError):
            await svc.verify_email_token("tok")


class TestEmailChangeTemplate:
    @pytest.mark.parametrize("sends_setup_link", [True, False])
    def test_renders_handover_copy(self, sends_setup_link) -> None:
        from app.services.auth_email_templates import render_email_change

        with patch("app.services.auth_email_templates.build_verify_url",
                   return_value="https://ui.example/auth/verify-email?token=t"):
            msg = render_email_change("new@tenant.com", "Acme", "t",
                                      sends_setup_link=sends_setup_link)

        assert msg.to == "new@tenant.com"
        for body in (msg.html_body, msg.text_body):
            assert "Acme" in body and "verify-email?token=t" in body
            assert "signing up" not in body and "Didn" not in body
            assert ("set your password" in body) is sends_setup_link
