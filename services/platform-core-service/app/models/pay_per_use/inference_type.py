from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func

from app.models import Base


class InferenceType(Base):
    """Catalogue of billable inference types (llm, asr, nmt, ...).

    This table is the source of truth. It replaced a deploy-time YAML that
    shipped inside the ``ai4i-core`` package, so adding a type meant publishing
    the library and redeploying every service pinned to it; that file is gone as
    of phase 2. ``endpoint_patterns[0]`` is the canonical path and any further
    elements are aliases — the YAML expressed that as a separate
    ``endpoint_aliases`` list, and today only ``llm`` has one.
    """

    __tablename__ = "inference_types"
    __table_args__ = (
        UniqueConstraint("name", name="uq_inference_types_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    endpoint_patterns = Column(ARRAY(Text), nullable=False, server_default="{}")
    unit = Column(String(64), nullable=False)
    pricing = Column(String(64), nullable=False)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
