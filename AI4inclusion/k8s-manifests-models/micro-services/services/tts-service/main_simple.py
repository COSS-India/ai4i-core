"""
Simple TTS Service - Minimal working version
"""

import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for responses
class VoiceMetadata(BaseModel):
    voiceId: str
    name: str
    language: str
    gender: str
    age: str
    isActive: bool

class VoiceListResponse(BaseModel):
    voices: List[VoiceMetadata]
    totalCount: int
    page: int = 1
    pageSize: int = 50

class StreamingInfo(BaseModel):
    endpoint: str
    supported_formats: List[str]

class ModelInfo(BaseModel):
    modelId: str
    name: str
    language: str
    gender: str
    isActive: bool

# Create FastAPI app
app = FastAPI(
    title="TTS Service",
    description="Text-to-Speech Microservice",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "tts-service"}

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "TTS Service is running", "status": "ok"}

@app.get("/info")
async def service_info():
    """Service information endpoint."""
    return {
        "service": "tts-service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "/health",
            "/info",
            "/"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
