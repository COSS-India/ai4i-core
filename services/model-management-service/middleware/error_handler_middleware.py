"""
Global error handler middleware for consistent error responses.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    ErrorDetail,
    VersionAlreadyExistsError,
    VersionNotFoundError,
    ImmutableVersionError,
    ActiveVersionLimitExceededError,
    InvalidVersionFormatError,
    DeprecatedVersionError,
    ServiceVersionSwitchError
)

import time
import traceback
from logger import logger


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        error_detail = ErrorDetail(
            message=exc.message,
            code="AUTHENTICATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=401,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        error_detail = ErrorDetail(
            message=exc.message,
            code="AUTHORIZATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError):
        """Handle rate limit exceeded errors."""
        error_detail = ErrorDetail(
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=429,
            content={"detail": error_detail.dict()},
            headers={"Retry-After": str(exc.retry_after)}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="HTTP_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.error(f"Unexpected error: {exc}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )


    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning(f"Validation error at {request.url.path}: {exc.errors()}")
        errors = []
        for err in exc.errors():
            errors.append({
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", "")
            })
        return JSONResponse(status_code=422, content={"detail": errors})
    
    @app.exception_handler(VersionAlreadyExistsError)
    async def version_exists_error_handler(request: Request, exc: VersionAlreadyExistsError):
        """Handle version already exists errors."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="VERSION_ALREADY_EXISTS",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=409,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(VersionNotFoundError)
    async def version_not_found_error_handler(request: Request, exc: VersionNotFoundError):
        """Handle version not found errors."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="VERSION_NOT_FOUND",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=404,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(ImmutableVersionError)
    async def immutable_version_error_handler(request: Request, exc: ImmutableVersionError):
        """Handle immutable version modification attempts."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="IMMUTABLE_VERSION",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(ActiveVersionLimitExceededError)
    async def version_limit_error_handler(request: Request, exc: ActiveVersionLimitExceededError):
        """Handle active version limit exceeded errors."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="ACTIVE_VERSION_LIMIT_EXCEEDED",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=400,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(InvalidVersionFormatError)
    async def invalid_version_format_error_handler(request: Request, exc: InvalidVersionFormatError):
        """Handle invalid version format errors."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="INVALID_VERSION_FORMAT",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=422,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(DeprecatedVersionError)
    async def deprecated_version_error_handler(request: Request, exc: DeprecatedVersionError):
        """Handle deprecated version usage errors."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="DEPRECATED_VERSION",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=400,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(ServiceVersionSwitchError)
    async def service_version_switch_error_handler(request: Request, exc: ServiceVersionSwitchError):
        """Handle service version switch errors."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="SERVICE_VERSION_SWITCH_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=400,
            content={"detail": error_detail.dict()}
        )