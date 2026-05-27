"""
Main FastAPI application factory for inference service.
Creates and configures the unified inference service with all components.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ai4icore_core.telemetry import TraceIDMiddleware
from typing import Optional, Any
import logging

from ai4icore_core.observability import setup_observability

from routes import router
from config import settings


logger = logging.getLogger(__name__)


class InferenceServiceFactory:
    """
    Factory for creating and configuring the inference service application.
    Handles dependency setup, middleware configuration, and lifecycle management.
    """

    @staticmethod
    async def create_app(
        settings: Optional[Any] = None,
    ) -> FastAPI:
        """
        Create and configure FastAPI application for inference service.

        Args:
            settings: Optional application settings (uses default if None)

        Returns:
            Configured FastAPI application
        """
        return FastAPI(
            title="AI4I Inference Service",
            description="Unified inference endpoint for all task services",
            version="1.0.0"
        )

    @staticmethod
    async def setup_dependencies(app: FastAPI, settings: Any) -> None:
        """
        Setup all service dependencies (Redis, DB, Model Management client, etc.).

        Args:
            app: FastAPI application instance
            settings: Application settings
        """
        logger.info("Setting up service dependencies...")
        # Dependencies will be injected via dependency injection in routes
        logger.info("✓ Dependencies setup complete")

    @staticmethod
    async def setup_middleware(app: FastAPI) -> None:
        """
        Configure middleware for CORS, auth, rate limiting, etc.

        Args:
            app: FastAPI application instance
        """
        logger.info("Setting up middleware...")
        
        # Trace ID middleware (must be first to capture all requests)
        app.add_middleware(TraceIDMiddleware)
        
        # CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Observability — Prometheus /metrics + per-request middleware.
        # Reads OBSERVE_UTIL_* env vars (enabled, debug, metrics_path).
        # Returns a MetricsCollector if you ever want to emit custom
        # metrics from inside route handlers (e.g. tokenizer-accurate
        # LLM token counts post-inference).
        setup_observability(app)

        logger.info("✓ Middleware setup complete")

    @staticmethod
    async def setup_routes(app: FastAPI) -> None:
        """
        Register all routes/routers with the application.

        Args:
            app: FastAPI application instance
        """
        logger.info("Setting up routes...")

        # Include inference router
        app.include_router(router, prefix=settings.API_PREFIX)

        # Health check endpoint — excluded from Swagger; used only by Docker HEALTHCHECK
        @app.get("/health", include_in_schema=False)
        async def health_check():
            return {"status": "healthy"}

        logger.info("✓ Routes setup complete")

    @staticmethod
    async def setup_exception_handlers(app: FastAPI) -> None:
        """
        Configure exception handlers for different error types.

        Args:
            app: FastAPI application instance
        """
        from fastapi.responses import JSONResponse
        from fastapi.exceptions import RequestValidationError

        logger.info("Setting up exception handlers...")

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request, exc):
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)}
            )

        @app.exception_handler(Exception)
        async def general_exception_handler(request, exc):
            logger.error(f"Unhandled exception: {exc}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )

        logger.info("✓ Exception handlers setup complete")

    @staticmethod
    async def setup_lifespan_events(app: FastAPI) -> None:
        """
        Configure startup and shutdown event handlers.

        Args:
            app: FastAPI application instance
        """
        logger.info("Setting up lifespan events...")

        @app.on_event("startup")
        async def startup():
            logger.info("✓ Inference service started")

        @app.on_event("shutdown")
        async def shutdown():
            logger.info("✓ Inference service shutting down")

        logger.info("✓ Lifespan events setup complete")


async def create_inference_app() -> FastAPI:
    """
    Entry point for creating the inference service application.
    Uses factory to construct fully configured app with all components wired.

    Returns:
        Configured FastAPI application ready to serve inference requests
    """
    factory = InferenceServiceFactory()

    # Create FastAPI app with OpenAPI docs
    app = FastAPI(
        title="AI4I Inference Service",
        description="Unified inference endpoint for NMT, ASR, OCR, NER, LLM and other task services",
        version="1.0.0",
        docs_url="/docs",
        openapi_url="/openapi.json"
    )

    # Setup all components
    await factory.setup_dependencies(app, settings)
    await factory.setup_middleware(app)
    await factory.setup_routes(app)
    await factory.setup_exception_handlers(app)
    await factory.setup_lifespan_events(app)

    logger.info("✓ Inference service application created and configured")
    return app


async def on_startup(app: FastAPI) -> None:
    """
    Startup event handler.
    Initializes connections and validates configuration.

    Args:
        app: FastAPI application instance
    """
    logger.info("Starting up inference service...")


async def on_shutdown(app: FastAPI) -> None:
    """
    Shutdown event handler.
    Closes connections and cleanup resources.

    Args:
        app: FastAPI application instance
    """
    logger.info("Shutting down inference service...")
