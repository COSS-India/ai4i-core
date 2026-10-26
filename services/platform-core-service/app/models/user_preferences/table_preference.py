"""ORM model for the user_table_preferences table.

One row per (user, view): the column ids the user chose to
show in that table. Generic over ``view_key`` so other tables can reuse it.
"""

import uuid

from sqlalchemy import Column, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models import Base


class UserTablePreference(Base):
    __tablename__ = "user_table_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "view_key", name="uq_user_table_preferences_user_view"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    view_key = Column(String(64), nullable=False)
    visible_columns = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
