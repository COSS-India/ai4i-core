"""
OpenAI-compatible model listing.

Served at ``GET /api/v1/models`` so a client can use
``base_url="https://<host>/api/v1"``. The platform's own model catalogue moved
to ``GET /api/v1/modellist``.

Each entry is an ACTIVE, published LLM service. ``id`` is the service ``name``
(e.g. ``google/gemma-4-E4B-it``), matching how OpenAI ids read.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from app.dependencies.services import ServiceService, get_service_service
from app.schemas.model_management.model_openai import (
    OpenAIModel,
    OpenAIModelListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/models",
    tags=["OpenAI-compatible"],
)

# Only LLM services are listed — an OpenAI client sends these ids to the chat
# completions surface, which no other task type serves.
_TASK_TYPE = "llm"

# "Active" is the joined model's version_status; a DEPRECATED version stays
# published but must not be offered to clients.
_ACTIVE_VERSION_STATUS = "ACTIVE"

# OpenAI requires a string owner. The platform records an audit `createdBy`;
# this is the fallback for rows that have none (the column is nullable).
_DEFAULT_OWNER = "library"


def _created_unix(created_at: Optional[str]) -> Optional[int]:
    """Convert the serializer's ISO ``createdAt`` to a Unix timestamp."""
    if not created_at:
        return None
    try:
        return int(datetime.fromisoformat(created_at).timestamp())
    except ValueError:
        logger.warning("Unparseable service createdAt %r; omitting created", created_at)
        return None


@router.get(
    "",
    response_model=OpenAIModelListResponse,
    summary="List Models (OpenAI-compatible)",
)
async def list_models_openai(
    svc: ServiceService = Depends(get_service_service),
) -> OpenAIModelListResponse:
    """List ACTIVE published LLM services in the OpenAI ``GET /v1/models`` shape."""
    items, _ = await svc.list_services(task_types=[_TASK_TYPE], is_published=True)
    data = [
        OpenAIModel(
            id=item["name"],
            object="model",
            created=_created_unix(item.get("createdAt")),
            owned_by=item.get("createdBy") or _DEFAULT_OWNER,
        )
        for item in items
        if item.get("versionStatus") == _ACTIVE_VERSION_STATUS
    ]
    return OpenAIModelListResponse(object="list", data=data)
