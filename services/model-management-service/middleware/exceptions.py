"""
Custom exception classes for authentication and authorization.
"""
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
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


class VersionAlreadyExistsError(HTTPException):
    """Exception raised when a model version already exists."""
    
    def __init__(self, message: str = "Version already exists"):
        super().__init__(status_code=409, detail=message)


class VersionNotFoundError(HTTPException):
    """Exception raised when a model version is not found."""
    
    def __init__(self, message: str = "Version not found"):
        super().__init__(status_code=404, detail=message)


class ImmutableVersionError(HTTPException):
    """Exception raised when attempting to modify an immutable version."""
    
    def __init__(self, message: str = "Version is immutable and cannot be modified"):
        super().__init__(status_code=403, detail=message)


class ActiveVersionLimitExceededError(HTTPException):
    """Exception raised when active version limit is exceeded."""
    
    def __init__(self, message: str = "Active version limit exceeded"):
        super().__init__(status_code=400, detail=message)


class InvalidVersionFormatError(HTTPException):
    """Exception raised when version format is invalid."""
    
    def __init__(self, message: str = "Invalid version format"):
        super().__init__(status_code=422, detail=message)


class DeprecatedVersionError(HTTPException):
    """Exception raised for service operations on deprecated versions."""
    
    def __init__(self, message: str = "Version is deprecated"):
        super().__init__(status_code=400, detail=message)


class ServiceVersionSwitchError(HTTPException):
    """Exception raised for version switch failures."""
    
    def __init__(self, message: str = "Service version switch failed"):
        super().__init__(status_code=400, detail=message)
