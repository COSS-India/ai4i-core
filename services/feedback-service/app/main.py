"""Feedback Service -- FastAPI application factory."""

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(str(_static_dir / "dashboard.html"))
