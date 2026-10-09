"""Repository for the policy_type table."""

from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_management.policy_type import PolicyType


class PolicyTypeRepository:
    """CRUD for policy_type."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all(self) -> List[PolicyType]:
        result = await self._db.execute(select(PolicyType).order_by(PolicyType.id))
        return list(result.scalars().all())

    async def get_by_id(self, policy_type_id: int) -> Optional[PolicyType]:
        result = await self._db.execute(
            select(PolicyType).where(PolicyType.id == policy_type_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, policy_type_name: str) -> Optional[PolicyType]:
        result = await self._db.execute(
            select(PolicyType).where(PolicyType.policy_type == policy_type_name)
        )
        return result.scalar_one_or_none()

    async def create(self, policy_type: str, policy_fields: Dict[str, Any], created_by: Optional[str] = None) -> PolicyType:
        row = PolicyType(policy_type=policy_type, policy_fields=policy_fields, created_by=created_by)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def update(self, policy_type_id: int, data: Dict[str, Any]) -> Optional[PolicyType]:
        await self._db.execute(
            update(PolicyType).where(PolicyType.id == policy_type_id).values(**data)
        )
        await self._db.commit()
        return await self.get_by_id(policy_type_id)

    async def delete(self, policy_type_id: int) -> bool:
        result = await self._db.execute(
            delete(PolicyType).where(PolicyType.id == policy_type_id)
        )
        await self._db.commit()
        return result.rowcount > 0
