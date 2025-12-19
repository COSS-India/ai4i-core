"""
Test script for correlation middleware.

Run this to verify the middleware works correctly.
"""

from fastapi import FastAPI, Request
try:
    from fastapi.testclient import TestClient
except ImportError:
    # Fallback for older FastAPI versions
    from starlette.testclient import TestClient

from ai4icore_logging import (
    get_logger,
    CorrelationMiddleware,
    get_correlation_id,
)

# Create test app
app = FastAPI()

# Add correlation middleware
app.add_middleware(CorrelationMiddleware)

# Get logger
logger = get_logger("test-service")


@app.get("/test")
async def test_endpoint(request: Request):
    """Test endpoint that logs a message."""
    # Get correlation ID from request
    correlation_id = get_correlation_id(request)
    
    # Log a message (should automatically include trace_id)
    logger.info("Processing test request", extra={"endpoint": "/test"})
    
    return {
        "correlation_id": correlation_id,
        "message": "Test successful"
    }


if __name__ == "__main__":
    # Test with TestClient
    client = TestClient(app)
    
    # Test 1: Request with correlation ID
    print("Test 1: Request WITH correlation ID")
    response = client.get("/test", headers={"X-Correlation-ID": "test-123"})
    print(f"Response: {response.json()}")
    print(f"Response header X-Correlation-ID: {response.headers.get('X-Correlation-ID')}")
    print()
    
    # Test 2: Request without correlation ID (should generate one)
    print("Test 2: Request WITHOUT correlation ID (should generate one)")
    response = client.get("/test")
    print(f"Response: {response.json()}")
    print(f"Response header X-Correlation-ID: {response.headers.get('X-Correlation-ID')}")
    print()
    
    print("✅ Middleware test completed!")

