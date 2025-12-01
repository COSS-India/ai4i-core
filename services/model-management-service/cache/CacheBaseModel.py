from datetime import datetime
from typing import Optional
from pydantic import Field, model_validator , ConfigDict
from redis_om import HashModel, Field as RedisField
from redis_om.model.model import PrimaryKey
from uuid import UUID as _UUID
from pydantic import BaseModel
import json

from .app_cache import get_cache_connection

# Fields to skip completely
EXCLUDED_FIELDS = ["id", "key", "services"]

# Allowed field types for Redis storage
# (no mongo-specific types here)
ACCEPTED_FIELD_TYPES = (str, int, float, bool, datetime, _UUID,dict,list)


class CacheBaseModel(HashModel):
    id: Optional[str] = Field(default=None, alias="_id")

    class Meta:
        global_key_prefix = "AI4x"
        database = get_cache_connection()
        primary_key: Optional[PrimaryKey] = None
        embedded = False
        encoding = "utf-8"

    model_config = ConfigDict(
        extra="ignore",          # Ignore unknown fields
        populate_by_name=False,  # Do NOT allow using alias for population
    )


@model_validator(mode="before")
def validate_fields(cls, values):
    """
    Filters and formats values before writing to Redis.
    Removes unwanted fields & converts datetimes/booleans.
    """
    if not isinstance(values, dict):
        return values
    values = dict(values)  # avoid mutating original input
    for key in list(values.keys()):
        val = values[key]
        # Skip excluded fields
        if (key not in cls.__fields__ and key != "_id") or (
            type(val) not in ACCEPTED_FIELD_TYPES
        ):
            # Handle special case for "task"
            if key == "task" and cls.__name__ == "ModelCache":
                values["task_type"] = val.get("type")
            # values.pop(key, None)
            continue

        if isinstance(val, (dict, list, BaseModel)):
            values[key] = json.dumps(
                val if not isinstance(val, BaseModel) else val.model_dump()
            )
            continue
        # Normalize datatypes
        if isinstance(val, datetime):
            values[key] = val.isoformat()
        elif isinstance(val, bool):
            values[key] = str(val)
    return values

# @model_validator(mode="before")
# def validate_fields(cls, values):
#     """
#     Convert all nested structures to JSON strings before writing to Redis.
#     """
#     if not isinstance(values, dict):
#         return values

#     values = dict(values)

#     for key, val in list(values.items()):

#         # Convert dict / list / BaseModel to JSON string
#         if isinstance(val, (dict, list, BaseModel)):
#             values[key] = json.dumps(
#                 val if not isinstance(val, BaseModel) else val.model_dump()
#             )
#             continue

#         # Normalize datatypes
#         if isinstance(val, datetime):
#             values[key] = val.isoformat()

#         elif isinstance(val, bool):
#             values[key] = str(val)

#     return values


def generate_cache_model(cls, primary_key_field: str):
    """
    Generate Redis OM hash fields from a Pydantic v2 model.
    """
    model_definition = {}

    for key, field in cls.model_fields.items():
        if key in EXCLUDED_FIELDS:
            continue

        field_type = field.annotation  # Pydantic v2 

        # Primary key
        if key == primary_key_field:
            model_definition[key] = (str, RedisField(..., primary_key=True))
            continue

        # Simple accepted values
        if field_type in ACCEPTED_FIELD_TYPES:
            model_definition[key] = (field_type, RedisField(...))
            continue

        # Special case: task
        if key == "task":
            model_definition["task_type"] = (str, RedisField(...))
            continue

        # Handle lists → flatten into strings
        # if getattr(field_type, "__origin__", None) == list:
        #     model_definition[key] = (str, RedisField(default=""))
        #     continue

        if field_type == list or field_type == dict or getattr(field_type, "__origin__", None) in (list, dict):
            model_definition[key] = (str, RedisField(default=""))
            continue
        

        # if issubclass(field_type, BaseModel):
        #     model_definition[key] = (str, RedisField(default=""))
        #     continue

    return model_definition

