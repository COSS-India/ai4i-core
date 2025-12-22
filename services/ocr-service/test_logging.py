"""
Test script to verify structured logging integration in OCR service.

Run this to test the logging before starting the full service.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai4icore_logging import (
    get_logger,
    set_trace_id,
    CorrelationMiddleware,
    configure_logging,
)

def test_basic_logging():
    """Test basic structured logging."""
    print("=" * 60)
    print("Test 1: Basic Structured Logging")
    print("=" * 60)
    
    # Configure logging (disable Kafka for local testing)
    configure_logging(service_name="ocr-service-test", use_kafka=False)
    
    # Get logger
    logger = get_logger("ocr-service")
    
    # Test different log levels
    logger.debug("This is a debug message")
    logger.info("This is an info message", extra={"test": "value"})
    logger.warning("This is a warning message")
    logger.error("This is an error message", extra={"error_code": "TEST_ERROR"})
    
    print("✅ Basic logging test completed!\n")


def test_trace_id():
    """Test trace ID injection."""
    print("=" * 60)
    print("Test 2: Trace ID Injection")
    print("=" * 60)
    
    configure_logging(service_name="ocr-service-test", use_kafka=False)
    logger = get_logger("ocr-service")
    
    # Set trace ID
    set_trace_id("test-correlation-123")
    logger.info("This log should have trace_id=test-correlation-123")
    
    # Generate new trace ID
    from ai4icore_logging import generate_trace_id
    new_trace_id = generate_trace_id()
    set_trace_id(new_trace_id)
    logger.info(f"This log should have trace_id={new_trace_id}")
    
    print("✅ Trace ID test completed!\n")


def test_context():
    """Test context extraction."""
    print("=" * 60)
    print("Test 3: Context Extraction")
    print("=" * 60)
    
    configure_logging(service_name="ocr-service-test", use_kafka=False)
    logger = get_logger("ocr-service")
    
    # Simulate request context
    set_trace_id("req-123")
    logger.info(
        "Processing OCR request",
        extra={
            "context": {
                "method": "POST",
                "path": "/api/v1/ocr/inference",
                "user_id": "user_456",
                "api_key_id": "key_789",
            }
        }
    )
    
    print("✅ Context test completed!\n")


if __name__ == "__main__":
    print("\n🧪 Testing OCR Service Logging Integration\n")
    
    try:
        test_basic_logging()
        test_trace_id()
        test_context()
        
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start OCR service: docker-compose up ocr-service")
        print("2. Send test request: curl http://localhost:8099/health")
        print("3. Check logs for JSON format with trace_id")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

