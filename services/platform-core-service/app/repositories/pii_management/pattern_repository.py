"""
Repository for pattern_library and geo_library.

Read-only at runtime: patterns and geo terms are loaded once at startup
by KnowledgeBaseService and cached in memory. Writes happen only through
Alembic migrations or the admin API (not modelled here yet).
"""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pii_management.pattern import GeoLibrary, PatternLibrary


class PatternRepository:
    """Read access to pattern_library and geo_library."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_active_patterns(self) -> List[PatternLibrary]:
        """Return all active regex patterns (all languages)."""
        result = await self._db.execute(
            select(PatternLibrary).where(PatternLibrary.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def get_active_geo_terms(self) -> List[GeoLibrary]:
        """Return all active geographic terms (suffixes and safe cities)."""
        result = await self._db.execute(
            select(GeoLibrary).where(GeoLibrary.is_active.is_(True))
        )
        return list(result.scalars().all())
