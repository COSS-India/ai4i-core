"""Language Detection Service -- FastAPI application factory."""

from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="language-detection-service",
    title="Language Detection Service",
    description="Language detection microservice for identifying text language and script (IndicLID).",
    api_prefix="/api/v1/language-detection",
    router=api_router,
    db_base=Base,
)
