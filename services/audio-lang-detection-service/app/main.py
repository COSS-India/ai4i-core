"""Audio Language Detection Service -- FastAPI application factory."""

from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="audio-lang-detection-service",
    title="Audio Language Detection Service",
    description="Audio Language Detection microservice using Triton Inference Server.",
    api_prefix="/api/v1/audio-lang-detection",
    router=api_router,
    db_base=Base,
)
