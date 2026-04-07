"""Business logic for Policy management."""
import asyncio
from typing import List, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import httpx
from ai4icore_env import app_env  # type: ignore
from ai4icore_auth.providers import build_jwt_verifier  # type: ignore

from app.models.orm import PiiPolicy
from app.models.schemas import PolicyCreate, PolicyStatusUpdate, PolicyUpdate
from app.repositories.policy_repository import PolicyRepository
from app.repositories.tenant_policy_repository import TenantPolicyRepository
from app.repositories.pii_type_repository import PiiTypeRepository


_forward_auth_init_lock = asyncio.Lock()
_forward_auth_verifier = build_jwt_verifier()


async def _validated_forward_auth_header(auth_header: Optional[str]) -> Optional[str]:
    """
    Validate an inbound Authorization header before forwarding it to downstream services.

    Why: prevents leaking arbitrary header values (or malformed tokens) to misconfigured URLs.
    How: verify RS256 signature via JWKS using the shared platform verifier.
    """
    if not auth_header:
        return None

    # Accept either "Bearer <jwt>" or a raw token, but always forward as "Bearer <jwt>".
    token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
    token = token.strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Empty authorization token"}},
        )

    # Initialize JWKS lazily (same pattern as the shared AuthProvider).
    if _forward_auth_verifier.loaded_key_count == 0:
        async with _forward_auth_init_lock:
            if _forward_auth_verifier.loaded_key_count == 0:
                await _forward_auth_verifier.initialize()

    # Verify signature/issuer/audience as configured (raises on failure).
    await _forward_auth_verifier.verify(token)
    return f"Bearer {token}"


