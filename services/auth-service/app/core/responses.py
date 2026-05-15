"""
API response envelope — re-exports from shared ai4icore_core.exceptions,
plus a tiny helper to render ORM objects through a Pydantic schema.
"""

from typing import Any

from pydantic import BaseModel

from ai4icore_core.exceptions import success_response, error_response  # noqa: F401


def to_response(obj: Any, schema: type[BaseModel], *, json_mode: bool = True) -> dict:
    """Validate an ORM row through ``schema`` and return its dict form.

    Replaces the boilerplate ``Schema.model_validate(obj, from_attributes=True)
    .model_dump(mode="json")`` repeated across route files.
    Pass ``json_mode=False`` to skip JSON-mode coercion (e.g. when the
    response builder will serialise types like UUID itself).
    """
    return schema.model_validate(obj, from_attributes=True).model_dump(
        mode="json" if json_mode else "python",
        by_alias=True,
    )


__all__ = ["success_response", "error_response", "to_response"]
