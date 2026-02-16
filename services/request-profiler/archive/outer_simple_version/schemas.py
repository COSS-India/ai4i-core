"""Pydantic schemas for RequestProfiler"""

from pydantic import BaseModel
from typing import Optional
from enum import Enum


class IntentType(str, Enum):
    GENERAL = "General Query"
    TECHNICAL = "Technical"
    CREATIVE = "Creative"
    LEGAL = "Legal"
    MEDICAL = "Medical"


class LanguageDetection(BaseModel):
    """Language detection result"""
    language: str
    language_name: str
    confidence: float


class RequestProfile(BaseModel):
    """Complete request profile"""
    text: str
    language: LanguageDetection
    complexity_score: float
    intent: IntentType
    suggested_model: str
    processing_time_ms: Optional[float] = None


class ProfileRequest(BaseModel):
    """Request to profile text"""
    text: str
    include_metadata: bool = True


class ProfileResponse(BaseModel):
    """Response with profiled request"""
    success: bool
    profile: Optional[RequestProfile] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    languages_supported: int
