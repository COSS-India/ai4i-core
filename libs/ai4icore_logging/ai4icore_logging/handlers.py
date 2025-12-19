"""
Log Handlers

Custom handlers for sending logs to Kafka and other destinations.
"""

import logging
import os
import sys
from typing import Optional

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


class KafkaHandler(logging.Handler):
    """
    Kafka handler for sending logs to Kafka topic.
    
    Falls back to stdout if Kafka is unavailable.
    """
    
    def __init__(
        self,
        topic: str = "logs",
        bootstrap_servers: Optional[str] = None,
        fallback_to_stdout: bool = True,
    ):
        """
        Initialize Kafka handler.
        
        Args:
            topic: Kafka topic to send logs to
            bootstrap_servers: Kafka bootstrap servers (defaults to env KAFKA_BOOTSTRAP_SERVERS)
            fallback_to_stdout: If True, fallback to stdout if Kafka unavailable
        """
        super().__init__()
        
        self.topic = topic
        self.fallback_to_stdout = fallback_to_stdout
        self.producer = None
        self.kafka_available = False
        
        # Get Kafka servers from env or parameter
        self.bootstrap_servers = (
            bootstrap_servers or 
            os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        )
        
        # Try to initialize Kafka producer
        if KAFKA_AVAILABLE:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers.split(","),
                    value_serializer=lambda v: v.encode('utf-8') if isinstance(v, str) else v,
                    acks='all',  # Wait for all replicas
                    retries=3,
                )
                self.kafka_available = True
            except Exception as e:
                if self.fallback_to_stdout:
                    print(f"⚠️ Kafka unavailable, falling back to stdout: {e}", file=sys.stderr)
                    self.kafka_available = False
                else:
                    raise
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to Kafka or stdout.
        
        Args:
            record: Log record to emit
        """
        try:
            # Format the log record
            log_message = self.format(record)
            
            # Try to send to Kafka
            if self.kafka_available and self.producer:
                try:
                    self.producer.send(self.topic, value=log_message)
                    # Flush immediately for important logs
                    if record.levelno >= logging.ERROR:
                        self.producer.flush()
                except Exception as e:
                    # If Kafka fails, fallback to stdout
                    if self.fallback_to_stdout:
                        print(log_message, file=sys.stdout)
                        print(f"⚠️ Kafka send failed, logged to stdout: {e}", file=sys.stderr)
                    else:
                        raise
            else:
                # Fallback to stdout
                if self.fallback_to_stdout:
                    print(log_message, file=sys.stdout)
        except Exception:
            # Handle any errors in emit
            self.handleError(record)
    
    def close(self) -> None:
        """
        Close the handler and flush Kafka producer.
        """
        if self.producer:
            try:
                self.producer.flush()
                self.producer.close()
            except Exception:
                pass
        super().close()

