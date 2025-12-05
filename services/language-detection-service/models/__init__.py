"""
Models
Pydantic and SQLAlchemy models
"""

from .database_models import (
    LanguageDetectionRequestDB,
    LanguageDetectionResultDB
)

__all__ = [
    "LanguageDetectionRequestDB",
    "LanguageDetectionResultDB"
]
