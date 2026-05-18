"""
Inference Service - Main entry point
Unified inference endpoint for all task services (NMT, ASR, OCR, NER, LLM, etc.)
"""

import uvicorn
import asyncio
from app_factory import create_inference_app
from config import settings


async def main():
    """Main async entry point for inference service."""
    app = await create_inference_app()
    
    config = uvicorn.Config(
        app,
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
