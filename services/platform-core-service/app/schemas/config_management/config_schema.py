from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta

_EXAMPLE_TYPE = "domain"
_EXAMPLE_DATA = ["healthcare", "global", "general"]
_EXAMPLE_USER = "user-uuid-or-username"
_EXAMPLE_TS = "2026-11-04T10:00:00Z"

_EXAMPLE_ITEM = {
    "id": 1,
    "type": _EXAMPLE_TYPE,
    "data": _EXAMPLE_DATA,
    "created_by": _EXAMPLE_USER,
    "created_at": _EXAMPLE_TS,
    "updated_by": _EXAMPLE_USER,
    "updated_at": _EXAMPLE_TS,
}


class ConfigCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": _EXAMPLE_TYPE,
                "data": _EXAMPLE_DATA,
            }
        }
    )

    type: str = Field(..., min_length=1, max_length=255, description="Config type identifier (e.g. 'domain').")
    data: Any = Field(..., description="Config payload — any valid JSON value (object, array, string, etc.).")

    @field_validator("type", mode="before")
    @classmethod
    def type_not_blank(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            raise ValueError("type cannot be blank")
        return v

    @field_validator("data", mode="before")
    @classmethod
    def data_not_null(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("data is required and cannot be null")
        return v


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": _EXAMPLE_TYPE,
                "data": _EXAMPLE_DATA,
            }
        }
    )

    type: Optional[str] = Field(None, min_length=1, max_length=255, description="Config type identifier. Omit to leave unchanged.")
    data: Optional[Any] = Field(None, description="Config payload. Omit to leave unchanged.")

    @field_validator("type", mode="before")
    @classmethod
    def type_not_null_or_blank(cls, v: Any) -> Any:
        # Field omitted → default None → validator not called (validate_default=False).
        # Field explicitly sent as null → validator called with v=None → reject.
        if v is None:
            raise ValueError("type cannot be null; omit the field to leave it unchanged")
        if isinstance(v, str) and not v.strip():
            raise ValueError("type cannot be blank")
        return v

    @field_validator("data", mode="before")
    @classmethod
    def data_not_null(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("data cannot be null; omit the field to leave it unchanged")
        return v


class ConfigItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"example": _EXAMPLE_ITEM},
    )

    id: int
    type: str
    data: Any
    created_by: Optional[str] = None
    created_at: datetime
    updated_by: Optional[str] = None
    updated_at: datetime


class ConfigListData(BaseModel):
    items: List[ConfigItem]


class ConfigDeletedData(BaseModel):
    id: int


# ── Route response envelopes ──


class CreateConfigResponse(SuccessResponseWithMeta):
    """POST /config"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": _EXAMPLE_ITEM,
                "meta": {"message": f"Config '{_EXAMPLE_TYPE}' created."},
            }
        }
    )

    data: ConfigItem
    meta: MessageMeta


class GetConfigResponse(SuccessResponse):
    """GET /config/{config_id}"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": _EXAMPLE_ITEM,
            }
        }
    )

    data: ConfigItem


class ListConfigResponse(SuccessResponse):
    """GET /config"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"items": [_EXAMPLE_ITEM]},
            }
        }
    )

    data: ConfigListData


class UpdateConfigResponse(SuccessResponseWithMeta):
    """PUT /config/{config_id}"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": _EXAMPLE_ITEM,
                "meta": {"message": f"Config '{_EXAMPLE_TYPE}' updated."},
            }
        }
    )

    data: ConfigItem
    meta: MessageMeta


class DeleteConfigResponse(SuccessResponseWithMeta):
    """DELETE /config/{config_id}"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"id": 1},
                "meta": {"message": "Config 1 deleted."},
            }
        }
    )

    data: ConfigDeletedData
    meta: MessageMeta
