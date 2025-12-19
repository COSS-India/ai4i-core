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
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Set log level
    if level is None:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, log_level_str, logging.INFO)
    
    logger.setLevel(level)
    
    # Get service name
    service_name = service_name or os.getenv("SERVICE_NAME", name)
    
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

