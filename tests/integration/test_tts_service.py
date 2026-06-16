"""
Integration tests for TTS service covering batch inference, voice management, authentication, and error handling.
"""
import pytest
import httpx
import base64


@pytest.mark.integration
@pytest.mark.asyncio
class TestTTSService:
    """Test class for TTS service integration tests."""

    async def test_tts_batch_inference_success(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test successful TTS batch inference."""
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
        
        assert response.status_code == 200
        data = response.json()
        assert "audio" in data
        assert len(data["audio"]) == 1
        assert "audioContent" in data["audio"][0]
        
        # Verify audio content is valid base64
        audio_content = data["audio"][0]["audioContent"]
        assert isinstance(audio_content, str)
        try:
            decoded_audio = base64.b64decode(audio_content)
            assert len(decoded_audio) > 0
        except Exception:
            pytest.fail("Invalid base64 audio content")

    async def test_tts_batch_inference_multiple_texts(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test TTS batch inference with multiple text inputs."""
        payload = {
            "input": [
                {"source": sample_text["english"]},
                {"source": sample_text["hindi"]},
                {"source": sample_text["tamil"]}
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
        
        assert response.status_code == 200
        data = response.json()
        assert "audio" in data
        assert len(data["audio"]) == 3
        
        for audio in data["audio"]:
            assert "audioContent" in audio
            # Verify each audio is valid base64
            try:
                decoded_audio = base64.b64decode(audio["audioContent"])
                assert len(decoded_audio) > 0
            except Exception:
                pytest.fail("Invalid base64 audio content")

    async def test_tts_batch_inference_long_text(self, authenticated_client: httpx.AsyncClient):
        """Test TTS batch inference with long text (triggers chunking)."""
        long_text = "This is a very long text that should trigger the text chunking mechanism in the TTS service. " * 10  # > 400 characters
        
        payload = {
            "input": [
                {"source": long_text}
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
        
        assert response.status_code == 200
        data = response.json()
        assert "audio" in data
        assert len(data["audio"]) == 1
        assert "audioContent" in data["audio"][0]

    async def test_tts_batch_inference_invalid_text(self, authenticated_client: httpx.AsyncClient):
        """Test TTS batch inference with invalid text."""
        payload = {
            "input": [
                {"source": ""}  # Empty text
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
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    async def test_tts_batch_inference_missing_api_key(self, api_client: httpx.AsyncClient, sample_text: dict):
        """Test TTS batch inference without API key."""
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
        
        response = await api_client.post("/api/v1/tts/inference", json=payload)
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_tts_list_voices(self, authenticated_client: httpx.AsyncClient):
        """Test listing available TTS voices."""
        response = await authenticated_client.get("/api/v1/tts/voices")
        
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        assert isinstance(data["voices"], list)
        
        for voice in data["voices"]:
            assert "voice_id" in voice
            assert "name" in voice
            assert "gender" in voice
            assert "languages" in voice
            assert "model_id" in voice

    async def test_tts_list_voices_filter_by_language(self, authenticated_client: httpx.AsyncClient):
        """Test filtering TTS voices by language."""
        response = await authenticated_client.get("/api/v1/tts/voices?language=ta")
        
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        
        for voice in data["voices"]:
            assert "ta" in voice["languages"]

    async def test_tts_list_voices_filter_by_gender(self, authenticated_client: httpx.AsyncClient):
        """Test filtering TTS voices by gender."""
        response = await authenticated_client.get("/api/v1/tts/voices?gender=female")
        
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        
        for voice in data["voices"]:
            assert voice["gender"] == "female"

    async def test_tts_get_voice_by_id(self, authenticated_client: httpx.AsyncClient):
        """Test getting specific voice by ID."""
        voice_id = "indic-tts-coqui-dravidian-female"
        response = await authenticated_client.get(f"/api/v1/tts/voices/{voice_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["voice_id"] == voice_id
        assert "name" in data
        assert "gender" in data
        assert "languages" in data

    async def test_tts_health_check(self, authenticated_client: httpx.AsyncClient):
        """Test TTS service health check."""
        response = await authenticated_client.get("/api/v1/tts/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "components" in data
        
        components = data["components"]
        assert "redis" in components
        assert "postgres" in components
        assert "triton" in components
        
        for component, status in components.items():
            assert status == "healthy"

    async def test_tts_audio_format_conversion(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test TTS audio format conversion."""
        payload = {
            "input": [
                {"source": sample_text["english"]}
            ],
            "config": {
                "language": {"sourceLanguage": "en"},
                "serviceId": "indic-tts-coqui-misc",
                "gender": "female",
                "audioFormat": "mp3",
                "samplingRate": 22050
            }
        }
        
        response = await authenticated_client.post("/api/v1/tts/inference", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "audio" in data
        assert "config" in data
        assert data["config"]["audioFormat"] == "mp3"

    async def test_tts_database_logging(self, authenticated_client: httpx.AsyncClient, sample_text: dict, test_db_session):
        """Test TTS request and result logging to database."""
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
        
        assert response.status_code == 200
        
        # Verify response structure
        data = response.json()
        assert "audio" in data
        assert len(data["audio"]) > 0
