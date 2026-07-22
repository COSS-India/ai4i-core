"""
Async repository for the FeedbackReason entity (ef_feedback_reason).
"""

from sqlalchemy import func, select
from sqlalchemy.engine.row import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback.feedback_reasons import FeedbackReason


class FeedbackReasonRepository:
    """Persistence layer for `ef_feedback_reason`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_task_type_with_language(
        self, task_types: list[str], lang: str | None
    ) -> list[Row]:
        """Active reasons for one or more (already-lowercased) task types,
        one query via `task_type IN (...)`, ordered by task_type then
        sort_order. `label` is resolved to `lang`'s translation at the DB
        level: `label_i18n ->> lang`, falling back to the default `label`
        column when that key is absent (missing column or NULL key) via
        COALESCE — label_i18n is a single-level {lang: str} map (see
        a3c1e9f27b6d), so a single `->>` is enough, no path traversal. When
        lang is None, `label` is the default column, no i18n lookup."""
        label = (
            func.coalesce(FeedbackReason.label_i18n[lang].astext, FeedbackReason.label)
            if lang
            else FeedbackReason.label
        ).label("label")
        result = await self._db.execute(
            select(FeedbackReason.task_type, FeedbackReason.code, label)
            .where(
                FeedbackReason.task_type.in_(task_types),
                FeedbackReason.is_active.is_(True),
            )
            .order_by(FeedbackReason.task_type, FeedbackReason.sort_order)
        )
        return list(result.all())

    async def get_all(self) -> list[FeedbackReason]:
        result = await self._db.execute(
            select(FeedbackReason)
            .where(FeedbackReason.is_active.is_(True))
            .order_by(FeedbackReason.task_type, FeedbackReason.sort_order)
        )
        return list(result.scalars().all())
