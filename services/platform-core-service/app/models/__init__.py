"""
SQLAlchemy ORM models for platform-core-service.

Tables are placed in the public schema (models, services).
Import order: Model first (FK dependency for Service).
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.models.model import Model  # noqa: E402
from app.models.service import Service  # noqa: E402

__all__ = [
    "Base",
    "Model",
    "Service",
]
