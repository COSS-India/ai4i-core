"""Notification-receiver domain service.

CRUD plus:
  - Email resolution against ``auth_db`` (RBAC role → emails, tenant → tenant-admin
    emails). The auth tables have no ORM models here, so we use raw ``text()``
    queries against the secondary ``auth_db`` session.
  - Auto-creation of a paired routing rule on receiver create (mirrors source
    behaviour).

Rewritten from alert-management-service/alert_management.py:107-245, 1736-2351.
``organization`` and audit logging dropped. Sync triggering is the route
layer's job.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError, ValidationError
from app.models.alert_management.notification_receiver import NotificationReceiver
from app.models.alert_management.routing_rule import RoutingRule
from app.repositories.alert_management.notification_receiver_repository import (
    NotificationReceiverRepository,
)
from app.repositories.alert_management.routing_rule_repository import RoutingRuleRepository
from app.schemas.alert_management.receiver import (
    NotificationReceiverCreate,
    NotificationReceiverResponse,
    NotificationReceiverUpdate,
)
from app.schemas.enums.alert_management import VALID_CATEGORIES, VALID_SEVERITIES

# Auth-DB (ai4iplatform_auth) schema: users.id (UUID PK), users.tenant_id → tenants.id,
# user_role.user_id → users.id, user_role.role_id → roles.id, roles.id (PK), roles.name.

# Active users holding a given RBAC role.
_SQL_EMAILS_BY_ROLE = text(
    """
    SELECT DISTINCT u.email
    FROM users u
    INNER JOIN user_role ur ON ur.user_id = u.id
    INNER JOIN roles r ON r.id = ur.role_id
    WHERE r.name = :role_name
      AND u.is_active = true
      AND u.email IS NOT NULL AND u.email != ''
    ORDER BY u.email
    """
)

# TENANT ADMIN emails for a tenant (matched by organisation name).
_SQL_TENANT_ADMIN_EMAILS = text(
    """
    SELECT u.email
    FROM tenants t
    JOIN users u ON u.tenant_id = t.id
    JOIN user_role ur ON ur.user_id = u.id
    JOIN roles r ON r.id = ur.role_id
    WHERE LOWER(TRIM(t.organisation)) = LOWER(TRIM(:tenant_name))
      AND u.is_active = true
      AND COALESCE(u.is_tenant_active, true) = true
      AND r.name = 'TENANT ADMIN'
      AND u.email IS NOT NULL AND u.email != ''
    """
)


class NotificationReceiverService:
    """Business logic for notification receivers."""

    def __init__(
        self,
        receiver_repo: NotificationReceiverRepository,
        routing_rule_repo: RoutingRuleRepository,
        auth_db: Optional[AsyncSession] = None,
    ) -> None:
        self._repo = receiver_repo
        self._routing_repo = routing_rule_repo
        self._auth_db = auth_db

    # ── auth_db email resolution ──

    async def _get_emails_by_role(self, role_name: str) -> List[str]:
        if self._auth_db is None:
            raise ValidationError(
                "auth_db is not configured; cannot resolve emails by RBAC role. "
                "Provide email_to explicitly or set AUTH_DB_NAME."
            )
        result = await self._auth_db.execute(_SQL_EMAILS_BY_ROLE, {"role_name": role_name})
        return [row[0] for row in result.fetchall() if row[0]]

    async def _resolve_tenant_emails(self, tenant_name: str) -> List[str]:
        if not tenant_name or not tenant_name.strip():
            return []
        if self._auth_db is None:
            return []
        result = await self._auth_db.execute(
            _SQL_TENANT_ADMIN_EMAILS, {"tenant_name": tenant_name.strip()}
        )
        return [row[0] for row in result.fetchall() if row[0]]

    # ── Reads ──

    async def get(self, receiver_id: int) -> NotificationReceiverResponse:
        receiver = await self._repo.get_by_id(receiver_id)
        if not receiver:
            raise EntityNotFoundError(f"Notification receiver {receiver_id} not found")
        return await self._to_response(receiver)

    async def list(self) -> List[NotificationReceiverResponse]:
        receivers = await self._repo.list()
        return [await self._to_response(r) for r in receivers]

    # ── Writes ──

    async def create(
        self, data: NotificationReceiverCreate
    ) -> NotificationReceiverResponse:
        if data.category not in VALID_CATEGORIES:
            raise ValidationError("category must be 'application' or 'infrastructure'")
        if data.severity not in VALID_SEVERITIES:
            raise ValidationError("severity must be 'critical', 'warning', or 'info'")

        tenant_val = (str(data.tenant).strip() or None) if data.tenant else None
        rbac_role = data.rbac_role
        email_to = data.email_to

        # Resolve recipients.
        if tenant_val:
            email_to = await self._resolve_tenant_emails(tenant_val)
            if not email_to:
                raise EntityNotFoundError(
                    f"No active TENANT ADMIN user found for tenant '{tenant_val}'"
                )
        elif rbac_role or (not email_to and not tenant_val):
            rbac_role = rbac_role or "ADMIN"
            email_to = await self._get_emails_by_role(rbac_role)
            if not email_to:
                raise EntityNotFoundError(f"No active users found with role '{rbac_role}'")
        elif not email_to:
            raise ValidationError("Either 'email_to' or 'rbac_role' must be provided")

        receiver_name, base_name, suffix_parts = self._build_receiver_name(data)

        if await self._repo.get_by_receiver_name(receiver_name):
            raise DuplicateEntityError(
                f"Receiver with name '{receiver_name}' already exists."
            )

        alert_names = [n for n in (data.alert_names or []) if n and str(n).strip()] or None
        rule_name = (str(data.rule_name).strip() or None) if data.rule_name else None

        receiver = NotificationReceiver(
            receiver_name=receiver_name,
            rule_name=rule_name,
            description=(str(data.description).strip() or None) if data.description else None,
            category=data.category.lower(),
            severity=data.severity.lower(),
            email_to=email_to,
            rbac_role=rbac_role,
            alert_names=alert_names,
            tenant=tenant_val,
            email_subject_template=data.email_subject_template,
            email_body_template=data.email_body_template,
        )
        await self._repo.add(receiver)

        # Auto-create the paired routing rule.
        await self._auto_create_routing_rule(
            receiver=receiver,
            data=data,
            base_name=base_name,
            suffix_parts=suffix_parts,
            rule_name=rule_name,
        )

        await self._repo.commit()
        refreshed = await self._repo.get_by_id(receiver.id)
        return await self._to_response(refreshed)

    async def update(
        self, receiver_id: int, data: NotificationReceiverUpdate
    ) -> NotificationReceiverResponse:
        receiver = await self._repo.get_by_id(receiver_id)
        if not receiver:
            raise EntityNotFoundError(f"Notification receiver {receiver_id} not found")

        updates = {}
        for field in (
            "receiver_name",
            "rule_name",
            "description",
            "category",
            "severity",
            "alert_names",
            "tenant",
            "email_subject_template",
            "email_body_template",
            "enabled",
        ):
            value = getattr(data, field)
            if value is not None:
                updates[field] = value

        # Re-resolve emails if rbac_role or email_to changed.
        if data.rbac_role is not None:
            updates["rbac_role"] = data.rbac_role
            updates["email_to"] = await self._get_emails_by_role(data.rbac_role)
        elif data.email_to is not None:
            updates["email_to"] = data.email_to
            updates["rbac_role"] = None

        await self._repo.apply_updates(receiver, updates)
        await self._repo.commit()
        refreshed = await self._repo.get_by_id(receiver_id)
        return await self._to_response(refreshed)

    async def delete(self, receiver_id: int) -> None:
        receiver = await self._repo.get_by_id(receiver_id)
        if not receiver:
            raise EntityNotFoundError(f"Notification receiver {receiver_id} not found")
        await self._repo.delete_by_id(receiver_id)
        await self._repo.commit()

    # ── Helpers ──

    @staticmethod
    def _build_receiver_name(data: NotificationReceiverCreate):
        """Returns (receiver_name, base_name, suffix_parts)."""
        base_name = f"{data.severity}-{data.category}"
        suffix_parts: List[str] = []
        if data.alert_names:
            names = sorted(n for n in data.alert_names if n and str(n).strip())
            if names:
                suffix_parts.append("alerts-" + "|".join(names))
        if data.tenant and str(data.tenant).strip():
            suffix_parts.append("tenant-" + str(data.tenant).strip())
        receiver_name = base_name + ("--" + "--".join(suffix_parts) if suffix_parts else "")
        return receiver_name, base_name, suffix_parts

    async def _auto_create_routing_rule(
        self,
        *,
        receiver: NotificationReceiver,
        data: NotificationReceiverCreate,
        base_name: str,
        suffix_parts: List[str],
        rule_name: Optional[str],
    ) -> None:
        # One routing rule per receiver — skip if one already exists.
        existing = await self._routing_repo.list(enabled=None)
        if any(r.receiver_id == receiver.id for r in existing):
            return

        derived_name = rule_name
        if derived_name is None:
            derived_name = receiver.receiver_name
            if data.alert_type and not derived_name.endswith(f"-{data.alert_type}"):
                derived_name = f"{base_name}-{data.alert_type}" + (
                    "--" + "--".join(suffix_parts) if suffix_parts else ""
                )
        # Guard against a name collision on the globally-unique rule_name.
        if await self._routing_repo.get_by_rule_name(derived_name):
            derived_name = f"{derived_name}-{receiver.id}"

        rule = RoutingRule(
            rule_name=derived_name,
            receiver_id=receiver.id,
            match_severity=data.severity.lower(),
            match_category=data.category.lower(),
            match_alert_type=data.alert_type,
            match_alert_names=[n for n in (data.alert_names or []) if n and str(n).strip()] or None,
            group_by=["alertname", "category", "severity"],
        )
        await self._routing_repo.add(rule)

    async def _to_response(
        self, receiver: NotificationReceiver
    ) -> NotificationReceiverResponse:
        # For tenant receivers, surface the live tenant-admin emails in the response.
        email_to = list(receiver.email_to or [])
        if receiver.tenant and str(receiver.tenant).strip():
            resolved = await self._resolve_tenant_emails(receiver.tenant)
            if resolved:
                email_to = resolved

        return NotificationReceiverResponse(
            id=receiver.id,
            receiver_name=receiver.receiver_name,
            rule_name=receiver.rule_name,
            description=receiver.description,
            category=receiver.category,
            severity=receiver.severity,
            email_to=email_to,
            rbac_role=receiver.rbac_role,
            alert_names=receiver.alert_names,
            tenant=receiver.tenant,
            email_subject_template=receiver.email_subject_template,
            email_body_template=receiver.email_body_template,
            enabled=bool(receiver.enabled),
            created_at=receiver.created_at,
            updated_at=receiver.updated_at,
        )
