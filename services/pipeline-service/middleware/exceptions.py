"""
Custom exception classes for authentication and authorization.
"""
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import time


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
    timestamp: float = time.time()


class ErrorResponse(BaseModel):
    """Error response model for consistent error responses."""
    detail: ErrorDetail
    status_code: int


class PipelineError(HTTPException):
    """Base exception for pipeline errors."""
    
    def __init__(self, message: str, error_code: str, status_code: int = 500, task_index: Optional[int] = None, task_type: Optional[str] = None, service_error: Optional[Dict] = None):
        self.message = message
        self.error_code = error_code
        self.task_index = task_index
        self.task_type = task_type
        self.service_error = service_error
        super().__init__(status_code=status_code, detail=message)


class PipelineTaskError(PipelineError):
    """Exception raised when a pipeline task fails."""
    
    def __init__(self, message: str, task_index: int, task_type: str, service_error: Optional[Dict] = None, error_code: str = "PIPELINE_TASK_ERROR"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=500,
            task_index=task_index,
            task_type=task_type,
            service_error=service_error
        )


class ServiceUnavailableError(PipelineError):
    """Exception raised when a service is unavailable."""
    
    def __init__(self, message: str, service_name: str, error_code: str = "SERVICE_UNAVAILABLE"):
        self.service_name = service_name
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=503,
            service_error={"service": service_name}
        )


class ModelNotFoundError(PipelineError):
    """Exception raised when a model is not found."""
    
    def __init__(self, message: str, model_name: str, service_name: str, error_code: str = "MODEL_NOT_FOUND"):
        self.model_name = model_name
        self.service_name = service_name
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=404,
            service_error={"model": model_name, "service": service_name}
        )







