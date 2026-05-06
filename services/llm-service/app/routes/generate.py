# POST /api/v1/llm/chat/completion  → messages  → choices[0].message.content
# POST /api/v1/llm/generate        → prompt     → choices[0].text
# OpenAI-shaped JSON; paths under /api/v1/llm for the API gateway.

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ai4icore_multi_tenant import enforce_tenant_and_service_checks as _mt_service_checks

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_llm_service
from app.request_context import optional_db_user_id
from app.schemas.inference import GenerateRequest, GenerateResponse
from app.services.llm_service import LLMService

router = APIRouter(tags=["generate"], dependencies=[Depends(AuthProvider)])


async def enforce_llm_checks(request: Request):
    await _mt_service_checks(
        request,
        service_name="llm",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="LLM service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect LLM service availability. Please contact your administrator",
        timeout_message="LLM service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="LLM service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_llm_checks))


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    http_request: Request,
    llm_service: LLMService = Depends(get_llm_service),
) -> GenerateResponse:
    print(">>> Generate request received")
    if body.stream:
        return JSONResponse(
            status_code=501,
            content={
                "error": {
                    "message": "Streaming is not implemented yet.",
                    "type": "not_implemented_error",
                    "param": "stream",
                    "code": None,
                }
            },
        )
    if body.n is not None and body.n != 1:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "Only n=1 is supported.",
                    "type": "invalid_request_error",
                    "param": "n",
                    "code": None,
                }
            },
        )

    request_id = str(uuid.uuid4()).replace("-", "")[:24]
    user_id = optional_db_user_id(http_request)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)
    return await llm_service.run_generate(
        body,
        request_id,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )
