"""
Repository for feature flag database operations
"""
import logging
from typing import Any, List, Optional, Tuple
from datetime import datetime, timezone

from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import FeatureFlag, FeatureFlagEvaluation

logger = logging.getLogger(__name__)


class FeatureFlagRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create_feature_flag(
        self,
        name: str,
        description: Optional[str],
        is_enabled: bool,
        environment: str,
        rollout_percentage: Optional[str] = None,
        target_users: Optional[List[str]] = None,
        unleash_flag_name: Optional[str] = None,
    ) -> FeatureFlag:
        """Create a new feature flag"""
        async with self._session_factory() as session:
            try:
                now = datetime.now(timezone.utc)
                flag = FeatureFlag(
                    name=name,
                    description=description,
                    is_enabled=is_enabled,
                    rollout_percentage=rollout_percentage,
                    target_users=target_users,
                    environment=environment,
                    unleash_flag_name=unleash_flag_name,
                    created_at=now,
                    updated_at=now,
                )
                session.add(flag)
                await session.commit()
                await session.refresh(flag)
                return flag
            except IntegrityError as e:
                await session.rollback()
                logger.error(f"Unique constraint violation for feature flag {name}: {e}")
                raise
            except Exception:
                await session.rollback()
                raise

    async def get_feature_flag(self, name: str, environment: str) -> Optional[FeatureFlag]:
        """Get feature flag by name and environment"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeatureFlag).where(
                    FeatureFlag.name == name,
                    FeatureFlag.environment == environment,
                )
            )
            return result.scalar_one_or_none()

    async def get_feature_flags(
        self,
        environment: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[FeatureFlag], int]:
        """Get feature flags with optional environment filter and pagination"""
        async with self._session_factory() as session:
            query = select(FeatureFlag)
            count_q = select(func.count(FeatureFlag.id))

            if environment:
                query = query.where(FeatureFlag.environment == environment)
                count_q = count_q.where(FeatureFlag.environment == environment)

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            items = list(result.scalars().all())
            total = (await session.execute(count_q)).scalar() or 0
            return items, int(total)

    async def update_feature_flag(
        self,
        name: str,
        environment: str,
        **kwargs,
    ) -> Optional[FeatureFlag]:
        """Update feature flag properties"""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(FeatureFlag).where(
                        FeatureFlag.name == name,
                        FeatureFlag.environment == environment,
                    ).with_for_update()
                )
                flag = result.scalar_one_or_none()
                if not flag:
                    return None

                # Update provided fields
                for key, value in kwargs.items():
                    if hasattr(flag, key):
                        setattr(flag, key, value)

                flag.updated_at = datetime.now(timezone.utc)

                await session.commit()
                await session.refresh(flag)
                return flag
            except Exception:
                await session.rollback()
                raise

    async def delete_feature_flag(self, name: str, environment: str) -> bool:
        """Delete feature flag by name and environment"""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    delete(FeatureFlag).where(
                        FeatureFlag.name == name,
                        FeatureFlag.environment == environment,
                    )
                )
                await session.commit()
                return result.rowcount > 0
            except Exception:
                await session.rollback()
                raise

    async def sync_from_unleash(
        self,
        name: str,
        environment: str,
        is_enabled: bool,
        unleash_data: dict,
    ) -> FeatureFlag:
        """Upsert feature flag from Unleash data"""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(FeatureFlag).where(
                        FeatureFlag.name == name,
                        FeatureFlag.environment == environment,
                    )
                )
                flag = result.scalar_one_or_none()

                now = datetime.now(timezone.utc)
                if flag:
                    # Update existing flag
                    flag.is_enabled = is_enabled
                    flag.unleash_flag_name = unleash_data.get("name", name)
                    flag.last_synced_at = now
                    flag.updated_at = now
                else:
                    # Create new flag
                    flag = FeatureFlag(
                        name=name,
                        is_enabled=is_enabled,
                        environment=environment,
                        unleash_flag_name=unleash_data.get("name", name),
                        last_synced_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(flag)

                await session.commit()
                await session.refresh(flag)
                return flag
            except Exception:
                await session.rollback()
                raise

    async def record_evaluation(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        result: Optional[bool],
        variant: Optional[str],
        environment: str,
        reason: str,
        evaluated_value: Optional[Any] = None,
    ) -> FeatureFlagEvaluation:
        """Record a feature flag evaluation in the audit trail"""
        async with self._session_factory() as session:
            try:
                now = datetime.now(timezone.utc)
                evaluation = FeatureFlagEvaluation(
                    flag_name=flag_name,
                    user_id=user_id,
                    context=context,
                    result=result,
                    variant=variant,
                    evaluated_value=evaluated_value,
                    environment=environment,
                    evaluated_at=now,
                    evaluation_reason=reason,
                )
                session.add(evaluation)

                # Update flag statistics
                flag_result = await session.execute(
                    select(FeatureFlag).where(
                        FeatureFlag.name == flag_name,
                        FeatureFlag.environment == environment,
                    )
                )
                flag = flag_result.scalar_one_or_none()
                if flag:
                    flag.evaluation_count = (flag.evaluation_count or 0) + 1
                    flag.last_evaluated_at = now

                await session.commit()
                await session.refresh(evaluation)
                return evaluation
            except Exception:
                await session.rollback()
                raise

    async def get_evaluation_history(
        self,
        flag_name: str,
        limit: int = 100,
    ) -> List[FeatureFlagEvaluation]:
        """Get evaluation history for a flag"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeatureFlagEvaluation).where(
                    FeatureFlagEvaluation.flag_name == flag_name
                ).order_by(FeatureFlagEvaluation.evaluated_at.desc()).limit(limit)
            )
            return list(result.scalars().all())

