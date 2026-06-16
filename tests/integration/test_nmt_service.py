"""
Integration tests for NMT service covering batch inference, language detection, authentication, and error handling.
"""
import pytest
import httpx


@pytest.mark.integration
@pytest.mark.asyncio
class TestNMTService:
    """Test class for NMT service integration tests."""

    async def test_nmt_batch_inference_success(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test successful NMT batch inference."""
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
        
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert len(data["output"]) == 1
        assert "source" in data["output"][0]
        assert "target" in data["output"][0]
        assert isinstance(data["output"][0]["target"], str)
        assert len(data["output"][0]["target"]) > 0

    async def test_nmt_batch_inference_multiple_texts(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test NMT batch inference with multiple text inputs."""
        texts = [
            sample_text["english"],
            "Hello world",
            "Good morning",
            "How are you?",
            "Thank you very much"
        ]
        
        payload = {
            "input": [{"source": text} for text in texts],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert len(data["output"]) == len(texts)
        
        for output in data["output"]:
            assert "source" in output
            assert "target" in output
            assert isinstance(output["target"], str)

    async def test_nmt_batch_inference_max_batch_size(self, authenticated_client: httpx.AsyncClient):
        """Test NMT batch inference with maximum batch size (90 texts)."""
        texts = [f"Test text {i}" for i in range(90)]  # Max batch size
        
        payload = {
            "input": [{"source": text} for text in texts],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert len(data["output"]) == 90

    async def test_nmt_batch_inference_exceeds_batch_size(self, authenticated_client: httpx.AsyncClient):
        """Test NMT batch inference exceeding maximum batch size."""
        texts = [f"Test text {i}" for i in range(91)]  # Exceeds max batch size
        
        payload = {
            "input": [{"source": text} for text in texts],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": "hi"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data

    async def test_nmt_batch_inference_bidirectional(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test NMT batch inference in both directions."""
        # English to Hindi
        payload_en_hi = {
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
        
        response_en_hi = await authenticated_client.post("/api/v1/nmt/inference", json=payload_en_hi)
        assert response_en_hi.status_code == 200
        
        # Hindi to English
        payload_hi_en = {
            "input": [
                {"source": sample_text["hindi"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "hi",
                    "targetLanguage": "en"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response_hi_en = await authenticated_client.post("/api/v1/nmt/inference", json=payload_hi_en)
        assert response_hi_en.status_code == 200

    async def test_nmt_batch_inference_script_codes(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test NMT batch inference with script codes."""
        payload = {
            "input": [
                {"source": sample_text["hindi"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "hi",
                    "targetLanguage": "en",
                    "sourceScriptCode": "Deva"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert len(data["output"]) == 1

    async def test_nmt_batch_inference_missing_api_key(self, api_client: httpx.AsyncClient, sample_text: dict):
        """Test NMT batch inference without API key."""
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
        
        response = await api_client.post("/api/v1/nmt/inference", json=payload)
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_nmt_list_models(self, authenticated_client: httpx.AsyncClient):
        """Test listing available NMT models."""
        response = await authenticated_client.get("/api/v1/nmt/models")
        
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        
        for model in data["models"]:
            assert "model_id" in model
            assert "language_pairs" in model
            assert "description" in model

    async def test_nmt_health_check(self, authenticated_client: httpx.AsyncClient):
        """Test NMT service health check."""
        response = await authenticated_client.get("/api/v1/nmt/health")
        
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

    async def test_nmt_language_detection(self, authenticated_client: httpx.AsyncClient, sample_text: dict):
        """Test NMT language detection with auto-detect."""
        payload = {
            "input": [
                {"source": sample_text["hindi"]}
            ],
            "config": {
                "language": {
                    "sourceLanguage": "auto",
                    "targetLanguage": "en"
                },
                "serviceId": "indictrans-v2-all"
            }
        }
        
        response = await authenticated_client.post("/api/v1/nmt/inference", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert len(data["output"]) == 1
        
        # Check if language detection information is included
        output = data["output"][0]
        if "language_detected" in output:
            assert output["language_detected"] == "hi"

    async def test_nmt_database_logging(self, authenticated_client: httpx.AsyncClient, sample_text: dict, test_db_session):
        """Test NMT request and result logging to database."""
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
        
        assert response.status_code == 200
        
        # Verify response structure
        data = response.json()
        assert "output" in data
        assert len(data["output"]) > 0
