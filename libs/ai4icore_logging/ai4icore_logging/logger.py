"""
Main Logger Module

Provides get_logger function and logging configuration.
"""

import logging
import os
import sys
from typing import Optional

from .formatters import JSONFormatter
from .handlers import KafkaHandler


def get_logger(
    name: str,
    service_name: Optional[str] = None,
    level: Optional[int] = None,
    use_kafka: bool = True,
    kafka_topic: str = "logs",
    fallback_to_stdout: bool = True,
) -> logging.Logger:
    """
    Get a configured logger instance with JSON formatting.
    
    Args:
        name: Logger name (usually __name__ or service name)
        service_name: Service name for logs (defaults to env SERVICE_NAME)
        level: Log level (defaults to env LOG_LEVEL or INFO)
        use_kafka: Whether to send logs to Kafka
        kafka_topic: Kafka topic name
        fallback_to_stdout: Fallback to stdout if Kafka unavailable
        
    Returns:
        Configured logger instance
        
    Example:
        logger = get_logger("my-service")
        logger.info("Processing request", extra={"user_id": "user_123"})
    """
    logger = logging.getLogger(name)
    
    # Get service name - check root logger's formatter first, then env var
    # This ensures all loggers use the same service_name as configured in configure_logging()
    root_logger = logging.getLogger()
    root_service_name = None
    if root_logger.handlers:
        for handler in root_logger.handlers:
            if hasattr(handler, 'formatter') and isinstance(handler.formatter, JSONFormatter):
                root_service_name = handler.formatter.service_name
                break
    
    # Priority: provided service_name > root logger's service_name > env var > "unknown"
    service_name = service_name or root_service_name or os.getenv("SERVICE_NAME", "unknown")
    
    # Avoid duplicate handlers
    if logger.handlers:
        # Update existing handlers' formatters to use correct service_name
        for handler in logger.handlers:
            if hasattr(handler, 'formatter') and isinstance(handler.formatter, JSONFormatter):
                handler.formatter.service_name = service_name
        return logger
    
    # Set log level
    if level is None:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, log_level_str, logging.INFO)
    
    logger.setLevel(level)
    
    # Create JSON formatter
    formatter = JSONFormatter(service_name=service_name)
    
    # Add handlers
    if use_kafka:
        # Kafka handler (with stdout fallback)
        kafka_handler = KafkaHandler(
            topic=kafka_topic,
            fallback_to_stdout=fallback_to_stdout,
        )
        kafka_handler.setFormatter(formatter)
        logger.addHandler(kafka_handler)
    else:
        # Stdout handler only
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def configure_logging(
    service_name: Optional[str] = None,
    level: Optional[int] = None,
    use_kafka: bool = True,
    kafka_topic: str = "logs",
    root_level: Optional[int] = None,
) -> None:
    """
    Configure root logging for the application.
    
    Args:
        service_name: Service name for logs
        level: Log level for service loggers
        use_kafka: Whether to use Kafka handler
        kafka_topic: Kafka topic name
        root_level: Log level for root logger (defaults to WARNING)
    """
    # Configure root logger
    if root_level is None:
        root_level = logging.WARNING
    
    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    service_name = service_name or os.getenv("SERVICE_NAME", "unknown")
    formatter = JSONFormatter(service_name=service_name)
    
    # Add stdout handler for root logger
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)
    
    # Update all existing loggers' formatters to use the correct service_name
    # This ensures loggers created before configure_logging() get the correct service_name
    for logger_name in logging.Logger.manager.loggerDict:
        logger_obj = logging.getLogger(logger_name)
        if logger_obj.handlers:
            for handler in logger_obj.handlers:
                if hasattr(handler, 'formatter'):
                    if isinstance(handler.formatter, JSONFormatter):
                        # Update existing JSONFormatter with correct service_name
                        handler.formatter.service_name = service_name
                    else:
                        # Replace non-JSON formatter with JSONFormatter
                        # This catches loggers created before configure_logging()
                        handler.setFormatter(JSONFormatter(service_name=service_name))
    
    # Also configure third-party library loggers (httpx, uvicorn, etc.) to use our formatter
    # This ensures all logs have trace_id and correct service_name
    third_party_loggers = ['httpx', 'httpcore', 'urllib3']
    for lib_name in third_party_loggers:
        lib_logger = logging.getLogger(lib_name)
        # Set level to WARNING to reduce noise from third-party libs
        lib_logger.setLevel(logging.WARNING)
        if lib_logger.handlers:
            for handler in lib_logger.handlers:
                if not isinstance(handler.formatter, JSONFormatter):
                    handler.setFormatter(JSONFormatter(service_name=service_name))
        else:
            # Add handler if logger exists but has no handlers
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(JSONFormatter(service_name=service_name))
            lib_logger.addHandler(stdout_handler)
        lib_logger.propagate = False
    
    # Disable uvicorn access logger completely (we use RequestLoggingMiddleware instead)
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    
    # Configure other uvicorn loggers to use our formatter
    for uvicorn_logger_name in ["uvicorn", "uvicorn.error", "uvicorn.asgi"]:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        if uvicorn_logger.handlers:
            for handler in uvicorn_logger.handlers:
                if not isinstance(handler.formatter, JSONFormatter):
                    handler.setFormatter(JSONFormatter(service_name=service_name))
        # Let them propagate to root logger which has our formatter
        uvicorn_logger.propagate = True

