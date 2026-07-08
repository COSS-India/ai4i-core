"""
Rate limiting using slowapi.

Used by ALL microservices. Defense-in-depth alongside APISIX.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri="memory://",
)


def setup_rate_limiting(app: FastAPI) -> None:
    """Register rate limiter and error handler on any FastAPI app."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded: {exc.detail}",
                },
            },
        )