class PolicyService:
    def __init__(self, db: AsyncSession):
        self.repo = PolicyRepository(db)
        self.pii_repo = PiiTypeRepository(db)
        self.tenant_repo = TenantPolicyRepository(db)

    async def list(
        self,
        is_global: Optional[bool],
        is_active: Optional[bool],
        search: Optional[str],
        page: int,
        limit: int,
    ) -> tuple[Sequence[PiiPolicy], int]:
        return await self.repo.list(
            is_global=is_global, is_active=is_active, search=search,
            page=page, limit=min(limit, 100),
        )

    async def get(self, policy_id: UUID) -> PiiPolicy:
        obj = await self.repo.get(policy_id)
        if not obj:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Policy not found"}})
        return obj

    async def get_detail(self, policy_id: UUID) -> PiiPolicy:
        obj = await self.repo.get_with_pii_types(policy_id)
        if not obj:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Policy not found"}})
        return obj

    async def create(self, data: PolicyCreate, auth_header: Optional[str] = None) -> PiiPolicy:
        if await self.repo.get_by_name(data.name):
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "CONFLICT", "message": "Policy name already exists"}},
            )

        # Validate tenant_id (non-global) against active tenants list
        active_tenant_ids = await self._get_active_tenant_ids(auth_header=auth_header)
        if (not data.is_global) and data.tenant_id:
            self._validate_tenant_id(data.tenant_id, active_tenant_ids)

        # tenant_id is not a column on pii_policy; it is only used for tenant_policy assignment.
        payload = data.model_dump(exclude={"pii_types", "tenant_id"})
        policy = await self.repo.create(payload)

        if data.pii_types:
            await self._validate_and_add_links(policy.policy_id, data.pii_types, replace=False)

        # Tenant mapping on create
        if policy.is_global:
            # Map to all active tenants
            await self.tenant_repo.assign_many(active_tenant_ids, policy.policy_id)
        elif data.tenant_id:
            existing = await self.tenant_repo.get_assignment(data.tenant_id, policy.policy_id)
            if not existing:
                await self.tenant_repo.assign(data.tenant_id, policy.policy_id)

        return await self.repo.get_with_pii_types(policy.policy_id)

    async def update(self, policy_id: UUID, data: PolicyUpdate, auth_header: Optional[str] = None) -> PiiPolicy:
        obj = await self.get(policy_id)
        active_tenant_ids = await self._get_active_tenant_ids(auth_header=auth_header)

        if (data.is_global is not True) and data.tenant_id:
            self._validate_tenant_id(data.tenant_id, active_tenant_ids)

        # tenant_id is not a column on pii_policy; it is only used for tenant_policy assignment.
        updates = data.model_dump(exclude_none=True, exclude={"pii_types", "tenant_id"})
        updated = await self.repo.update(obj, updates)

        # If pii_types is provided (including empty list), replace the linked set
        if data.pii_types is not None:
            await self._validate_and_add_links(policy_id, data.pii_types, replace=True)
            updated = await self.repo.get_with_pii_types(policy_id)

        # Handle is_global switch and optional tenant_id mapping
        if data.is_global is True:
            # Map to all active tenants
            await self.tenant_repo.assign_many(active_tenant_ids, policy_id)
        elif data.tenant_id:
            existing = await self.tenant_repo.get_assignment(data.tenant_id, policy_id)
            if not existing:
                await self.tenant_repo.assign(data.tenant_id, policy_id)

        return updated

    async def set_status(self, policy_id: UUID, data: PolicyStatusUpdate) -> dict:
        obj = await self.get(policy_id)
        await self.repo.update(obj, {"is_active": data.is_active})
        return {"is_active": data.is_active}

    async def delete(self, policy_id: UUID) -> None:
        obj = await self.get(policy_id)
        await self.repo.delete(obj)

    async def _validate_and_add_links(self, policy_id: UUID, links, replace: bool) -> None:
        validated = []
        for link in links:
            pii_type = await self.pii_repo.get(link.pii_type_id)
            if not pii_type:
                raise HTTPException(
                    status_code=404,
                    detail={"error": {"code": "NOT_FOUND", "message": f"pii_type_id {link.pii_type_id} not found"}},
                )
            validated.append({"pii_type_id": link.pii_type_id})

        if replace:
            await self.repo.replace_pii_type_links(policy_id, validated)
        else:
            await self.repo.add_pii_type_links(policy_id, validated)

    async def _get_active_tenant_ids(self, auth_header: Optional[str]) -> List[str]:
        """
        Fetch active tenant IDs from multi-tenant service.
        """
        base = (app_env.multi_tenant_service_url or "").rstrip("/")
        if not base:
            scheme = (app_env.multi_tenant_service_scheme or "http").strip() or "http"
            host = (app_env.multi_tenant_service_name or "").strip()
            port = str(app_env.multi_tenant_service_port or "").strip()
            if host and port:
                base = f"{scheme}://{host}:{port}"
            elif host:
                base = f"{scheme}://{host}"

        if not base:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "CONFIG_ERROR",
                        "message": (
                            "multi_tenant_service_url is not configured "
                            "(set multi_tenant_service_url or multi_tenant_service_scheme/name/port)"
                        ),
                    }
                },
            )
        # Multi-tenant-feature runs with root-level prefixes (e.g. /admin/...)
        # Gateway deployments may mount it under /api/v1/multi-tenant.
        primary_url = f"{base}/admin/list/tenants"
        gateway_url = f"{base}/api/v1/multi-tenant/admin/list/tenants"
        headers = {}
        validated = await _validated_forward_auth_header(auth_header)
        if validated:
            headers["Authorization"] = validated
        async with httpx.AsyncClient(timeout=app_env.policy_service_http_timeout) as client:
            resp = await client.get(primary_url, headers=headers)
            if resp.status_code == 404:
                resp = await client.get(gateway_url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": {
                        "code": "TENANT_SERVICE_ERROR",
                        "message": f"Failed to fetch tenants (status {resp.status_code})",
                    }
                },
            )
        try:
            data = resp.json() or {}
        except ValueError:
            # Downstream may return HTML/text for errors even when status < 400 via proxies.
            raise HTTPException(
                status_code=502,
                detail={
                    "error": {
                        "code": "TENANT_SERVICE_ERROR",
                        "message": "Failed to parse tenants response as JSON",
                    }
                },
            )
        tenants = data.get("tenants") or []
        active = []
        for t in tenants:
            tid = t.get("tenant_id")
            status = str(t.get("status", "")).lower()
            if tid and status == "active":
                active.append(str(tid))
        return active

    @staticmethod
    def _validate_tenant_id(tenant_id: str, active_tenant_ids: Sequence[str]) -> None:
        if tenant_id not in set(active_tenant_ids):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid or inactive tenant_id",
                        "details": [{"field": "tenant_id", "issue": "Tenant must be ACTIVE in multi-tenant service"}],
                    }
                },
            )
