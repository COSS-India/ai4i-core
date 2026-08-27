from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.sql import func

from app.models import Base


class InferenceType(Base):
    """Catalogue of billable inference types.

    Replaces the deploy-time YAML (``ai4i_core/ppu/inference_types.yaml``) as the
    single source of truth so inference types can be added/edited without a
    release, and so ``ppu_tier_quotas`` / ``ppu_quota_usage`` can eventually
    reference a real FK instead of the free-text ``inference_name`` column.
    """

    __tablename__ = "inference_types"
    __table_args__ = (
        UniqueConstraint("name", name="uq_inference_types_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    # One type can be served on several paths (llm answers both /api/v1/chat and
    # /api/v1/chat/completions), so patterns are an array rather than a scalar.
    endpoint_patterns = Column(ARRAY(TEXT), nullable=False, server_default=text("'{}'"))
    unit = Column(String(64), nullable=False)
    pricing = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
