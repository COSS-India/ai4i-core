"""Language Diarization Service -- FastAPI application factory."""

from ai4icore_env import app_env
from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="language-diarization-service",
    title="Language Diarization Service",
    description="Language diarization microservice for segmenting audio by spoken language.",
    api_prefix="/api/v1/language-diarization",
    router=api_router,
    db_base=Base,
    extra_state={
        "triton_timeout": getattr(app_env, "triton_timeout", 300.0),
    },
)
