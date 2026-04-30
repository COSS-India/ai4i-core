"""LLM Service -- FastAPI application factory."""

from ai4icore_env import app_env
from ai4icore_service_base import create_inference_app

from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="llm-service",
    title="LLM Service",
    description="Large Language Model microservice for text processing, translation, and generation.",
    api_prefix="/api/v1/llm",
    router=api_router,
    db_base=Base,
    extra_state={
        "triton_endpoint": app_env.triton_endpoint,
        "triton_timeout": app_env.triton_timeout,
    },
)
