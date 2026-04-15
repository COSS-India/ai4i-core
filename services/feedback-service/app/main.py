"""Feedback Service -- FastAPI application factory."""

from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="feedback-service",
    title="Feedback Service",
    description=(
        "RLAIF feedback pipeline: implicit telemetry ingestion, "
        "LLM-based quality evaluation, and human-in-the-loop correction "
        "for NMT/ASR/TTS/OCR model improvement."
    ),
    version="1.0.0",
    api_prefix="/api/v1/feedback",
    router=api_router,
    db_base=Base,
)
