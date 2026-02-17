"""API tests for RequestProfiler"""

import pytest
from fastapi.testclient import TestClient
from request_profiler.main import app


client = TestClient(app)


def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["languages_supported"] == 6


def test_get_languages():
    """Test get supported languages"""
    response = client.get("/languages")
    assert response.status_code == 200
    data = response.json()
    assert "languages" in data
    assert len(data["languages"]) == 6


def test_profile_hindi():
    """Test profiling Hindi text"""
    response = client.post("/profile", json={"text": "नमस्ते, आप कैसे हैं?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["profile"]["language"]["language"] == "hi"


def test_profile_tamil():
    """Test profiling Tamil text"""
    response = client.post("/profile", json={"text": "வணக்கம், எப்படி இருக்கீர்கள்?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["profile"]["language"]["language"] == "ta"


def test_profile_kannada():
    """Test profiling Kannada text"""
    response = client.post("/profile", json={"text": "ನಮಸ್ಕಾರ, ನೀವು ಹೇಗಿದ್ದೀರಿ?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["profile"]["language"]["language"] == "kn"


def test_profile_assamese():
    """Test profiling Assamese text"""
    response = client.post("/profile", json={"text": "নমস্কাৰ, আপুনি কেনেকৈ আছে?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["profile"]["language"]["language"] == "as"


def test_batch_profile():
    """Test batch profiling"""
    requests = [
        {"text": "नमस्ते"},
        {"text": "வணக்கம்"},
        {"text": "ನಮಸ್ಕಾರ"}
    ]
    response = client.post("/batch-profile", json=requests)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["profiles"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
