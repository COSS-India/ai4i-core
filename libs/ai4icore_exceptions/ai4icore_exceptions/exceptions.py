"""
Shared exception classes for ALL AI4I-Core microservices.

Single hierarchy. Every service imports from here — no local exception files.

Base: AppError(HTTPException) with .message and .code fields.
All exceptions produce consistent {success, error: {code, message}} responses
via the shared register_exception_handlers().
"""

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import time


# =============================================================================
# Base
# =============================================================================

class AppError(HTTPException):
    """
    Base exception for all platform errors.
    Every exception carries: message (human), code (machine), status_code (HTTP).
    """

    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 400):
        self.message = message
        self.code = code
        super().__init__(status_code=status_code, detail=message)


# =============================================================================
# Authentication (401)
# =============================================================================

class AuthenticationError(AppError):
    """Base for all authentication failures."""

    def __init__(self, message: str = "Not authenticated", code: str = "AUTHENTICATION_REQUIRED"):
        super().__init__(message=message, code=code, status_code=401)


class AuthenticationRequiredError(AuthenticationError):
    def __init__(self, message: str = "Authentication is required."):
        super().__init__(message=message, code="AUTHENTICATION_REQUIRED")


class InvalidCredentialsError(AuthenticationError):
    def __init__(self, message: str = "Invalid email or password."):
        super().__init__(message=message, code="INVALID_CREDENTIALS")


class TokenExpiredError(AuthenticationError):
    def __init__(self, message: str = "Token has expired."):
        super().__init__(message=message, code="TOKEN_EXPIRED")


class TokenInvalidError(AuthenticationError):
    def __init__(self, message: str = "Token is invalid."):
        super().__init__(message=message, code="TOKEN_INVALID")


class TokenRevokedError(AuthenticationError):
    def __init__(self, message: str = "Token has been revoked."):
        super().__init__(message=message, code="TOKEN_REVOKED")


class InvalidTokenError(AuthenticationError):
    """Alias for TokenInvalidError (backward compat)."""
    def __init__(self, message: str = "Invalid authentication token"):
        super().__init__(message=message, code="TOKEN_INVALID")


class InvalidAPIKeyError(AuthenticationError):
    def __init__(self, message: str = "Invalid API key."):
        super().__init__(message=message, code="INVALID_API_KEY")


class ExpiredAPIKeyError(AuthenticationError):
    def __init__(self, message: str = "API key has expired."):
        super().__init__(message=message, code="API_KEY_EXPIRED")


class APIKeyRevokedError(AuthenticationError):
    def __init__(self, message: str = "API key has been revoked."):
        super().__init__(message=message, code="API_KEY_REVOKED")


# =============================================================================
# Authorization (403)
# =============================================================================

class AuthorizationError(AppError):
    """Base for all authorization failures."""

    def __init__(self, message: str = "Not authorized", code: str = "FORBIDDEN"):
        super().__init__(message=message, code=code, status_code=403)


class InsufficientPermissionsError(AuthorizationError):
    def __init__(self, resource: str = "", action: str = ""):
        msg = "You do not have permission to perform this action."
        if resource and action:
            msg = f"Missing permission: {resource}.{action}"
        super().__init__(message=msg, code="INSUFFICIENT_PERMISSIONS")


class UserInactiveError(AuthorizationError):
    def __init__(self, message: str = "User account is inactive."):
        super().__init__(message=message, code="USER_INACTIVE")


# =============================================================================
# Resource errors (404, 409)
# =============================================================================

class EntityNotFoundError(AppError):
    def __init__(self, entity: str = "Entity"):
        super().__init__(message=f"{entity} not found.", code="NOT_FOUND", status_code=404)


class UserNotFoundError(EntityNotFoundError):
    def __init__(self, message: str = "User not found."):
        AppError.__init__(self, message=message, code="USER_NOT_FOUND", status_code=404)


class DuplicateEntityError(AppError):
    def __init__(self, entity: str = "Entity", field: str = ""):
        msg = f"{entity} already exists."
        if field:
            msg = f"{entity} with this {field} already exists."
        super().__init__(message=msg, code="DUPLICATE_ENTITY", status_code=409)


# =============================================================================
# Validation (422)
# =============================================================================

class ValidationError(AppError):
    """Base for input validation errors."""

    def __init__(self, message: str = "Validation failed.", code: str = "VALIDATION_ERROR", errors: list[str] | None = None):
        self.errors = errors or []
        super().__init__(message=message, code=code, status_code=422)


class PasswordValidationError(ValidationError):
    def __init__(self, errors: list[str]):
        super().__init__(
            message="Password does not meet requirements.",
            code="PASSWORD_VALIDATION_ERROR",
            errors=errors,
        )


class PasswordMismatchError(ValidationError):
    def __init__(self, message: str = "Passwords do not match."):
        super().__init__(message=message, code="PASSWORD_MISMATCH")


# =============================================================================
# Tenant (400)
# =============================================================================

