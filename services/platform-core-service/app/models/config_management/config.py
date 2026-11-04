from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models import Base


class Config(Base):
    __tablename__ = "configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(255), nullable=False)
    data = Column(JSONB, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
