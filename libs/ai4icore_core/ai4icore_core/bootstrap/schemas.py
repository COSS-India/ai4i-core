"""
Base Pydantic schema for ALL microservices.
"""

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema for all request/response models across all services."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )
