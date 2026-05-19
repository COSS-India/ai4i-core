"""OCR Service -- FastAPI application factory."""

from ai4icore_env import app_env
from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

ENV_DEVELOPMENT = "development"
hide_docs = app_env.environment != ENV_DEVELOPMENT

app = create_inference_app(
    service_name="ocr-service",
    title="OCR Service",
    description="Optical Character Recognition microservice using Surya OCR via Triton Inference Server.",
    api_prefix="/api/v1/ocr",
    router=api_router,
    db_base=Base,
    hide_docs=hide_docs,
)
