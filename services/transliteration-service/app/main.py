"""Transliteration Service -- FastAPI application factory."""

from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="transliteration-service",
    title="Transliteration Service",
    description="Transliteration microservice for converting text between scripts using Triton Inference Server.",
    api_prefix="/api/v1/transliteration",
    router=api_router,
    db_base=Base,
)
