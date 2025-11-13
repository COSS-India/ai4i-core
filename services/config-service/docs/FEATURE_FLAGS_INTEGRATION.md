# Feature Flags Integration Guide

**Complete guide for integrating feature flags into any microservice**

This guide provides everything you need to integrate feature flags from the config service into your microservice. It includes a ready-to-use HTTP client, initialization patterns, usage examples, and best practices.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Setup](#setup)
- [Client Implementation](#client-implementation)
- [Usage Examples](#usage-examples)
- [FastAPI Integration](#fastapi-integration)
- [Error Handling](#error-handling)
- [Performance Optimization](#performance-optimization)
- [Testing](#testing)
- [Best Practices](#best-practices)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

## Overview

The feature flag system allows you to:
- **Gradually roll out** new features to specific users or percentages
- **A/B test** different implementations
- **Enable/disable features** without code deployments
- **Target features** based on user attributes, regions, or custom context
- **Emergency kill switches** to quickly disable features

### Architecture

```
┌─────────────────┐
│ Your Microservice│
│  (ASR, NMT, etc) │
└────────┬─────────┘
         │ HTTP Request
         ▼
┌─────────────────┐
│ Config Service  │
│ Feature Flag    │
│     API         │
└────────┬────────┘
         │
         ├─► Redis Cache (fast path)
         │
         └─► Unleash Server (source of truth)
```

## Quick Start

1. **Copy the client** (see [Client Implementation](#client-implementation))
2. **Add environment variables** (see [Setup](#setup))
3. **Initialize in your service** (see [FastAPI Integration](#fastapi-integration))
4. **Use in your code** (see [Usage Examples](#usage-examples))

## Setup

### 1. Environment Variables

Add these to your service's environment configuration (`env.template` and `.env`):

```bash
# Config service URL (default: http://config-service:8082)
CONFIG_SERVICE_URL=http://config-service:8082

# Environment name (must match Unleash environment)
ENVIRONMENT=development  # or staging, production

# Optional: Timeout for feature flag requests (default: 5.0 seconds)
FEATURE_FLAG_TIMEOUT=5.0
```

### 2. Install Dependencies

The feature flag client uses `httpx` which should already be in your `requirements.txt`:

```txt
httpx>=0.25.0
```

If not present, add it:

```bash
pip install httpx>=0.25.0
```

### 3. Create Client Utility

Create `utils/feature_flag_client.py` in your microservice directory (see [Client Implementation](#client-implementation) for complete code).

## Client Implementation

Create `utils/feature_flag_client.py` in your microservice:

```python
"""
Feature Flag HTTP Client for microservices

This client provides a simple interface to evaluate feature flags via the config service API.
"""
import os
import logging
from typing import Optional, Dict, Any, List, Union
import httpx

logger = logging.getLogger(__name__)


class FeatureFlagClient:
    """
    HTTP API client for feature flag evaluation
    
    Example usage:
        client = FeatureFlagClient()
        enabled = await client.is_enabled("new-ui-enabled", user_id="user-123")
    """
    
    def __init__(
        self,
        config_service_url: Optional[str] = None,
        timeout: float = 5.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize the feature flag client
        
        Args:
            config_service_url: Base URL of config service (defaults to CONFIG_SERVICE_URL env var)
            timeout: Request timeout in seconds (default: 5.0)
            http_client: Optional shared httpx.AsyncClient instance for connection pooling
        """
        self.base_url = (config_service_url or os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082")).rstrip("/")
        self.api_base = f"{self.base_url}/api/v1/feature-flags"
        self.timeout = timeout
        self._http_client = http_client
        self._own_client = None
    
    @property
    async def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client instance"""
        if self._http_client:
            return self._http_client
        if self._own_client is None:
            self._own_client = httpx.AsyncClient(timeout=self.timeout)
        return self._own_client
    
    async def close(self):
        """Close the HTTP client if we own it"""
        if self._own_client:
            await self._own_client.aclose()
            self._own_client = None
    
    async def is_enabled(
        self,
        flag_name: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        default_value: bool = False,
        environment: Optional[str] = None,
    ) -> bool:
        """
        Evaluate a boolean feature flag
        
        Args:
            flag_name: Name of the feature flag
            user_id: User identifier for targeting
            context: Additional context attributes (e.g., {"region": "us-west", "plan": "premium"})
            default_value: Fallback value if evaluation fails (default: False)
            environment: Environment name (defaults to ENVIRONMENT env var)
        
        Returns:
            Boolean indicating if flag is enabled
        """
        env = environment or os.getenv("ENVIRONMENT", "development")
        
        try:
            client = await self.client
            response = await client.post(
                f"{self.api_base}/evaluate/boolean",
                json={
                    "flag_name": flag_name,
                    "user_id": user_id,
                    "context": context or {},
                    "default_value": default_value,
                    "environment": env,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("value", default_value)
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Feature flag evaluation failed for '{flag_name}': {e.response.status_code} - {e.response.text}. "
                f"Using default value: {default_value}"
            )
            return default_value
        except httpx.RequestError as e:
            logger.warning(
                f"Feature flag request failed for '{flag_name}': {e}. "
                f"Using default value: {default_value}"
            )
            return default_value
        except Exception as e:
            logger.error(f"Unexpected error evaluating flag '{flag_name}': {e}", exc_info=True)
            return default_value
    
    async def evaluate(
        self,
        flag_name: str,
        default_value: Union[bool, str, int, float, dict],
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a feature flag with detailed response
        
        Supports boolean, string, integer, float, and object (dict) flag types.
        
        Args:
            flag_name: Name of the feature flag
            default_value: Fallback value (also determines flag type)
            user_id: User identifier for targeting
            context: Additional context attributes
            environment: Environment name (defaults to ENVIRONMENT env var)
        
        Returns:
            Dictionary with keys: flag_name, value, variant, reason, evaluated_at
        """
        env = environment or os.getenv("ENVIRONMENT", "development")
        
        try:
            client = await self.client
            response = await client.post(
                f"{self.api_base}/evaluate",
                json={
                    "flag_name": flag_name,
                    "user_id": user_id,
                    "context": context or {},
                    "default_value": default_value,
                    "environment": env,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Feature flag evaluation failed for '{flag_name}': {e.response.status_code}. "
                f"Using default value: {default_value}"
            )
            return {
                "flag_name": flag_name,
                "value": default_value,
                "variant": None,
                "reason": "ERROR",
                "evaluated_at": None,
            }
        except httpx.RequestError as e:
            logger.warning(
                f"Feature flag request failed for '{flag_name}': {e}. "
                f"Using default value: {default_value}"
            )
            return {
                "flag_name": flag_name,
                "value": default_value,
                "variant": None,
                "reason": "ERROR",
                "evaluated_at": None,
            }
        except Exception as e:
            logger.error(f"Unexpected error evaluating flag '{flag_name}': {e}", exc_info=True)
            return {
                "flag_name": flag_name,
                "value": default_value,
                "variant": None,
                "reason": "ERROR",
                "evaluated_at": None,
            }
    
    async def bulk_evaluate(
        self,
        flag_names: List[str],
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Evaluate multiple flags at once (more efficient than individual calls)
        
        Args:
            flag_names: List of flag names to evaluate
            user_id: User identifier for targeting
            context: Additional context attributes
            environment: Environment name (defaults to ENVIRONMENT env var)
        
        Returns:
            Dictionary mapping flag names to evaluation results
        """
        env = environment or os.getenv("ENVIRONMENT", "development")
        
        try:
            client = await self.client
            response = await client.post(
                f"{self.api_base}/evaluate/bulk",
                json={
                    "flag_names": flag_names,
                    "user_id": user_id,
                    "context": context or {},
                    "environment": env,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("results", {})
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Bulk feature flag evaluation failed: {e.response.status_code}. "
                f"Returning empty results."
            )
            return {}
        except httpx.RequestError as e:
            logger.warning(f"Bulk feature flag request failed: {e}. Returning empty results.")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error in bulk evaluation: {e}", exc_info=True)
            return {}
    
    async def get_flag(
        self,
        flag_name: str,
        environment: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get feature flag metadata by name
        
        Args:
            flag_name: Name of the feature flag
            environment: Environment name (defaults to ENVIRONMENT env var)
        
        Returns:
            Flag metadata dictionary or None if not found
        """
        env = environment or os.getenv("ENVIRONMENT", "development")
        
        try:
            client = await self.client
            response = await client.get(
                f"{self.api_base}/{flag_name}",
                params={"environment": env},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Feature flag '{flag_name}' not found")
                return None
            logger.warning(f"Failed to get flag '{flag_name}': {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Request failed for flag '{flag_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting flag '{flag_name}': {e}", exc_info=True)
            return None
    
    async def list_flags(
        self,
        environment: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List feature flags with pagination
        
        Args:
            environment: Environment name (defaults to ENVIRONMENT env var)
            limit: Maximum number of flags to return (default: 50)
            offset: Pagination offset (default: 0)
        
        Returns:
            Dictionary with keys: items, total, limit, offset
        """
        env = environment or os.getenv("ENVIRONMENT", "development")
        
        try:
            client = await self.client
            response = await client.get(
                f"{self.api_base}/",
                params={
                    "environment": env,
                    "limit": limit,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"Failed to list flags: {e.response.status_code}")
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        except httpx.RequestError as e:
            logger.warning(f"Request failed to list flags: {e}")
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        except Exception as e:
            logger.error(f"Unexpected error listing flags: {e}", exc_info=True)
            return {"items": [], "total": 0, "limit": limit, "offset": offset}


# Global client instance (optional - for convenience)
_global_client: Optional[FeatureFlagClient] = None


def get_feature_flag_client() -> FeatureFlagClient:
    """
    Get or create global feature flag client instance
    
    Note: In production, prefer dependency injection over global instance.
    See FastAPI Integration section for better patterns.
    """
    global _global_client
    if _global_client is None:
        _global_client = FeatureFlagClient()
    return _global_client
```

## Usage Examples

### Basic Boolean Check

The simplest use case - check if a feature is enabled:

```python
from utils.feature_flag_client import FeatureFlagClient

async def my_endpoint(user_id: str):
    client = FeatureFlagClient()
    
    # Check if feature is enabled
    is_enabled = await client.is_enabled(
        flag_name="new-feature",
        user_id=user_id,
        default_value=False,  # Fallback if check fails
    )
    
    if is_enabled:
        # Use new feature
        return new_implementation()
    else:
        # Use old implementation
        return old_implementation()
```

### With Context Attributes

Pass additional context for advanced targeting:

```python
async def process_request(user_id: str, region: str, plan: str):
    client = FeatureFlagClient()
    
    is_enabled = await client.is_enabled(
        flag_name="premium-features",
        user_id=user_id,
        context={
            "region": region,
            "plan": plan,
            "subscription_active": True,
        },
        default_value=False,
    )
    
    if is_enabled:
        # Enable premium features
        pass
```

### Bulk Evaluation

Evaluate multiple flags at once (more efficient):

```python
async def process_request(user_id: str):
    client = FeatureFlagClient()
    
    # Evaluate multiple flags in one request
    flags = await client.bulk_evaluate(
        flag_names=[
            "new-model",
            "enhanced-processing",
            "enable-caching",
        ],
        user_id=user_id,
        context={"service_id": "asr-service"},
    )
    
    # Use results
    if flags.get("new-model", {}).get("value", False):
        use_new_model()
    
    if flags.get("enhanced-processing", {}).get("value", False):
        apply_enhanced_processing()
```

### Detailed Evaluation

Get full evaluation details (value, variant, reason):

```python
async def get_feature_details(flag_name: str, user_id: str):
    client = FeatureFlagClient()
    
    result = await client.evaluate(
        flag_name=flag_name,
        default_value="default-variant",
        user_id=user_id,
        context={"region": "us-west"},
    )
    
    # result contains:
    # {
    #     "flag_name": "theme-color",
    #     "value": "red",
    #     "variant": "red",
    #     "reason": "TARGETING_MATCH",
    #     "evaluated_at": "2024-01-15T10:30:00Z"
    # }
    
    if result["reason"] == "TARGETING_MATCH":
        # Flag matched targeting rules
        return result["value"]
    else:
        # Using default value
        return result["value"]
```

### String/Integer/Float Flags

Evaluate non-boolean flags:

```python
async def get_theme_color(user_id: str):
    client = FeatureFlagClient()
    
    # String flag
    result = await client.evaluate(
        flag_name="theme-color",
        default_value="blue",  # String default = string flag
        user_id=user_id,
    )
    theme_color = result["value"]  # "red", "blue", etc.

async def get_max_retries():
    client = FeatureFlagClient()
    
    # Integer flag
    result = await client.evaluate(
        flag_name="max-retries",
        default_value=3,  # Integer default = integer flag
    )
    max_retries = result["value"]  # 3, 5, etc.

async def get_timeout():
    client = FeatureFlagClient()
    
    # Float flag
    result = await client.evaluate(
        flag_name="request-timeout",
        default_value=5.0,  # Float default = float flag
    )
    timeout = result["value"]  # 5.0, 10.0, etc.
```

## FastAPI Integration

### Dependency Injection Pattern (Recommended)

This pattern provides better testability and resource management:

```python
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
import httpx
from utils.feature_flag_client import FeatureFlagClient

# Shared HTTP client for connection pooling
http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global http_client
    
    # Startup: Create shared HTTP client
    http_client = httpx.AsyncClient(timeout=5.0)
    
    yield
    
    # Shutdown: Close HTTP client
    if http_client:
        await http_client.aclose()

app = FastAPI(lifespan=lifespan)

def get_feature_flag_client() -> FeatureFlagClient:
    """Dependency for feature flag client"""
    return FeatureFlagClient(http_client=http_client)

@app.get("/my-endpoint")
async def my_endpoint(
    user_id: str,
    client: FeatureFlagClient = Depends(get_feature_flag_client),
):
    is_enabled = await client.is_enabled(
        flag_name="new-feature",
        user_id=user_id,
    )
    return {"feature_enabled": is_enabled}
```

### App State Pattern

Alternative pattern using FastAPI app state:

```python
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from utils.feature_flag_client import FeatureFlagClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup: Initialize feature flag client
    app.state.feature_flag_client = FeatureFlagClient()
    
    yield
    
    # Shutdown: Close client
    if hasattr(app.state, "feature_flag_client"):
        await app.state.feature_flag_client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/my-endpoint")
async def my_endpoint(user_id: str, request: Request):
    client: FeatureFlagClient = request.app.state.feature_flag_client
    
    is_enabled = await client.is_enabled(
        flag_name="new-feature",
        user_id=user_id,
    )
    return {"feature_enabled": is_enabled}
```

## Error Handling

The feature flag client handles errors gracefully:

- **Network errors**: Returns `default_value` and logs warning
- **Invalid flags**: Returns `default_value` and logs warning
- **Service unavailable**: Returns `default_value` and logs warning
- **HTTP errors**: Returns `default_value` and logs warning

**Always provide a sensible `default_value`:**

```python
# Good: Safe default (feature disabled by default)
is_enabled = await client.is_enabled(
    flag_name="new-feature",
    default_value=False,  # Safe: feature disabled by default
)

# Bad: Risky default
is_enabled = await client.is_enabled(
    flag_name="critical-feature",
    default_value=True,  # Risky: enabled by default if check fails
)
```

## Performance Optimization

### 1. Use Connection Pooling

Share an HTTP client instance across requests:

```python
# Good: Shared client
http_client = httpx.AsyncClient(timeout=5.0)
client = FeatureFlagClient(http_client=http_client)

# Bad: New client per request
client = FeatureFlagClient()  # Creates new connection each time
```

### 2. Use Bulk Evaluation

If you need multiple flags, use bulk evaluation:

```python
# Good: Single request
flags = await client.bulk_evaluate(
    flag_names=["flag1", "flag2", "flag3"],
    user_id=user_id,
)

# Bad: Multiple requests
flag1 = await client.is_enabled("flag1", user_id=user_id)
flag2 = await client.is_enabled("flag2", user_id=user_id)
flag3 = await client.is_enabled("flag3", user_id=user_id)
```

### 3. Cache Results (Optional)

For flags that don't change per request, cache results:

```python
from functools import lru_cache
import asyncio

# Cache flag values for 60 seconds
@lru_cache(maxsize=128)
def _cached_flag_check(flag_name: str, user_id: str, timestamp: int):
    # This is a synchronous cache - use async cache in production
    pass

async def get_cached_flag(flag_name: str, user_id: str):
    client = FeatureFlagClient()
    # Round timestamp to nearest minute for 60s cache
    cache_key = int(time.time() / 60)
    return await client.is_enabled(flag_name, user_id=user_id)
```

## Testing

### Mocking the Client

In unit tests, mock the feature flag client:

```python
import pytest
from unittest.mock import AsyncMock, patch
from utils.feature_flag_client import FeatureFlagClient

@pytest.mark.asyncio
async def test_with_feature_enabled():
    with patch('utils.feature_flag_client.FeatureFlagClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_enabled = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client
        
        # Your code that uses feature flag
        result = await my_function()
        
        # Assert behavior when flag is enabled
        assert result == expected_when_enabled

@pytest.mark.asyncio
async def test_with_feature_disabled():
    with patch('utils.feature_flag_client.FeatureFlagClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_enabled = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client
        
        # Your code that uses feature flag
        result = await my_function()
        
        # Assert behavior when flag is disabled
        assert result == expected_when_disabled
```

### Integration Testing

For integration tests, use a real client pointing to a test config service:

```python
@pytest.mark.asyncio
async def test_integration():
    client = FeatureFlagClient(
        config_service_url="http://test-config-service:8082",
        timeout=2.0,
    )
    
    # Test with real service
    result = await client.is_enabled(
        flag_name="test-flag",
        user_id="test-user",
        default_value=False,
    )
    
    assert isinstance(result, bool)
```

## Best Practices

### 1. Use Consistent User IDs

For gradual rollouts, use consistent user IDs to ensure sticky behavior:

```python
# Good: Consistent user ID
user_id = request.user_id  # From authentication

# Bad: Random or inconsistent
user_id = str(random.randint(1, 1000))  # Different each time
```

### 2. Provide Safe Defaults

Always provide safe default values:

```python
# Good: Safe default (feature disabled)
is_enabled = await client.is_enabled(
    flag_name="experimental-feature",
    default_value=False,  # Safe: disabled by default
)

# Bad: Risky default
is_enabled = await client.is_enabled(
    flag_name="experimental-feature",
    default_value=True,  # Risky: enabled if check fails
)
```

### 3. Include Relevant Context

Pass context that might be used for targeting:

```python
# Good: Rich context
is_enabled = await client.is_enabled(
    flag_name="region-feature",
    user_id=user_id,
    context={
        "region": region,
        "plan": plan,
        "language": language,
    },
)

# Bad: No context
is_enabled = await client.is_enabled(
    flag_name="region-feature",
    user_id=user_id,
    # Missing context that might be needed for targeting
)
```

### 4. Log Feature Flag Usage

Log when feature flags affect behavior:

```python
import logging

logger = logging.getLogger(__name__)

is_enabled = await client.is_enabled(
    flag_name="new-feature",
    user_id=user_id,
)

if is_enabled:
    logger.info(f"Feature 'new-feature' enabled for user {user_id}")
    # Use new feature
else:
    logger.debug(f"Feature 'new-feature' disabled for user {user_id}")
    # Use old feature
```

### 5. Use Dependency Injection

Prefer dependency injection over global instances:

```python
# Good: Dependency injection
@app.get("/endpoint")
async def endpoint(client: FeatureFlagClient = Depends(get_feature_flag_client)):
    pass

# Bad: Global instance
client = FeatureFlagClient()  # Hard to test and manage
```

## Real-World Examples

### Example 1: Gradual Model Rollout

Gradually roll out a new ASR model to a percentage of users:

```python
async def run_inference(request, user_id: str):
    client = FeatureFlagClient()
    
    # Check if user should get new model (e.g., 25% rollout)
    use_new_model = await client.is_enabled(
        flag_name="new-asr-model-v2",
        user_id=user_id,  # Consistent user_id ensures sticky behavior
        default_value=False,
    )
    
    if use_new_model:
        # Use new model
        return await asr_service.run_with_new_model(request)
    else:
        # Use old model
        return await asr_service.run_with_old_model(request)
```

### Example 2: Region-Based Features

Enable features for specific regions:

```python
async def process_request(user_id: str, region: str):
    client = FeatureFlagClient()
    
    # Enable feature only for US West region
    is_enabled = await client.is_enabled(
        flag_name="region-specific-feature",
        user_id=user_id,
        context={"region": region},
        default_value=False,
    )
    
    if is_enabled:
        # Apply region-specific logic
        pass
```

### Example 3: A/B Testing

Test different implementations:

```python
async def process_request(user_id: str):
    client = FeatureFlagClient()
    
    # Get variant (e.g., "variant-a" or "variant-b")
    result = await client.evaluate(
        flag_name="ab-test-algorithm",
        default_value="control",
        user_id=user_id,
    )
    
    variant = result.get("variant", "control")
    
    if variant == "variant-a":
        return algorithm_a()
    elif variant == "variant-b":
        return algorithm_b()
    else:
        return control_algorithm()
```

### Example 4: Feature Gating

Gate features based on user attributes:

```python
async def premium_endpoint(user_id: str, user_plan: str):
    client = FeatureFlagClient()
    
    # Check if premium features are enabled for this user
    has_access = await client.is_enabled(
        flag_name="premium-features",
        user_id=user_id,
        context={"plan": user_plan},
        default_value=False,
    )
    
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="Premium features not available"
        )
    
    # Proceed with premium features
    return premium_functionality()
```

### Example 5: Dynamic Configuration

Use flags for runtime configuration:

```python
async def get_processing_config():
    client = FeatureFlagClient()
    
    # Get max retries from feature flag
    result = await client.evaluate(
        flag_name="max-retries",
        default_value=3,
    )
    max_retries = result["value"]
    
    # Get timeout from feature flag
    result = await client.evaluate(
        flag_name="request-timeout",
        default_value=5.0,
    )
    timeout = result["value"]
    
    return {
        "max_retries": max_retries,
        "timeout": timeout,
    }
```

## API Reference

### `FeatureFlagClient.is_enabled()`

Check if a boolean feature flag is enabled.

```python
is_enabled(
    flag_name: str,
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    default_value: bool = False,
    environment: Optional[str] = None,
) -> bool
```

**Returns**: Boolean indicating if flag is enabled

### `FeatureFlagClient.evaluate()`

Evaluate a feature flag with detailed response.

```python
evaluate(
    flag_name: str,
    default_value: Union[bool, str, int, float, dict],
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]
```

**Returns**: Dictionary with keys: `flag_name`, `value`, `variant`, `reason`, `evaluated_at`

### `FeatureFlagClient.bulk_evaluate()`

Evaluate multiple flags at once.

```python
bulk_evaluate(
    flag_names: List[str],
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    environment: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]
```

**Returns**: Dictionary mapping flag names to evaluation results

### `FeatureFlagClient.get_flag()`

Get feature flag metadata by name.

```python
get_flag(
    flag_name: str,
    environment: Optional[str] = None,
) -> Optional[Dict[str, Any]]
```

**Returns**: Flag metadata dictionary or None if not found

### `FeatureFlagClient.list_flags()`

List feature flags with pagination.

```python
list_flags(
    environment: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]
```

**Returns**: Dictionary with keys: `items`, `total`, `limit`, `offset`

## Creating Flags in Unleash

Before using a flag, create it in Unleash:

1. Navigate to Unleash UI: http://localhost:4242
2. Click **"Create feature toggle"**
3. Enter flag name (e.g., `new-asr-model-v2`)
4. Configure environment settings:
   - Enable/disable for each environment
   - Add strategies (gradual rollout, user targeting, etc.)
5. Save the flag

### Example Flag Configurations

**Gradual Rollout (25% of users)**:
- Strategy: `flexibleRollout`
- Rollout: 25%
- Stickiness: `userId`

**User Targeting**:
- Strategy: `userWithId`
- User IDs: `user-123, user-456`

**Context-Based**:
- Strategy: `default`
- Constraints: `region == "us-west"`

## Troubleshooting

### Flags Not Working

1. **Check flag exists in Unleash**: Verify flag name matches exactly
2. **Check environment**: Ensure `ENVIRONMENT` matches Unleash environment
3. **Check config service**: Verify config service is running and accessible
4. **Check logs**: Look for warnings about feature flag evaluation

### Getting Default Values

If you're always getting default values:

1. **Flag might be disabled**: Check flag state in Unleash UI
2. **Targeting not matching**: Check if user/context matches targeting rules
3. **Environment mismatch**: Verify environment name matches

### Performance Issues

If feature flag checks are slow:

1. **Use bulk evaluation**: Check multiple flags at once
2. **Use connection pooling**: Share HTTP client instance
3. **Check config service**: Verify config service is responding quickly
4. **Check network**: Verify network latency to config service

### Connection Errors

If you see connection errors:

1. **Check CONFIG_SERVICE_URL**: Verify URL is correct
2. **Check network**: Ensure service can reach config service
3. **Check timeout**: Increase `FEATURE_FLAG_TIMEOUT` if needed
4. **Check DNS**: Verify service name resolution works

## Additional Resources

- [Feature Flags Architecture](./FEATURE_FLAGS_ARCHITECTURE.md) - System architecture details
- [Feature Flags API Documentation](./FEATURE_FLAGS.md) - Complete API reference
- [Feature Flags Evaluation Guide](./FEATURE_FLAGS_EVALUATION.md) - Evaluation details
- [Unleash Documentation](https://docs.getunleash.io/) - Unleash platform docs

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the architecture and API documentation
3. Check service logs for error messages
4. Contact the platform team
