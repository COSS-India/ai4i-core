#!/usr/bin/env python3
"""
Simple script to start the inference service for testing
"""

import asyncio
import uvicorn
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Start the inference service"""
    try:
        from app_factory import create_inference_app
        from config import settings
        
        logger.info("🚀 Starting AI4I Inference Service...")
        logger.info(f"   Host: {settings.HOST}")
        logger.info(f"   Port: {settings.PORT}")
        logger.info(f"   Workers: {settings.WORKERS}")
        
        # Create app
        app = await create_inference_app()
        
        # Configure uvicorn
        config = uvicorn.Config(
            app,
            host=settings.HOST,
            port=settings.PORT,
            workers=settings.WORKERS,
            log_level=settings.LOG_LEVEL.lower(),
        )
        
        server = uvicorn.Server(config)
        await server.serve()
        
    except KeyboardInterrupt:
        logger.info("⛔ Service interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Service failed to start: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
