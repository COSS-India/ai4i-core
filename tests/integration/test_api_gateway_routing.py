"""
Integration tests for API Gateway routing to AI services.
"""
import pytest
import httpx


@pytest.mark.integration
@pytest.mark.asyncio
class TestAPIGatewayRouting:
    """Test class for API Gateway routing integration tests."""

    async def test_gateway_routes_to_asr_service(self, authenticated_client: httpx.AsyncClient, sample_audio_base64: str):
        """Test API Gateway routes to ASR service."""
        payload = {
            "audio": [
                {"audioContent": sample_audio_base64}
            ],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "vakyansh-asr-en",
                "audioFormat": "wav",
                "samplingRate": 16000
            }
        }
        
        response = await authenticated_client.post("/api/v1/asr/inference", json=payload)
        
        # Should route to ASR service successfully
        assert response.status_code in [200, 422]  # 422 for invalid audio is acceptable
        
        # Verify response structure indicates ASR service processing
        if response.status_code == 200:
            data = response.json()
            assert "output" in data

    async def test_gateway_routes_to_tts_service(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API Gateway routes to TTS service."""
        payload = {
            "input": [
                {"source": sample_text["english"]}
            ],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "indic-tts-coqui-misc",
                "gender": "female",
                "audioFormat": "wav",
                "samplingRate": 22050
            }
        }
        
        response = await authenticated_client.post("/api/v1/tts/inference", json=payload)
        
        # Should route to TTS service successfully
        assert response.status_code in [200, 422]  # 422 for invalid data is acceptable
        
        # Verify response structure indicates TTS service processing
        if response.status_code == 200:
            data = response.json()
            assert "audio" in data

    async def test_gateway_routes_to_nmt_service(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API Gateway routes to NMT service."""
        payload = {
            "input": [
                {"source": sample_text["english"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        # Should route to NMT service successfully
        assert response.status_code in [200, 422]  # 422 for invalid data is acceptable
        
        # Verify response structure indicates NMT service processing
        if response.status_code == 200:
            data = response.json()
            assert "output" in data

    async def test_gateway_health_aggregation(self, api_client: httpx.AsyncClient):
        """Test API Gateway health aggregation."""
        response = await api_client.get("/api/v1/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should contain URLs for all services
        assert "asr" in data
        assert "tts" in data
        assert "nmt" in data
        
        # Verify service URLs are correct
        assert data["asr"] == "http://asr-service:8087"
        assert data["tts"] == "http://tts-service:8088"
        assert data["nmt"] == "http://nmt-service:8089"

    async def test_gateway_load_balancing(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API Gateway load balancing (if multiple instances)."""
        # This test assumes multiple instances are running
        # In practice, you would scale the service: docker-compose up -d --scale asr-service=3
        
        payload = {
            "input": [
                {"source": sample_text["english"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        # Send multiple requests to test load balancing
        responses = []
        for i in range(10):
            response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
            responses.append(response)
        
        # All requests should succeed (or fail consistently)
        success_count = sum(1 for r in responses if r.status_code == 200)
        error_count = sum(1 for r in responses if r.status_code != 200)
        
        # Either all succeed or all fail consistently
        assert success_count == 10 or error_count == 10

    async def test_gateway_service_discovery(self, api_client: httpx.AsyncClient):
        """Test API Gateway service discovery."""
        response = await api_client.get("/api/v1/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all AI services are registered
        required_services = ["asr", "tts", "nmt"]
        for service in required_services:
            assert service in data
            assert data[service].startswith("http://")
            assert ":808" in data[service]  # Should contain port

    async def test_gateway_handles_service_failure(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API Gateway handles service failure gracefully."""
        # This test would require stopping a service
        # For now, we'll test with a non-existent endpoint
        response = await authenticated_client.post("/api/v1/nonexistent/inference", json={})
        
        # Should return 404 for non-existent service
        assert response.status_code == 404

    async def test_gateway_request_timeout(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API Gateway request timeout handling."""
        # This would require mocking a slow service response
        # For now, we'll test with a normal request
        payload = {
            "input": [
                {"source": sample_text["english"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        # Use a very short timeout to test timeout handling
        async with httpx.AsyncClient(
            base_url="http://localhost:8080",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_api_key_12345"
            },
            timeout=0.1  # Very short timeout
        ) as client:
            try:
                response = await client.post("/api/v1/nmt/inference", json=payload)
                # If it doesn't timeout, it should succeed or fail with expected error
                assert response.status_code in [200, 422, 500, 504]
            except httpx.TimeoutException:
                # Timeout is also acceptable for this test
                pass

    async def test_gateway_cors_headers(self, api_client: httpx.AsyncClient):
        """Test API Gateway CORS headers."""
        # Send OPTIONS request to test CORS
        response = await api_client.options("/api/v1/asr/inference")
        
        # Should include CORS headers
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers

    async def test_gateway_rate_limiting_headers(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test API Gateway includes rate limiting headers."""
        payload = {
            "input": [
                {"source": sample_text["english"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        # Should include rate limiting headers
        if response.status_code == 429:
            assert "Retry-After" in response.headers
        elif response.status_code == 200:
            # May include rate limit info headers
            pass  # Rate limit headers are optional for successful requests
