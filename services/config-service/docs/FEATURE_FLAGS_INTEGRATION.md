# Feature Flags Integration Guide

## Overview

This guide explains how to integrate the Feature Flags system into your microservices. It covers client libraries, API usage, caching strategies, and best practices.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Integration Methods](#integration-methods)
3. [Client Libraries](#client-libraries)
4. [Direct API Integration](#direct-api-integration)
5. [Caching Strategies](#caching-strategies)
6. [Error Handling](#error-handling)
7. [Testing](#testing)
8. [Best Practices](#best-practices)
9. [Examples](#examples)

## Quick Start

### 1. Add Dependencies

**Python:**
```bash
pip install aiohttp httpx redis
```

**Node.js:**
```bash
npm install axios ioredis
```

**Go:**
```bash
go get github.com/go-redis/redis/v8
go get github.com/valyala/fasthttp
```

### 2. Basic Integration

**Python Example:**
```python
import aiohttp
import os

async def is_feature_enabled(flag_name: str, user_id: str, environment: str = None):
    """Check if a feature flag is enabled for a user"""
    env = environment or os.getenv("ENVIRONMENT", "development")
    config_service_url = os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{config_service_url}/api/v1/feature-flags/evaluate",
            json={
                "flag_name": flag_name,
                "user_id": user_id,
                "environment": env
            }
        ) as response:
            if response.status == 200:
                result = await response.json()
                return result.get("enabled", False)
    return False
```

## Integration Methods

### Method 1: Direct API Calls (Simple)

**Pros:**
- No additional dependencies
- Easy to implement
- Works with any language

**Cons:**
- Network latency on every check
- No local caching
- Higher load on config service

**Use When:**
- Low traffic services
- Simple use cases
- Prototyping

### Method 2: Client Library with Caching (Recommended)

**Pros:**
- Local caching reduces latency
- Lower load on config service
- Better performance

**Cons:**
- Requires cache infrastructure (Redis)
- More complex setup
- Cache invalidation needed

**Use When:**
- Production services
- High traffic applications
- Performance critical

### Method 3: Event-Driven Updates

**Pros:**
- Real-time updates
- No polling needed
- Efficient

**Cons:**
- Requires Kafka consumer
- More complex architecture
- Event ordering considerations

**Use When:**
- Real-time feature toggles needed
- Large-scale deployments
- Advanced use cases

## Client Libraries

### Python Client

Create `feature_flags_client.py`:

```python
import aiohttp
import asyncio
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import json
import os

class FeatureFlagsClient:
    def __init__(
        self,
        config_service_url: str,
        environment: str,
        cache_ttl: int = 300,
        redis_client=None
    ):
        self.config_service_url = config_service_url.rstrip('/')
        self.environment = environment
        self.cache_ttl = cache_ttl
        self.redis = redis_client
        self._session = None
    
    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    def _cache_key(self, flag_name: str, user_id: str) -> str:
        return f"ff_eval:{self.environment}:{flag_name}:{user_id}"
    
    async def is_enabled(
        self,
        flag_name: str,
        user_id: str,
        default: bool = False
    ) -> bool:
        """Check if a feature flag is enabled for a user"""
        # Check cache first
        if self.redis:
            cache_key = self._cache_key(flag_name, user_id)
            cached = await self.redis.get(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    return data.get("enabled", default)
                except:
                    pass
        
        # Fetch from API
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.config_service_url}/api/v1/feature-flags/evaluate",
                json={
                    "flag_name": flag_name,
                    "user_id": user_id,
                    "environment": self.environment
                },
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    enabled = result.get("enabled", default)
                    
                    # Cache result
                    if self.redis:
                        cache_key = self._cache_key(flag_name, user_id)
                        await self.redis.setex(
                            cache_key,
                            self.cache_ttl,
                            json.dumps({"enabled": enabled, "cached_at": datetime.now().isoformat()})
                        )
                    
                    return enabled
        except Exception as e:
            print(f"Error evaluating flag {flag_name}: {e}")
        
        return default
    
    async def batch_evaluate(
        self,
        flag_names: List[str],
        user_id: str,
        default: bool = False
    ) -> Dict[str, bool]:
        """Evaluate multiple flags at once"""
        results = {}
        
        # Check cache for each flag
        cache_keys = {}
        if self.redis:
            for flag_name in flag_names:
                cache_key = self._cache_key(flag_name, user_id)
                cached = await self.redis.get(cache_key)
                if cached:
                    try:
                        data = json.loads(cached)
                        results[flag_name] = data.get("enabled", default)
                    except:
                        pass
                else:
                    cache_keys[flag_name] = cache_key
        
        # Fetch uncached flags from API
        uncached_flags = [f for f in flag_names if f not in results]
        if uncached_flags:
            try:
                session = await self._get_session()
                async with session.post(
                    f"{self.config_service_url}/api/v1/feature-flags/evaluate/batch",
                    params={
                        "user_id": user_id,
                        "environment": self.environment
                    },
                    json=uncached_flags,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        batch_results = await response.json()
                        
                        # Cache results
                        if self.redis:
                            for flag_name, result in batch_results.items():
                                enabled = result.get("enabled", default)
                                results[flag_name] = enabled
                                
                                cache_key = self._cache_key(flag_name, user_id)
                                await self.redis.setex(
                                    cache_key,
                                    self.cache_ttl,
                                    json.dumps({"enabled": enabled, "cached_at": datetime.now().isoformat()})
                                )
            except Exception as e:
                print(f"Error batch evaluating flags: {e}")
                # Fill missing with default
                for flag_name in uncached_flags:
                    if flag_name not in results:
                        results[flag_name] = default
        
        return results
    
    async def close(self):
        """Close the HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
```

**Usage:**
```python
import redis.asyncio as redis
from feature_flags_client import FeatureFlagsClient

# Initialize
redis_client = redis.from_url("redis://localhost:6379")
ff_client = FeatureFlagsClient(
    config_service_url="http://config-service:8082",
    environment="development",
    cache_ttl=300,
    redis_client=redis_client
)

# Check a flag
enabled = await ff_client.is_enabled("new_ui", "user123")
if enabled:
    # Use new UI
    pass

# Batch check
results = await ff_client.batch_evaluate(
    ["new_ui", "dark_mode", "beta_features"],
    "user123"
)
```

### Node.js Client

Create `featureFlagsClient.js`:

```javascript
const axios = require('axios');
const Redis = require('ioredis');

class FeatureFlagsClient {
    constructor(config) {
        this.configServiceUrl = config.configServiceUrl || 'http://config-service:8082';
        this.environment = config.environment || 'development';
        this.cacheTtl = config.cacheTtl || 300;
        this.redis = config.redis ? new Redis(config.redis) : null;
        this.httpClient = axios.create({
            timeout: 5000,
            baseURL: this.configServiceUrl
        });
    }

    cacheKey(flagName, userId) {
        return `ff_eval:${this.environment}:${flagName}:${userId}`;
    }

    async isEnabled(flagName, userId, defaultValue = false) {
        // Check cache
        if (this.redis) {
            const cacheKey = this.cacheKey(flagName, userId);
            const cached = await this.redis.get(cacheKey);
            if (cached) {
                try {
                    const data = JSON.parse(cached);
                    return data.enabled;
                } catch (e) {
                    // Invalid cache, continue
                }
            }
        }

        // Fetch from API
        try {
            const response = await this.httpClient.post('/api/v1/feature-flags/evaluate', {
                flag_name: flagName,
                user_id: userId,
                environment: this.environment
            });

            if (response.status === 200 && response.data) {
                const enabled = response.data.enabled || defaultValue;

                // Cache result
                if (this.redis) {
                    const cacheKey = this.cacheKey(flagName, userId);
                    await this.redis.setex(
                        cacheKey,
                        this.cacheTtl,
                        JSON.stringify({ enabled, cached_at: new Date().toISOString() })
                    );
                }

                return enabled;
            }
        } catch (error) {
            console.error(`Error evaluating flag ${flagName}:`, error.message);
        }

        return defaultValue;
    }

    async batchEvaluate(flagNames, userId, defaultValue = false) {
        const results = {};
        const uncachedFlags = [];

        // Check cache
        if (this.redis) {
            for (const flagName of flagNames) {
                const cacheKey = this.cacheKey(flagName, userId);
                const cached = await this.redis.get(cacheKey);
                if (cached) {
                    try {
                        const data = JSON.parse(cached);
                        results[flagName] = data.enabled;
                    } catch (e) {
                        uncachedFlags.push(flagName);
                    }
                } else {
                    uncachedFlags.push(flagName);
                }
            }
        } else {
            uncachedFlags.push(...flagNames);
        }

        // Fetch uncached flags
        if (uncachedFlags.length > 0) {
            try {
                const response = await this.httpClient.post(
                    `/api/v1/feature-flags/evaluate/batch?user_id=${userId}&environment=${this.environment}`,
                    uncachedFlags
                );

                if (response.status === 200 && response.data) {
                    // Cache results
                    if (this.redis) {
                        for (const [flagName, result] of Object.entries(response.data)) {
                            const enabled = result.enabled || defaultValue;
                            results[flagName] = enabled;

                            const cacheKey = this.cacheKey(flagName, userId);
                            await this.redis.setex(
                                cacheKey,
                                this.cacheTtl,
                                JSON.stringify({ enabled, cached_at: new Date().toISOString() })
                            );
                        }
                    }
                }
            } catch (error) {
                console.error('Error batch evaluating flags:', error.message);
                // Fill missing with default
                for (const flagName of uncachedFlags) {
                    if (!(flagName in results)) {
                        results[flagName] = defaultValue;
                    }
                }
            }
        }

        return results;
    }

    async close() {
        if (this.redis) {
            await this.redis.quit();
        }
    }
}

module.exports = FeatureFlagsClient;
```

**Usage:**
```javascript
const FeatureFlagsClient = require('./featureFlagsClient');
const Redis = require('ioredis');

// Initialize
const redis = new Redis('redis://localhost:6379');
const ffClient = new FeatureFlagsClient({
    configServiceUrl: 'http://config-service:8082',
    environment: 'development',
    cacheTtl: 300,
    redis: redis
});

// Check a flag
const enabled = await ffClient.isEnabled('new_ui', 'user123');
if (enabled) {
    // Use new UI
}

// Batch check
const results = await ffClient.batchEvaluate(
    ['new_ui', 'dark_mode', 'beta_features'],
    'user123'
);
```

## Direct API Integration

### Simple HTTP Client

**Python:**
```python
import requests

def is_feature_enabled(flag_name, user_id, environment="development"):
    try:
        response = requests.post(
            "http://config-service:8082/api/v1/feature-flags/evaluate",
            json={
                "flag_name": flag_name,
                "user_id": user_id,
                "environment": environment
            },
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get("enabled", False)
    except Exception as e:
        print(f"Error: {e}")
    return False
```

**cURL:**
```bash
curl -X POST http://config-service:8082/api/v1/feature-flags/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "flag_name": "new_ui",
    "user_id": "user123",
    "environment": "development"
  }'
```

## Caching Strategies

### 1. Local In-Memory Cache

**Python:**
```python
from functools import lru_cache
from datetime import datetime, timedelta

class LocalFeatureFlagsCache:
    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
    
    def get(self, key):
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now() - entry['timestamp'] < timedelta(seconds=self.ttl):
                return entry['value']
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = {
            'value': value,
            'timestamp': datetime.now()
        }
```

### 2. Redis Cache (Recommended)

**Benefits:**
- Shared across service instances
- Persistent across restarts
- High performance
- TTL support

**Implementation:** See client library examples above

### 3. Hybrid Cache

Combine local + Redis for best performance:

```python
class HybridCache:
    def __init__(self, redis_client, local_ttl=60, redis_ttl=300):
        self.redis = redis_client
        self.local_cache = {}
        self.local_ttl = local_ttl
        self.redis_ttl = redis_ttl
    
    async def get(self, key):
        # Check local first
        if key in self.local_cache:
            entry = self.local_cache[key]
            if datetime.now() - entry['timestamp'] < timedelta(seconds=self.local_ttl):
                return entry['value']
        
        # Check Redis
        if self.redis:
            cached = await self.redis.get(key)
            if cached:
                value = json.loads(cached)
                # Update local cache
                self.local_cache[key] = {
                    'value': value,
                    'timestamp': datetime.now()
                }
                return value
        
        return None
```

## Error Handling

### Graceful Degradation

Always provide a default value:

```python
# Good: Graceful degradation
enabled = await ff_client.is_enabled("new_ui", user_id, default=False)
if enabled:
    use_new_ui()
else:
    use_old_ui()

# Bad: No default
enabled = await ff_client.is_enabled("new_ui", user_id)  # Could raise exception
```

### Retry Logic

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def is_enabled_with_retry(flag_name, user_id, default=False):
    return await ff_client.is_enabled(flag_name, user_id, default=default)
```

### Circuit Breaker

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def evaluate_flag(flag_name, user_id):
    return await ff_client.is_enabled(flag_name, user_id, default=False)
```

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_feature_flag_enabled():
    with patch('feature_flags_client.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"enabled": True, "reason": "user_targeted"})
        
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
        
        client = FeatureFlagsClient("http://config-service:8082", "development")
        result = await client.is_enabled("new_ui", "user123")
        
        assert result is True
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_integration_with_config_service():
    client = FeatureFlagsClient(
        config_service_url="http://localhost:8082",
        environment="test"
    )
    
    # Assume flag exists in test environment
    result = await client.is_enabled("test_flag", "test_user", default=False)
    assert isinstance(result, bool)
```

### Mocking for Development

```python
class MockFeatureFlagsClient:
    def __init__(self, flags=None):
        self.flags = flags or {}
    
    async def is_enabled(self, flag_name, user_id, default=False):
        return self.flags.get(flag_name, default)
```

## Best Practices

### 1. Initialize Once, Reuse

```python
# Good: Singleton pattern
class Service:
    def __init__(self):
        self.ff_client = FeatureFlagsClient(...)
    
    async def handle_request(self, user_id):
        enabled = await self.ff_client.is_enabled("new_ui", user_id)
        # ...

# Bad: Creating new client for each request
async def handle_request(user_id):
    client = FeatureFlagsClient(...)  # Don't do this
    enabled = await client.is_enabled("new_ui", user_id)
```

### 2. Use Batch Evaluation

```python
# Good: Batch evaluation
flags = await ff_client.batch_evaluate(
    ["new_ui", "dark_mode", "beta_features"],
    user_id
)

# Bad: Multiple individual calls
ui_enabled = await ff_client.is_enabled("new_ui", user_id)
dark_enabled = await ff_client.is_enabled("dark_mode", user_id)
beta_enabled = await ff_client.is_enabled("beta_features", user_id)
```

### 3. Cache Aggressively

- Use Redis for shared cache
- Set appropriate TTL (5 minutes recommended)
- Invalidate on flag updates (via Kafka events)

### 4. Handle Failures Gracefully

```python
try:
    enabled = await ff_client.is_enabled("new_ui", user_id, default=False)
except Exception as e:
    logger.error(f"Feature flag check failed: {e}")
    enabled = False  # Safe default
```

### 5. Monitor and Log

```python
import logging

logger = logging.getLogger(__name__)

async def is_enabled_with_logging(flag_name, user_id):
    enabled = await ff_client.is_enabled(flag_name, user_id, default=False)
    logger.info(f"Flag {flag_name} for user {user_id}: {enabled}")
    return enabled
```

## Examples

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from feature_flags_client import FeatureFlagsClient

app = FastAPI()

# Initialize client
ff_client = FeatureFlagsClient(
    config_service_url=os.getenv("CONFIG_SERVICE_URL"),
    environment=os.getenv("ENVIRONMENT", "development")
)

@app.get("/api/users/{user_id}/dashboard")
async def get_dashboard(user_id: str):
    # Check feature flags
    new_ui = await ff_client.is_enabled("new_ui", user_id, default=False)
    dark_mode = await ff_client.is_enabled("dark_mode", user_id, default=False)
    
    if new_ui:
        return {"template": "new_dashboard", "dark_mode": dark_mode}
    else:
        return {"template": "old_dashboard", "dark_mode": dark_mode}
```

### Express.js Integration

```javascript
const express = require('express');
const FeatureFlagsClient = require('./featureFlagsClient');

const app = express();
const ffClient = new FeatureFlagsClient({
    configServiceUrl: process.env.CONFIG_SERVICE_URL,
    environment: process.env.ENVIRONMENT || 'development'
});

app.get('/api/users/:userId/dashboard', async (req, res) => {
    const { userId } = req.params;
    
    const newUi = await ffClient.isEnabled('new_ui', userId, false);
    const darkMode = await ffClient.isEnabled('dark_mode', userId, false);
    
    if (newUi) {
        res.json({ template: 'new_dashboard', darkMode });
    } else {
        res.json({ template: 'old_dashboard', darkMode });
    }
});
```

### Event-Driven Updates

```python
from kafka import KafkaConsumer
import json

async def consume_flag_updates():
    consumer = KafkaConsumer(
        'feature-flag-updates',
        bootstrap_servers=['kafka:9092'],
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    
    for message in consumer:
        event = message.value
        flag_name = event.get('flag_name')
        environment = event.get('environment')
        
        # Invalidate cache
        if ff_client.redis:
            pattern = f"ff_eval:{environment}:{flag_name}:*"
            keys = await ff_client.redis.keys(pattern)
            if keys:
                await ff_client.redis.delete(*keys)
        
        logger.info(f"Flag {flag_name} updated in {environment}, cache invalidated")
```

## Related Documentation

- [Feature Flags Implementation](./FEATURE_FLAGS.md) - Detailed implementation guide
- [Config Service README](../README.md) - Service overview
- [Feature Flags Implementation Details](../FEATURE_FLAGS_IMPLEMENTATION.md) - Implementation status

