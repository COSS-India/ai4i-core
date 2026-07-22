"""
Async repository for the Feedback entity (ef_feedback).
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback.feedback import Feedback


class FeedbackRepository:
    """Persistence layer for `ef_feedback`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_request_id(self, request_id: UUID) -> Optional[Feedback]:
        result = await self._db.execute(
            select(Feedback).where(Feedback.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(self, entity: Feedback) -> Feedback:
        """Insert a new feedback row, or update the existing one for the
        same request_id — one feedback per request, per the spec ("a second
        submission for the same requestId updates the first")."""
        values = {
            "id": entity.id,
            "request_id": entity.request_id,
            "model_task_type": entity.model_task_type,
            "feedback_type": entity.feedback_type,
            "rating": entity.rating,
            "reasons": entity.reasons,
            "comments": entity.comments,
            "corrected_output": entity.corrected_output,
            "model_provider": entity.model_provider,
            "model_version": entity.model_version,
            "model_id": entity.model_id,
            "tenant_id": entity.tenant_id,
            "source_language": entity.source_language,
            "target_language": entity.target_language,
            "language_info": entity.language_info,
            "feedback_language": entity.feedback_language,
            "feedback_source": entity.feedback_source,
            "created_by": entity.created_by,
        }
        # id/request_id are the conflict key and the row's identity — never
        # overwritten on update, so a repeat submission keeps the same
        # feedbackId and original request_id.
        update_values = {
            k: v for k, v in values.items() if k not in ("id", "request_id")
        }
        update_values["updated_at"] = func.now()

        stmt = (
            insert(Feedback)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["request_id"],
                set_=update_values,
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()
        return await self.get_by_request_id(entity.request_id)


    async def get_
