"""
OAuthProvider table queries.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth import OAuthProvider


class OAuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_provider(self, provider_name: str, provider_user_id: str) -> Optional[OAuthProvider]:
        result = await self._db.execute(
            select(OAuthProvider).where(
                OAuthProvider.provider_name == provider_name,
                OAuthProvider.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_user_providers(self, user_id: int) -> list[OAuthProvider]:
        result = await self._db.execute(
            select(OAuthProvider).where(OAuthProvider.user_id == user_id)
        )
        return list(result.scalars().all())

    async def create(self, provider: OAuthProvider) -> OAuthProvider:
        self._db.add(provider)
        await self._db.flush()
        return provider

    async def update_tokens(self, provider: OAuthProvider, access_token: str, refresh_token: Optional[str]) -> None:
        provider.access_token = access_token
        if refresh_token:
            provider.refresh_token = refresh_token
        await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()
