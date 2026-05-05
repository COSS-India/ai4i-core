"""Route aggregation with API versioning."""

from fastapi import APIRouter

from app.routes import chat_completions, completions
from app.routes.inference import router as inference_router
from app.routes.health import router as health_router
from app.routes.vllm_endpoints import router as vllm_router

api_router = APIRouter()
api_router.include_router(inference_router)
api_router.include_router(chat_completions.router, prefix="/api/v1")
api_router.include_router(completions.router, prefix="/api/v1")
api_router.include_router(health_router)
