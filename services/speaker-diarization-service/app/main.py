"""Speaker Diarization Service -- FastAPI application factory."""

from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="speaker-diarization-service",
    title="Speaker Diarization Service",
    description="Speaker Diarization microservice using Triton Inference Server.",
    api_prefix="/api/v1/speaker-diarization",
    router=api_router,
    db_base=Base,
)
