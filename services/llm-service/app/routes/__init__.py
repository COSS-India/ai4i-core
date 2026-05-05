"""Route aggregation with API versioning."""

from fastapi import APIRouter

from app.routes.openai_proxy import router as openai_proxy_router
from app.routes.inference import router as inference_router
from app.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(inference_router)
api_router.include_router(openai_proxy_router, prefix="/api/v1")
api_router.include_router(health_router)
