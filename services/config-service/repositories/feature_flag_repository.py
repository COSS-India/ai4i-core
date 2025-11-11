import hashlib
from typing import List, Optional, Tuple

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import FeatureFlag, FeatureFlagHistory
from datetime import datetime, timezone


class FeatureFlagRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create_feature_flag(
        self,
        name: str,
        description: Optional[str],
        is_enabled: bool,
        rollout_percentage: float,
        target_users: Optional[List[str]],
        environment: str,
    ) -> FeatureFlag:
        async with self._session_factory() as session:  # type: AsyncSession
            now = datetime.now(timezone.utc)
            flag = FeatureFlag(
                name=name,
                description=description,
                is_enabled=is_enabled,
                rollout_percentage=str(rollout_percentage),
                target_users=target_users or [],
                environment=environment,
                created_at=now,
                updated_at=now,
            )
            session.add(flag)
            await session.commit()
            await session.refresh(flag)
            return flag

    async def get_feature_flag(self, name: str, environment: str) -> Optional[FeatureFlag]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeatureFlag).where(
                    FeatureFlag.name == name,
                    FeatureFlag.environment == environment,
                )
            )
            return result.scalar_one_or_none()

    async def list_feature_flags(
        self,
        environment: Optional[str] = None,
        enabled: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[FeatureFlag], int]:
        async with self._session_factory() as session:
            q = select(FeatureFlag)
            cq = select(func.count(FeatureFlag.id))
            if environment:
                q = q.where(FeatureFlag.environment == environment)
                cq = cq.where(FeatureFlag.environment == environment)
            if enabled is not None:
                q = q.where(FeatureFlag.is_enabled == enabled)
                cq = cq.where(FeatureFlag.is_enabled == enabled)
            q = q.limit(limit).offset(offset)
            items = list((await session.execute(q)).scalars().all())
            total = (await session.execute(cq)).scalar() or 0
            return items, int(total)

    async def update_feature_flag(
        self,
        name: str,
        environment: str,
        is_enabled: Optional[bool] = None,
        rollout_percentage: Optional[float] = None,
        target_users: Optional[List[str]] = None,
        changed_by: Optional[str] = None,
    ) -> Optional[FeatureFlag]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeatureFlag).where(
                    FeatureFlag.name == name,
                    FeatureFlag.environment == environment,
                ).with_for_update()
            )
            flag = result.scalar_one_or_none()
            if not flag:
                return None
            
            # Store old values for history
            old_is_enabled = flag.is_enabled
            old_rollout_percentage = flag.rollout_percentage
            old_target_users = flag.target_users
            
            # Update flag
            if is_enabled is not None:
                flag.is_enabled = is_enabled
            if rollout_percentage is not None:
                flag.rollout_percentage = str(rollout_percentage)
            if target_users is not None:
                flag.target_users = target_users
            flag.updated_at = datetime.now(timezone.utc)
            
            # Create history entry if something changed
            if (is_enabled is not None and old_is_enabled != is_enabled) or \
               (rollout_percentage is not None and old_rollout_percentage != str(rollout_percentage)) or \
               (target_users is not None and old_target_users != target_users):
                history = FeatureFlagHistory(
                    feature_flag_id=flag.id,
                    old_is_enabled=old_is_enabled,
                    new_is_enabled=flag.is_enabled,
                    old_rollout_percentage=old_rollout_percentage,
                    new_rollout_percentage=flag.rollout_percentage,
                    old_target_users=old_target_users,
                    new_target_users=flag.target_users,
                    changed_by=changed_by,
                    changed_at=datetime.now(timezone.utc),
                )
                session.add(history)
            
            await session.commit()
            await session.refresh(flag)
            return flag

    async def delete_feature_flag(self, name: str, environment: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(FeatureFlag).where(
                    FeatureFlag.name == name,
                    FeatureFlag.environment == environment,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def evaluate_feature_flag(self, name: str, environment: str, user_id: str) -> Tuple[bool, str]:
        flag = await self.get_feature_flag(name, environment)
        if not flag:
            return False, "flag_not_found"
        if not flag.is_enabled:
            return False, "flag_disabled"
        if flag.target_users and user_id in (flag.target_users or []):
            return True, "user_targeted"
        try:
            rollout = float(flag.rollout_percentage or 0)
        except ValueError:
            rollout = 0.0
        if rollout >= 100.0:
            return True, "full_rollout"
        if rollout <= 0.0:
            return False, "zero_rollout"
        h = hashlib.sha256(f"{name}:{user_id}".encode("utf-8")).hexdigest()
        bucket = int(h[:8], 16) % 100
        if bucket < int(rollout):
            return True, "percentage_rollout"
        return False, "percentage_excluded"

    async def get_feature_flag_history(self, name: str, environment: str, limit: int = 50) -> List[FeatureFlagHistory]:
        async with self._session_factory() as session:
            flag = await self.get_feature_flag(name, environment)
            if not flag:
                return []
            result = await session.execute(
                select(FeatureFlagHistory)
                .where(FeatureFlagHistory.feature_flag_id == flag.id)
                .order_by(FeatureFlagHistory.changed_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())


