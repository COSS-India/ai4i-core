"""
Inference Service - Main entry point
Unified inference endpoint for all task services (NMT, ASR, OCR, NER, LLM, etc.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Configure logging FIRST before importing anything else
from ai4icore_core.logging import configure_logging

configure_logging(service_name="ai4x-inference", log_level="INFO")

# NOW import the rest
import uvicorn
from app_factory import create_inference_app
from config import settings

app = create_inference_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
    )
