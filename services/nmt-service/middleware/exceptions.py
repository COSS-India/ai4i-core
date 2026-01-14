"""
Custom exception classes for authentication and authorization.
"""
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional


class AuthenticationError(HTTPException):
    """Exception raised for authentication errors."""
    
    def __init__(self, message: str = "Not authenticated", status_code: int = 401):
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class AuthorizationError(HTTPException):
    """Exception raised for authorization errors."""
    
    def __init__(self, message: str = "Not authorized", status_code: int = 403):
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class InvalidAPIKeyError(AuthenticationError):
    """Exception raised for invalid API key."""
    
    def __init__(self, message: str = "Invalid API key"):
        super().__init__(message=message, status_code=401)


class ExpiredAPIKeyError(AuthenticationError):
    """Exception raised for expired API key."""
    
    def __init__(self, message: str = "API key has expired"):
        super().__init__(message=message, status_code=401)


class RateLimitExceededError(HTTPException):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.message = message
        self.retry_after = retry_after
        super().__init__(
            status_code=429, 
            detail=message, 
            headers={"Retry-After": str(retry_after)}
        )


class InvalidTokenError(AuthenticationError):
    """Exception raised for invalid authentication token."""
    
    def __init__(self, message: str = "Invalid authentication token"):
        super().__init__(message=message, status_code=401)


class ErrorDetail(BaseModel):
    """Error detail model for consistent error responses."""
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model for consistent error responses."""
    detail: ErrorDetail
    status_code: int


class ServiceError(HTTPException):
    """Base exception for service-specific errors."""
    
    def __init__(self, message: str, error_code: str, status_code: int = 500, model_name: Optional[str] = None, service_error: Optional[dict] = None):
        self.message = message
        self.error_code = error_code
        self.model_name = model_name
        self.service_error = service_error or {}
        super().__init__(status_code=status_code, detail=message)


class TritonInferenceError(ServiceError):
    """Exception raised when Triton inference fails."""
    
    def __init__(self, message: str, model_name: Optional[str] = None, error_code: str = "TRITON_INFERENCE_ERROR"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=503,
            model_name=model_name,
            service_error={"model": model_name, "service": "triton"} if model_name else {"service": "triton"}
        )


class ModelNotFoundError(ServiceError):
    """Exception raised when a model is not found."""
    
    def __init__(self, message: str, model_name: str, error_code: str = "MODEL_NOT_FOUND"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=404,
            model_name=model_name,
            service_error={"model": model_name, "service": "nmt"}
        )


class ServiceUnavailableError(ServiceError):
    """Exception raised when a service is unavailable."""
    
    def __init__(self, message: str, service_name: str = "nmt", error_code: str = "SERVICE_UNAVAILABLE"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=503,
            service_error={"service": service_name}
        )


class TextProcessingError(ServiceError):
    """Exception raised when text processing fails."""
    
    def __init__(self, message: str, error_code: str = "TEXT_PROCESSING_ERROR"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=422
        )
