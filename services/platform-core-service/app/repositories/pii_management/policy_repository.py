"""Repository for domain_policies."""

import json
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pii_management.domain_policy import DomainPolicy


class PolicyRepository:
    """CRUD for domain_policies."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all(self) -> List[DomainPolicy]:
        result = await self._db.execute(select(DomainPolicy).order_by(DomainPolicy.domain_id))
        return list(result.scalars().all())

    async def get_by_id(self, domain_id: str) -> Optional[DomainPolicy]:
        result = await self._db.execute(
            select(DomainPolicy).where(DomainPolicy.domain_id == domain_id)
        )
        return result.scalar_one_or_none()

    async def get_active_ids(self) -> List[str]:
        result = await self._db.execute(
            select(DomainPolicy.domain_id).where(DomainPolicy.is_active.is_(True))
        )
        return [row[0] for row in result.all()]

    async def create(self, domain_id: str, description: str) -> DomainPolicy:
        policy = DomainPolicy(
            domain_id=domain_id,
            is_active=False,
            policy_json={"meta": {"version": "1.0", "description": description}, "rules": []},
        )
        self._db.add(policy)
        await self._db.commit()
        await self._db.refresh(policy)
        return policy

    async def update_rules(self, domain_id: str, rules: list) -> Optional[DomainPolicy]:
        policy = await self.get_by_id(domain_id)
        if not policy:
            return None
        updated = dict(policy.policy_json)
        updated["rules"] = rules
        await self._db.execute(
            update(DomainPolicy)
            .where(DomainPolicy.domain_id == domain_id)
            .values(policy_json=updated)
        )
        await self._db.commit()
        return await self.get_by_id(domain_id)

    async def set_active_bulk(self, domain_ids: List[str]) -> None:
        """Deactivate all, then activate the specified domains."""
        await self._db.execute(
            update(DomainPolicy).values(is_active=False)
        )
        if domain_ids:
            await self._db.execute(
                update(DomainPolicy)
                .where(DomainPolicy.domain_id.in_(domain_ids))
                .values(is_active=True)
            )
        await self._db.commit()
