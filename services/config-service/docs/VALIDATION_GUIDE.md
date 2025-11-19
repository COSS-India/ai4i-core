# Feature Flag Validation Guide

## How to Validate Feature Flags in Your Integrations

This guide shows you how to validate that feature flags are working correctly in your microservices.

## Quick Validation Test

### 1. Test Basic Evaluation

```bash
# Test flag evaluation for different environments
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "test-flag-4",
    "default_value": false,
    "environment": "development"
  }'

# Expected: If flag is disabled in development
# {
#   "value": false,
#   "reason": "DISABLED"
# }

curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "test-flag-4",
    "default_value": false,
    "environment": "production"
  }'

# Expected: If flag is enabled in production
# {
#   "value": true,
#   "reason": "TARGETING_MATCH"
# }
```

### 2. Validate Environment-Specific Behavior

The key validation is that **the same flag returns different values for different environments**:

```bash
# Development (disabled)
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"flag_name": "test-flag-4", "default_value": false, "environment": "development"}'
# Should return: {"value": false, "reason": "DISABLED"}

# Production (enabled)
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"flag_name": "test-flag-4", "default_value": false, "environment": "production"}'
# Should return: {"value": true, "reason": "TARGETING_MATCH"}
```

## Integration Testing in Your Microservices

### Python/FastAPI Example

```python
import httpx
import pytest

@pytest.mark.asyncio
async def test_feature_flag_evaluation():
    """Test that feature flags work correctly for different environments"""
    
    async with httpx.AsyncClient() as client:
        base_url = "http://config-service:8082/api/v1/feature-flags"
        
        # Test development environment (flag disabled)
        response = await client.post(
            f"{base_url}/evaluate",
            json={
                "flag_name": "test-flag-4",
                "default_value": False,
                "environment": "development"
            }
        )
        result = response.json()
        assert result["value"] == False
        assert result["reason"] == "DISABLED"
        
        # Test production environment (flag enabled)
        response = await client.post(
            f"{base_url}/evaluate",
            json={
                "flag_name": "test-flag-4",
                "default_value": False,
                "environment": "production"
            }
        )
        result = response.json()
        assert result["value"] == True
        assert result["reason"] == "TARGETING_MATCH"
```

### Using the Feature Flag Client

```python
from utils.feature_flag_client import FeatureFlagClient

async def test_integration():
    """Test feature flag integration in your service"""
    client = FeatureFlagClient()
    
    # Test with development environment
    is_enabled_dev = await client.is_enabled(
        flag_name="test-flag-4",
        default_value=False,
        environment="development"
    )
    assert is_enabled_dev == False, "Flag should be disabled in development"
    
    # Test with production environment
    is_enabled_prod = await client.is_enabled(
        flag_name="test-flag-4",
        default_value=False,
        environment="production"
    )
    assert is_enabled_prod == True, "Flag should be enabled in production"
    
    print("✅ Feature flags working correctly!")
```

## Validation Checklist

### ✅ Environment-Specific Behavior
- [ ] Flag returns correct value for development environment
- [ ] Flag returns correct value for production environment
- [ ] Different environments return different values (when configured differently)

### ✅ Reason Codes
- [ ] `DISABLED` when flag is disabled in that environment
- [ ] `TARGETING_MATCH` when flag is enabled and matches
- [ ] `DEFAULT` when flag doesn't match targeting rules
- [ ] `ERROR` when flag doesn't exist or evaluation fails

### ✅ Default Values
- [ ] Returns default value when flag is disabled
- [ ] Returns default value when flag doesn't exist
- [ ] Returns default value on evaluation errors

### ✅ Targeting (if applicable)
- [ ] User targeting works (when user_id is in target list)
- [ ] Percentage rollout works (consistent for same user)
- [ ] Context-based targeting works (when context matches)

## Real-World Integration Example

### In Your ASR Service

```python
from utils.feature_flag_client import FeatureFlagClient

class ASRService:
    def __init__(self):
        self.flag_client = FeatureFlagClient()
    
    async def process_audio(self, audio_data, user_id: str):
        # Check if new model is enabled for this user
        use_new_model = await self.flag_client.is_enabled(
            flag_name="new-asr-model",
            user_id=user_id,
            default_value=False,
            environment=os.getenv("ENVIRONMENT", "development")
        )
        
        if use_new_model:
            # Use new model
            return await self.new_model_process(audio_data)
        else:
            # Use old model
            return await self.old_model_process(audio_data)
```

### Testing the Integration

```python
@pytest.mark.asyncio
async def test_asr_service_with_feature_flag():
    service = ASRService()
    
    # Mock the flag client to return True
    service.flag_client.is_enabled = AsyncMock(return_value=True)
    
    result = await service.process_audio(b"audio_data", "user-123")
    
    # Verify new model was used
    assert service.new_model_process.called
    assert not service.old_model_process.called
```

## Monitoring and Observability

### Log Validation

Check logs to ensure flags are being evaluated correctly:

```bash
# Check config service logs
docker logs ai4v-config-service | grep "feature_flag"

# Look for:
# - "Flag 'test-flag-4' is disabled in environment 'development'"
# - "Flag 'test-flag-4' is enabled in environment 'production'"
```

### Metrics Validation

Monitor these metrics:
- Flag evaluation count per environment
- Cache hit rates
- Evaluation errors
- Response times

## Troubleshooting

### Issue: Flag returns same value for all environments

**Check:**
1. Is the flag configured differently in Unleash UI for each environment?
2. Are you passing the correct `environment` parameter?
3. Check config service logs for environment mismatch warnings

### Issue: Flag always returns default value

**Check:**
1. Does the flag exist in Unleash?
2. Is the flag enabled in the requested environment?
3. Check if flag name matches exactly (case-sensitive)

### Issue: Reason is always "ERROR"

**Check:**
1. Is Unleash server accessible?
2. Is `UNLEASH_API_TOKEN` set correctly?
3. Check config service logs for API errors

## Best Practices for Validation

1. **Test in all environments**: Always test flags in development, staging, and production
2. **Use default values**: Always provide sensible default values
3. **Monitor logs**: Check logs regularly for flag evaluation issues
4. **Test edge cases**: Test with missing flags, disabled flags, and error scenarios
5. **Validate targeting**: If using targeting, test with different user IDs and contexts

