"""Route aggregation with API versioning."""

from fastapi import APIRouter

from app.routes.inference import router as inference_router
from app.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(inference_router)
api_router.include_router(health_router)

# Try-it router (optional)
try:
    from app.routes.try_it import router as try_it_router
    api_router.include_router(try_it_router)
except ImportError:
    pass
