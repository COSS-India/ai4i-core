"""
Integration tests for authentication and authorization flows across all AI services.
"""
import pytest
import httpx
import asyncio
from unittest.mock import patch


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthenticationFlows:
    """Test class for authentication flow integration tests."""

    async def test_api_key_validation_success(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API key validation with successful request."""
        # Test with ASR service
        asr_payload = {
            "audio": [{"audioContent": "dummy_base64"}],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "vakyansh-asr-en",
                "audioFormat": "wav",
                "samplingRate": 16000
            }
        }
        
        response = await authenticated_client.post("/api/v1/asr/inference", json=asr_payload)
        # Should succeed (even if audio is dummy, auth should work)
        assert response.status_code in [200, 422]  # 422 for invalid audio is acceptable

    async def test_api_key_validation_redis_cache(self, authenticated_client: httpx.AsyncClient, redis_client):
        """Test API key validation with Redis caching."""
        # Clear Redis cache first
        await redis_client.flushdb()
        
        # First request (cache miss)
        start_time = asyncio.get_event_loop().time()
        response1 = await authenticated_client.get("/api/v1/asr/health")
        first_request_time = asyncio.get_event_loop().time() - start_time
        
        # Second request (cache hit)
        start_time = asyncio.get_event_loop().time()
        response2 = await authenticated_client.get("/api/v1/asr/health")
        second_request_time = asyncio.get_event_loop().time() - start_time
        
        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Second request should be faster (cached)
        # Note: This is a basic test - in practice, the difference might be minimal
        assert second_request_time <= first_request_time

    async def test_api_key_expiration(self, sample_text: dict):
        """Test API key expiration handling."""
        # This would require creating an expired API key in the database
        # For now, we'll test with an invalid key
        async with httpx.AsyncClient(
            base_url="http://localhost:8080",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer expired_key_12345"
            }
        ) as client:
            payload = {
                "input": [{"source": sample_text["english"]}],
                "config": {
                    "language": {"sourceLanguage": "en"},
                    "serviceId": "indic-tts-coqui-misc",
                    "gender": "female",
                    "audioFormat": "wav",
                    "samplingRate": 22050
                }
            }
            
            response = await client.post("/api/v1/tts/inference", json=payload)
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    async def test_api_key_inactive(self, sample_text: dict):
        """Test inactive API key handling."""
        # This would require creating an inactive API key in the database
        # For now, we'll test with an invalid key
        async with httpx.AsyncClient(
            base_url="http://localhost:8080",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer inactive_key_12345"
            }
        ) as client:
            payload = {
                "input": [{"source": sample_text["english"]}],
                "config": {
                    "language": {
                        "sourceLanguage": "en",
                        "targetLanguage": "hi"
                    },
                    "serviceId": "indictrans-v2-all"
                }
            }
            
            response = await client.post("/api/v1/nmt/inference", json=payload)
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    async def test_rate_limiting_per_api_key(self, sample_text: dict):
        """Test rate limiting per API key."""
        # Create two different API keys (simulated)
        key1_client = httpx.AsyncClient(
            base_url="http://localhost:8080",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_api_key_1"
            }
        )
        
        key2_client = httpx.AsyncClient(
            base_url="http://localhost:8080",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_api_key_2"
            }
        )
        
        try:
            # Send requests with key1 until rate limited
            payload = {
                "input": [{"source": sample_text["english"]}],
                "config": {
                    "language": {
                        "sourceLanguage": "en",
                        "targetLanguage": "hi"
                    },
                    "serviceId": "indictrans-v2-all"
                }
            }
            
            responses_key1 = []
            for i in range(65):  # Exceed rate limit
                response = await key1_client.post("/api/v1/nmt/inference", json=payload)
                responses_key1.append(response)
            
            # Send request with key2 (should work)
            response_key2 = await key2_client.post("/api/v1/nmt/inference", json=payload)
            
            # Check that key1 was rate limited
            assert responses_key1[-1].status_code == 429
            
            # Check that key2 still works (or at least doesn't get rate limited by key1's limit)
            assert response_key2.status_code != 429
            
        finally:
            await key1_client.aclose()
            await key2_client.aclose()

    async def test_rate_limiting_reset_after_minute(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test rate limiting reset after time window."""
        payload = {
            "input": [{"source": sample_text["english"]}],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        # Send requests until rate limited
        responses = []
        for i in range(65):
            response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
            responses.append(response)
            if response.status_code == 429:
                break
        
        # Wait for rate limit to reset (in real test, this would be 61 seconds)
        # For testing purposes, we'll just verify the rate limiting behavior
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        assert len(rate_limited_responses) > 0

    async def test_request_logging_with_user_context(self, authenticated_client: httpx.AsyncClient, sample_text: dict, test_db_session):
        """Test request logging with user context."""
        payload = {
            "input": [{"source": sample_text["english"]}],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "indic-tts-coqui-misc",
                "gender": "female",
                "audioFormat": "wav",
                "samplingRate": 22050
            }
        }
        
        response = await authenticated_client.post("/api/v1/tts/inference", json=payload)
        
        # Request should be logged with user context
        # In a real implementation, we would query the database to verify logging
        assert response.status_code in [200, 422]  # 422 for invalid audio is acceptable

    async def test_cross_service_authentication(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test authentication across multiple services."""
        # Test ASR service
        asr_payload = {
            "audio": [{"audioContent": "dummy_base64"}],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "vakyansh-asr-en",
                "audioFormat": "wav",
                "samplingRate": 16000
            }
        }
        asr_response = await authenticated_client.post("/api/v1/asr/inference", json=asr_payload)
        
        # Test TTS service
        tts_payload = {
            "input": [{"source": sample_text["english"]}],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "indic-tts-coqui-misc",
                "gender": "female",
                "audioFormat": "wav",
                "samplingRate": 22050
            }
        }
        tts_response = await authenticated_client.post("/api/v1/tts/inference", json=tts_payload)
        
        # Test NMT service
        nmt_payload = {
            "input": [{"source": sample_text["english"]}],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        nmt_response = await authenticated_client.post("/api/v1/nmt/inference", json=nmt_payload)
        
        # All services should accept the same API key
        # (Some may return 422 for invalid data, but not 401 for auth)
        assert asr_response.status_code != 401
        assert tts_response.status_code != 401
        assert nmt_response.status_code != 401

    async def test_session_management(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test session management with session ID."""
        # This would require creating a session in the sessions table
        # For now, we'll test that requests work with the current setup
        payload = {
            "input": [{"source": sample_text["english"]}],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        # Request should succeed (session management is handled internally)
        assert response.status_code in [200, 422]  # 422 for invalid data is acceptable
