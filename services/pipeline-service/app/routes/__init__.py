"""Route aggregation with API versioning."""

from fastapi import APIRouter

from app.routes.pipeline import pipeline_router
from app.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(pipeline_router)
api_router.include_router(health_router)
