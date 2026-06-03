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
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app_factory import create_inference_app
from config import settings

def _build_app():
    """Expose the async-built app at module level for `uvicorn main:app --reload`.

    uvicorn imports this module inside a running loop, so asyncio.run() must run
    in a separate thread. Safe because the factory opens no connections at build
    time — they connect in the FastAPI "startup" event on the serving loop.
    """
    # One throwaway thread; the app is built exactly once.
    with ThreadPoolExecutor() as ex:
        return ex.submit(lambda: asyncio.run(create_inference_app())).result()


app = _build_app()


async def main():
    """Main async entry point for inference service."""
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
