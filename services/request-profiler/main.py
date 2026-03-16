
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from ai4icore_logging import get_logger

    logger = get_logger(__name__)
except Exception:  # pragma: no cover – fallback when lib not installed
    logger = logging.getLogger(__name__)

from routers.profile_router import router as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service startup and graceful shutdown."""
    logger.info(
        "Starting Request Profiler Service...",
        extra={"context": {"event": "startup"}},
    )
    yield
    logger.info(
        "Shutting down Request Profiler Service...",
        extra={"context": {"event": "shutdown"}},
    )


app = FastAPI(
    title="Request Profiler Service",
    version="1.0.0",
    description=(
        "Microservice that profiles text for domain and complexity analysis "
        "by proxying requests to the upstream profiler API."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile_router)


@app.get("/health", tags=["health"])
async def health():
    """Root health check used by Docker / load-balancers."""
    return {"status": "ok", "service": "request-profiler-service"}


@app.get("/api/v1/health", tags=["health"])
async def api_health():
    """Versioned health check endpoint."""
    return {"status": "ok", "service": "request-profiler-service"}


def get_app() -> FastAPI:
    """Uvicorn entrypoint helper."""
    return app


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
