"""Route aggregation for the Feedback service."""

from fastapi import APIRouter

from app.routes.feedback import router as feedback_router
from app.routes.correction import router as correction_router
from app.routes.evaluation import router as evaluation_router
from app.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(feedback_router)
api_router.include_router(correction_router)
api_router.include_router(evaluation_router)
