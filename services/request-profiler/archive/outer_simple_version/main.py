"""FastAPI application for RequestProfiler"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .profiler import RequestProfiler
from .schemas import (
    ProfileRequest,
    ProfileResponse,
    HealthResponse
)
from .config import settings


app = FastAPI(
    title="RequestProfiler API",
    description="Indian Language Request Profiling Service",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize profiler
profiler = RequestProfiler()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        languages_supported=len(profiler.languages)
    )


@app.get("/languages")
async def get_supported_languages():
    """Get list of supported languages"""
    return {
        "languages": profiler.get_supported_languages()
    }


@app.post("/profile", response_model=ProfileResponse)
async def profile_request(request: ProfileRequest):
    """Profile a text request"""
    try:
        profile = profiler.profile(request.text)
        return ProfileResponse(
            success=True,
            profile=profile,
            error=None
        )
    except Exception as e:
        return ProfileResponse(
            success=False,
            profile=None,
            error=str(e)
        )


@app.post("/batch-profile")
async def batch_profile(requests: list[ProfileRequest]):
    """Profile multiple requests"""
    try:
        texts = [r.text for r in requests]
        profiles = profiler.batch_profile(texts)
        return {
            "success": True,
            "profiles": profiles
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def create_app() -> FastAPI:
    """Factory function to create the app"""
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
