"""Routes package initialization."""

from fastapi import APIRouter

from routes.inference import router as inference_router
from routes.pii import router as pii_router

router = APIRouter()
router.include_router(inference_router)
router.include_router(pii_router)

__all__ = ["router"]
