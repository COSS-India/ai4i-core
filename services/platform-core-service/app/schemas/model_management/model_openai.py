"""
OpenAI-compatible model listing schemas.

Field names are the OpenAI wire format verbatim (``object``, ``owned_by``) —
snake_case here is deliberate and must not be camelCased like the v1 schemas,
since clients point an OpenAI SDK at this route.
"""

from typing import List, Optional

from app.schemas.base import BaseSchema


class OpenAIModel(BaseSchema):
    """A single entry in an OpenAI-style ``GET /v1/models`` listing."""

    id: str
    object: str = "model"
    created: Optional[int] = None
    owned_by: str


class OpenAIModelListResponse(BaseSchema):
    """Envelope for the OpenAI-style listing — no success/meta wrapper by design."""

    object: str = "list"
    data: List[OpenAIModel]
