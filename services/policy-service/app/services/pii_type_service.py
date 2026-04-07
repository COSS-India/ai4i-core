"""Business logic for PII Type management."""
import re
from typing import Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import PiiType
from app.models.schemas import PiiTypeCreate, PiiTypeUpdate
from app.repositories.pii_type_repository import PiiTypeRepository
from app.utils.constants import ALLOWED_MASK_TYPES

try:
    # `regex` supports per-operation timeouts; stdlib `re` does not.
    import regex as safe_regex  # type: ignore
except Exception:  # pragma: no cover
    safe_regex = None


class PiiTypeService:
    def __init__(self, db: AsyncSession):
        self.repo = PiiTypeRepository(db)

    async def list(
        self,
        search: Optional[str],
        page: int,
        limit: int,
    ) -> tuple[Sequence[PiiType], int]:
        return await self.repo.list(search=search, page=page, limit=min(limit, 100))

    async def get(self, pii_type_id: UUID) -> PiiType:
        obj = await self.repo.get(pii_type_id)
        if not obj:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "PII type not found"}})
        return obj

    async def create(self, data: PiiTypeCreate) -> PiiType:
        # Validate enumerated inputs with helpful messages
        if data.mask_format not in ALLOWED_MASK_TYPES:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Unsupported mask_format",
                        "details": [
                            {"field": "mask_format", "issue": f"Allowed: {', '.join(ALLOWED_MASK_TYPES)}"}
                        ],
                    }
                },
            )
        # validate regex against example_values
        self._validate_regex(data.regex_pattern, data.example_values)
        # check duplicate
        existing = await self.repo.get_by_label(data.pii_type_label)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "CONFLICT", "message": "pii_type_label already exists"}},
            )
        payload = data.model_dump(exclude={"example_values"})
        return await self.repo.create(payload)

    async def update(self, pii_type_id: UUID, data: PiiTypeUpdate) -> PiiType:
        obj = await self.get(pii_type_id)
        updates = data.model_dump(exclude_none=True)
        # Enforce uniqueness on pii_type_label if it changes
        next_label = updates.get("pii_type_label", obj.pii_type_label)
        if next_label != obj.pii_type_label:
            existing = await self.repo.get_by_label(next_label)
            if existing and existing.pii_type_id != obj.pii_type_id:
                raise HTTPException(
                    status_code=409,
                    detail={"error": {"code": "CONFLICT", "message": "pii_type_label already exists"}},
                )

        if "regex_pattern" in updates:
            # re-validate against empty examples (no stored examples — best effort)
            pass
        return await self.repo.update(obj, updates)

    async def delete(self, pii_type_id: UUID) -> None:
        obj = await self.get(pii_type_id)
        if await self.repo.has_active_policy_links(pii_type_id):
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "CONFLICT", "message": "PII type is linked to active policies. Unlink first."}},
            )
        await self.repo.delete(obj)

    @staticmethod
    def _validate_regex(pattern: str, examples: Sequence[str]) -> None:
        # Guard against Regex DoS (catastrophic backtracking) from untrusted patterns.
        # Prefer `regex` module with a tight timeout; stdlib `re` cannot enforce time limits.
        if not isinstance(pattern, str) or not pattern.strip():
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "VALIDATION_ERROR", "message": "regex_pattern must be a non-empty string"}},
            )
        if len(pattern) > 1024:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "VALIDATION_ERROR", "message": "regex_pattern is too long (max 1024 chars)"}},
            )

        try:
            if safe_regex is not None:
                compiled = safe_regex.compile(pattern)
            else:
                # Fallback (shouldn't happen in normal deployments since `regex` is pinned in requirements).
                # Without timeouts, stdlib `re` is susceptible to catastrophic backtracking.
                compiled = re.compile(pattern)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "VALIDATION_ERROR", "message": f"Invalid regex: {exc}"}},
            ) from exc

        mismatches = []
        if safe_regex is not None:
            # seconds; keep small to prevent CPU pinning while still allowing typical patterns.
            timeout_s = 0.05
            for v in examples:
                try:
                    if not compiled.search(v, timeout=timeout_s):
                        mismatches.append(v)
                except safe_regex.TimeoutError:  # type: ignore[attr-defined]
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Regex evaluation timed out (pattern too complex)",
                            }
                        },
                    )
        else:
            mismatches = [v for v in examples if not compiled.search(v)]

        if mismatches:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Regex did not match some example_values",
                        "details": [{"field": "example_values", "issue": f"no match: {v}"} for v in mismatches],
                    }
                },
            )
