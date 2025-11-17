from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import ServiceRegistry


class ServiceRegistryRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def register_service(
        self,
        service_name: str,
        service_url: str,
        health_check_url: Optional[str],
        status: str,
        service_metadata: Optional[dict],
    ) -> ServiceRegistry:
        async with self._session_factory() as session:  # type: AsyncSession
            result = await session.execute(
                select(ServiceRegistry).where(ServiceRegistry.service_name == service_name).with_for_update(of=ServiceRegistry)
            )
            existing = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if existing:
                existing.service_url = service_url
                existing.health_check_url = health_check_url
                existing.status = status
                existing.service_metadata = service_metadata or {}
                existing.updated_at = now
                await session.commit()
                await session.refresh(existing)
                return existing
            record = ServiceRegistry(
                service_name=service_name,
                service_url=service_url,
                health_check_url=health_check_url,
                status=status,
                service_metadata=service_metadata or {},
                registered_at=now,
                updated_at=now,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_service(self, service_name: str) -> Optional[ServiceRegistry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ServiceRegistry).where(ServiceRegistry.service_name == service_name)
            )
            return result.scalar_one_or_none()

    async def list_services(self, status: Optional[str] = None) -> List[ServiceRegistry]:
        async with self._session_factory() as session:
            q = select(ServiceRegistry)
            if status:
                q = q.where(ServiceRegistry.status == status)
            result = await session.execute(q)
            return list(result.scalars().all())

    async def update_service_status(self, service_name: str, status: str, last_health_check: Optional[datetime] = None) -> bool:
        async with self._session_factory() as session:
            values = {"status": status, "updated_at": datetime.now(timezone.utc)}
            if last_health_check is not None:
                values["last_health_check"] = last_health_check
            result = await session.execute(
                update(ServiceRegistry).where(ServiceRegistry.service_name == service_name).values(**values)
            )
            await session.commit()
            return result.rowcount > 0

    async def update_service_metadata(self, service_name: str, service_metadata: dict) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                update(ServiceRegistry)
                .where(ServiceRegistry.service_name == service_name)
                .values(service_metadata=service_metadata, updated_at=datetime.now(timezone.utc))
            )
            await session.commit()
            return result.rowcount > 0

    async def deregister_service(self, service_name: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(ServiceRegistry).where(ServiceRegistry.service_name == service_name)
            )
            await session.commit()
            return result.rowcount > 0

    async def get_healthy_services(self) -> List[ServiceRegistry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ServiceRegistry).where(ServiceRegistry.status == "healthy")
            )
            return list(result.scalars().all())


