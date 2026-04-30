"""
Custom exceptions and error handlers for the profiler service.

This module provides comprehensive error handling with:
- Structured error types with HTTP status codes
- Detailed error context and metadata
- Retry logic and circuit breaker support
- Graceful degradation helpers
"""

import functools
import logging
import time
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from enum import Enum

logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels for monitoring and alerting."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProfilerError(Exception):
    """Base exception for profiler errors with enhanced context."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 500,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
    ):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
        self.severity = severity
        self.recoverable = recoverable
        self.timestamp = time.time()
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "status": self.status,
                "details": self.details,
                "severity": self.severity.value,
                "recoverable": self.recoverable,
                "timestamp": self.timestamp,
            }
        }


class ValidationError(ProfilerError):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status=400,
            details=details,
            severity=ErrorSeverity.LOW,
            recoverable=True,
        )


class ModelError(ProfilerError):
    """Raised when model prediction fails."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        super().__init__(
            code="MODEL_ERROR",
            message=message,
            status=500,
            details=details,
            severity=ErrorSeverity.HIGH,
            recoverable=recoverable,
        )


class ModelNotLoadedError(ProfilerError):
    """Raised when models are not yet loaded."""

    def __init__(self, message: str = "Service is starting up. Models not yet loaded."):
        super().__init__(
            code="MODEL_NOT_LOADED",
            message=message,
            status=503,
            severity=ErrorSeverity.CRITICAL,
            recoverable=True,
        )


class RateLimitError(ProfilerError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int):
        super().__init__(
            code="RATE_LIMITED",
            message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            status=429,
            details={"retry_after": retry_after},
            severity=ErrorSeverity.LOW,
            recoverable=True,
        )


class TimeoutError(ProfilerError):
    """Raised when request processing times out."""

    def __init__(self, timeout: int = 30):
        super().__init__(
            code="TIMEOUT",
            message=f"Request timed out after {timeout} seconds.",
            status=408,
            details={"timeout": timeout},
            severity=ErrorSeverity.MEDIUM,
            recoverable=True,
        )


class BatchSizeExceededError(ProfilerError):
    """Raised when batch size exceeds maximum."""

    def __init__(self, size: int, max_size: int):
        super().__init__(
            code="BATCH_SIZE_EXCEEDED",
            message=f"Batch size {size} exceeds maximum of {max_size}.",
            status=400,
            details={"size": size, "max_size": max_size},
            severity=ErrorSeverity.LOW,
            recoverable=True,
        )


class DataQualityError(ProfilerError):
    """Raised when input data quality is insufficient."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="DATA_QUALITY_ERROR",
            message=message,
            status=400,
            details=details,
            severity=ErrorSeverity.LOW,
            recoverable=True,
        )


class ServiceUnavailableError(ProfilerError):
    """Raised when a required service is unavailable."""

    def __init__(self, service: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=f"Required service '{service}' is unavailable.",
            status=503,
            details=details or {"service": service},
            severity=ErrorSeverity.HIGH,
            recoverable=True,
        )


# ── Retry Logic and Circuit Breaker ──────────────────────────────────────


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for fault tolerance.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail immediately
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise ServiceUnavailableError(
                    service=func.__name__,
                    details={"circuit_breaker_state": "OPEN"}
                )

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("Circuit breaker recovered, entering CLOSED state")
            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"Circuit breaker opened after {self.failure_count} failures")

            raise


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry

    Example:
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def unstable_function():
            # Function that might fail
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}: {e}"
                        )

            # If we get here, all retries failed
            raise last_exception

        return wrapper
    return decorator


def safe_execute(
    func: Callable[..., T],
    *args,
    default: Optional[T] = None,
    log_errors: bool = True,
    **kwargs
) -> Union[T, None]:
    """
    Safely execute a function with error handling and optional default value.

    Args:
        func: Function to execute
        *args: Positional arguments for the function
        default: Default value to return on error
        log_errors: Whether to log errors
        **kwargs: Keyword arguments for the function

    Returns:
        Function result or default value on error

    Example:
        result = safe_execute(risky_function, arg1, arg2, default=0)
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
        return default


def validate_input(
    text: str,
    min_length: int = 1,
    max_length: int = 100000,
    allow_empty: bool = False
) -> None:
    """
    Validate input text with comprehensive checks.

    Args:
        text: Input text to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        allow_empty: Whether to allow empty strings

    Raises:
        ValidationError: If validation fails
    """
    if text is None:
        raise ValidationError(
            "Input text cannot be None",
            details={"field": "text", "value": None}
        )

    if not isinstance(text, str):
        raise ValidationError(
            f"Input must be a string, got {type(text).__name__}",
            details={"field": "text", "type": type(text).__name__}
        )

    if not allow_empty and not text.strip():
        raise ValidationError(
            "Input text cannot be empty or whitespace only",
            details={"field": "text", "length": len(text)}
        )

    if len(text) < min_length:
        raise ValidationError(
            f"Input text too short (minimum {min_length} characters)",
            details={"field": "text", "length": len(text), "min_length": min_length}
        )

    if len(text) > max_length:
        raise ValidationError(
            f"Input text too long (maximum {max_length} characters)",
            details={"field": "text", "length": len(text), "max_length": max_length}
        )


def handle_model_error(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to handle model prediction errors gracefully.

    Converts various model-related exceptions into ProfilerError types.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except ModelNotLoadedError:
            # Re-raise as-is
            raise
        except (ValueError, TypeError) as e:
            # Input validation errors
            raise ValidationError(
                f"Invalid input for model: {e}",
                details={"original_error": str(e)}
            )
        except MemoryError as e:
            # Out of memory
            raise ModelError(
                "Insufficient memory for model prediction",
                details={"original_error": str(e)},
                recoverable=False
            )
        except Exception as e:
            # Generic model errors
            raise ModelError(
                f"Model prediction failed: {e}",
                details={"original_error": str(e), "error_type": type(e).__name__}
            )

    return wrapper