class TenantResolutionError(AppError):
    def __init__(self, message: str = "Could not resolve tenant."):
        super().__init__(message=message, code="TENANT_RESOLUTION_ERROR", status_code=400)


# =============================================================================
# Rate Limiting (429)
# =============================================================================

class RateLimitExceededError(AppError):
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message=message, code="RATE_LIMIT_EXCEEDED", status_code=429)


# =============================================================================
# Service / Infrastructure errors (500, 503)
# =============================================================================

class ServiceError(AppError):
    """Base for service-specific operational errors."""

    def __init__(self, message: str, error_code: str = "SERVICE_ERROR", status_code: int = 500, model_name: Optional[str] = None, service_error: Optional[dict] = None):
        self.error_code = error_code
        self.model_name = model_name
        self.service_error = service_error or {}
        super().__init__(message=message, code=error_code, status_code=status_code)


class TritonInferenceError(ServiceError):
    def __init__(self, message: str, model_name: Optional[str] = None, error_code: str = "TRITON_INFERENCE_ERROR"):
        super().__init__(
            message=message, error_code=error_code, status_code=503,
            model_name=model_name,
            service_error={"model": model_name, "service": "triton"} if model_name else {"service": "triton"},
        )


class ModelNotFoundError(ServiceError):
    def __init__(self, message: str, model_name: str, error_code: str = "MODEL_NOT_FOUND", service_name: Optional[str] = None):
        super().__init__(
            message=message, error_code=error_code, status_code=404,
            model_name=model_name,
            service_error={"model": model_name, "service": service_name} if service_name else {"model": model_name},
        )


class ServiceUnavailableError(ServiceError):
    def __init__(self, message: str, service_name: str = "unknown", error_code: str = "SERVICE_UNAVAILABLE"):
        super().__init__(
            message=message, error_code=error_code, status_code=503,
            service_error={"service": service_name},
        )


class AudioProcessingError(ServiceError):
    def __init__(self, message: str, error_code: str = "AUDIO_PROCESSING_ERROR"):
        super().__init__(message=message, error_code=error_code, status_code=422)


class TextProcessingError(ServiceError):
    def __init__(self, message: str, error_code: str = "TEXT_PROCESSING_ERROR"):
        super().__init__(message=message, error_code=error_code, status_code=422)


class UnpublishedServiceError(ServiceError):
    """Raised when inference is attempted on an unpublished service."""
    def __init__(self, service_id: str = ""):
        msg = "The requested service is unpublished." if not service_id else f"Service {service_id} is unpublished."
        self.service_id = service_id
        super().__init__(message=msg, error_code="SERVICE_UNPUBLISHED", status_code=403)


# =============================================================================
# Pipeline errors
# =============================================================================

class PipelineError(AppError):
    def __init__(self, message: str, error_code: str = "PIPELINE_ERROR", status_code: int = 500, task_index: Optional[int] = None, task_type: Optional[str] = None, service_error: Optional[Dict] = None):
        self.error_code = error_code
        self.task_index = task_index
        self.task_type = task_type
        self.service_error = service_error
        super().__init__(message=message, code=error_code, status_code=status_code)


class PipelineTaskError(PipelineError):
    def __init__(self, message: str, task_index: int, task_type: str, service_error: Optional[Dict] = None, error_code: str = "PIPELINE_TASK_ERROR"):
        super().__init__(
            message=message, error_code=error_code, status_code=500,
            task_index=task_index, task_type=task_type, service_error=service_error,
        )


# =============================================================================
# Error Response Models (for documentation / OpenAPI)
# =============================================================================

class ErrorDetail(BaseModel):
    message: str
    code: Optional[str] = None
    timestamp: float = 0.0
    details: Optional[str] = None

    def __init__(self, **data):
        if "timestamp" not in data or data["timestamp"] == 0.0:
            data["timestamp"] = time.time()
        super().__init__(**data)


class ErrorResponse(BaseModel):
    detail: ErrorDetail
    status_code: int


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base
    "AppError",
    # Authentication (401)
    "AuthenticationError",
    "AuthenticationRequiredError",
    "InvalidCredentialsError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenRevokedError",
    "InvalidTokenError",
    "InvalidAPIKeyError",
    "ExpiredAPIKeyError",
    "APIKeyRevokedError",
    # Authorization (403)
    "AuthorizationError",
    "InsufficientPermissionsError",
    "UserInactiveError",
    # Resource (404, 409)
    "EntityNotFoundError",
    "UserNotFoundError",
    "DuplicateEntityError",
    # Validation (422)
    "ValidationError",
    "PasswordValidationError",
    "PasswordMismatchError",
    # Tenant
    "TenantResolutionError",
    # Rate Limiting
    "RateLimitExceededError",
    # Service Errors
    "ServiceError",
    "TritonInferenceError",
    "ModelNotFoundError",
    "ServiceUnavailableError",
    "AudioProcessingError",
    "TextProcessingError",
    "UnpublishedServiceError",
    # Pipeline Errors
    "PipelineError",
    "PipelineTaskError",
    # Response Models
    "ErrorDetail",
    "ErrorResponse",
]
