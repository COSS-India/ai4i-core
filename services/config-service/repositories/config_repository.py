import logging
from typing import List, Optional, Tuple

from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import Configuration, ConfigurationHistory
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class ConfigRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create_configuration(
        self,
        key: str,
        value: str,
        environment: str,
        service_name: str,
        is_encrypted: bool,
        changed_by: Optional[str] = None,
    ) -> Configuration:
        async with self._session_factory() as session:  # type: AsyncSession
            try:
                now = datetime.now(timezone.utc)
                config = Configuration(
                    key=key,
                    value=value,
                    environment=environment,
                    service_name=service_name,
                    is_encrypted=is_encrypted,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(config)
                await session.flush()

                history = ConfigurationHistory(
                    configuration_id=config.id,
                    old_value=None,
                    new_value=value,
                    changed_by=changed_by,
                    changed_at=now,
                )
                session.add(history)

                await session.commit()
                await session.refresh(config)
                return config
            except IntegrityError as e:
                await session.rollback()
                logger.error(f"Unique constraint violation for configuration {key}/{environment}/{service_name}: {e}")
                raise
            except Exception:
                await session.rollback()
                raise

    async def get_configuration(
        self,
        key: str,
        environment: str,
        service_name: str,
    ) -> Optional[Configuration]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Configuration).where(
                    Configuration.key == key,
                    Configuration.environment == environment,
                    Configuration.service_name == service_name,
                )
            )
            return result.scalar_one_or_none()

    async def get_configurations(
        self,
        environment: Optional[str] = None,
        service_name: Optional[str] = None,
        keys: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Configuration], int]:
        async with self._session_factory() as session:
            query = select(Configuration)
            count_q = select(func.count(Configuration.id))

            if environment:
                query = query.where(Configuration.environment == environment)
                count_q = count_q.where(Configuration.environment == environment)
            if service_name:
                query = query.where(Configuration.service_name == service_name)
                count_q = count_q.where(Configuration.service_name == service_name)
            if keys:
                query = query.where(Configuration.key.in_(keys))
                count_q = count_q.where(Configuration.key.in_(keys))

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            items = list(result.scalars().all())
            total = (await session.execute(count_q)).scalar() or 0
            return items, int(total)

    async def update_configuration(
        self,
        key: str,
        environment: str,
        service_name: str,
        new_value: str,
        is_encrypted: Optional[bool] = None,
        changed_by: Optional[str] = None,
    ) -> Optional[Configuration]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(Configuration).where(
                        Configuration.key == key,
                        Configuration.environment == environment,
                        Configuration.service_name == service_name,
                    ).with_for_update()
                )
                config = result.scalar_one_or_none()
                if not config:
                    return None

                old_value = config.value
                now = datetime.now(timezone.utc)
                config.value = new_value
                if is_encrypted is not None:
                    config.is_encrypted = is_encrypted
                config.version = (config.version or 0) + 1
                config.updated_at = now

                history = ConfigurationHistory(
                    configuration_id=config.id,
                    old_value=old_value,
                    new_value=new_value,
                    changed_by=changed_by,
                    changed_at=now,
                )
                session.add(history)

                await session.commit()
                await session.refresh(config)
                return config
            except Exception:
                await session.rollback()
                raise

    async def delete_configuration(
        self,
        key: str,
        environment: str,
        service_name: str,
    ) -> bool:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    delete(Configuration).where(
                        Configuration.key == key,
                        Configuration.environment == environment,
                        Configuration.service_name == service_name,
                    )
                )
                await session.commit()
                return result.rowcount > 0
            except Exception:
                await session.rollback()
                raise

    async def get_configuration_history(self, configuration_id: int):
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConfigurationHistory).where(
                    ConfigurationHistory.configuration_id == configuration_id
                ).order_by(ConfigurationHistory.changed_at.desc())
            )
            return list(result.scalars().all())


