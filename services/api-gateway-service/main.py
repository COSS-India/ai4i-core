"""
API Gateway Service - Central entry point for all microservice requests
"""
import os
import sys
from dotenv import load_dotenv

# Add /app to Python path to ensure services module can be imported
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# Load environment variables from .env file
load_dotenv()

import asyncio
import logging
import uuid
import time
import json
from contextlib import nullcontext
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple, Union
from enum import Enum
from uuid import UUID
from urllib.parse import urlencode, urlparse, parse_qs, quote
from fastapi import FastAPI, Request, HTTPException, Response, Query, Header, Path, Body, Security, Depends, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, EmailStr, field_validator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.utils import get_openapi
import redis.asyncio as redis

# Import request logging middleware and error handlers
import httpx
from auth_middleware import auth_middleware
from decimal import Decimal

# AI4ICore logging and telemetry
from ai4icore_logging import (
    get_logger,
    CorrelationMiddleware,
    configure_logging,
)
from ai4icore_telemetry import setup_tracing, IPCaptureMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from smr import (
    call_policy_engine_for_smr,
    fetch_candidate_services_for_task,
    select_service_deterministically,
    get_downstream_for_task,
    inject_service_id_if_missing,
)

# Tenant resolver function - extract tenant context from JWT payload
# Replicated from services/multi-tenant-feature/utils/tenant_resolver.py
def resolve_tenant_from_jwt(jwt_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract tenant context from JWT payload.
    
    This function extracts tenant information from the JWT token payload.
    It returns a dictionary with tenant context or None if tenant_id is missing.
    
    Args:
        jwt_payload: Dictionary containing JWT token claims
        
    Returns:
        Dictionary with tenant context (tenant_id, tenant_uuid, schema_name, subscriptions, user_subscriptions)
        or None if tenant_id is not present in the payload
    """
    tenant_id = jwt_payload.get("tenant_id")
    if not tenant_id:
        return None
    
    return {
        "tenant_id": tenant_id,
        "tenant_uuid": jwt_payload.get("tenant_uuid"),
        "schema_name": jwt_payload.get("schema_name"),
        "subscriptions": jwt_payload.get("subscriptions", []),
        "user_subscriptions": jwt_payload.get("user_subscriptions", []),
    }

# OpenTelemetry for distributed tracing
try:
    from opentelemetry import trace
    from opentelemetry.propagate import inject
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    trace = None
    inject = None
    Status = None
    StatusCode = None
    FastAPIInstrumentor = None
    logging.warning("OpenTelemetry not available, tracing disabled")

# Tracer will be initialized after setup_tracing is called
# Helper function to get tracer dynamically (ensures it's available after setup_tracing)
def get_tracer():
    """Get tracer instance dynamically at runtime."""
    if not TRACING_AVAILABLE or not trace:
        return None
    try:
        return trace.get_tracer("api-gateway-service")
    except Exception:
        return None

tracer = None  # Will be set after setup_tracing, but use get_tracer() for reliability

# Configure AI4ICore logging
configure_logging(
    service_name=os.getenv("SERVICE_NAME", "api-gateway-service"),
    use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
)

logger = get_logger(__name__)

# Define auth error constants (fallback if not available from services.constants)
try:
    from services.constants.error_messages import AUTH_FAILED, AUTH_FAILED_MESSAGE
except ImportError:
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."

# Configure structured JSON logging
try:
    from ai4icore_logging import configure_logging, get_logger
    
    # Configure logging with JSON formatter
    configure_logging(
        service_name=os.getenv("SERVICE_NAME", "api-gateway"),
        use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
    )
    
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging if ai4icore_logging is not available
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# Auth service base URL (also used by SMR for auth metadata if needed)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")

# Pydantic models for ASR endpoints
class AudioInput(BaseModel):
    """Audio input for ASR processing."""
    audioContent: Optional[str] = Field(None, description="Base64 encoded audio content")
    audioUri: Optional[str] = Field(None, description="URI to audio file")

class LanguageConfig(BaseModel):
    """Language configuration for ASR."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi')")

class ASRInferenceConfig(BaseModel):
    """Configuration for ASR inference."""
    serviceId: Optional[str] = Field(None, description="ASR service/model ID (optional; Smart Router will assign if omitted)")
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: str = Field(default="wav", description="Audio format")
    samplingRate: int = Field(default=16000, description="Audio sampling rate")
    transcriptionFormat: str = Field(default="transcript", description="Output format")
    bestTokenCount: int = Field(default=0, description="Number of best token alternatives")

class ASRInferenceRequest(BaseModel):
    """ASR inference request model."""
    audio: List[AudioInput] = Field(..., description="List of audio inputs", min_items=1)
    config: ASRInferenceConfig = Field(..., description="Inference configuration")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

class TranscriptOutput(BaseModel):
    """Transcription output."""
    source: str = Field(..., description="Transcribed text")

class ASRInferenceResponse(BaseModel):
    """ASR inference response model."""
    output: List[TranscriptOutput] = Field(..., description="Transcription results")
    config: Optional[Dict[str, Any]] = Field(None, description="Response metadata")

# Pydantic models for NMT endpoints
class NMTLanguagePair(BaseModel):
    """Language pair configuration for NMT."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi', 'ta')")
    targetLanguage: str = Field(..., description="Target language code")
    sourceScriptCode: Optional[str] = Field(None, description="Script code for source (e.g., 'Deva', 'Arab')")
    targetScriptCode: Optional[str] = Field(None, description="Script code for target")

class NMTTextInput(BaseModel):
    """Text input for NMT translation."""
    source: str = Field(..., description="Input text to translate")

class NMTInferenceConfig(BaseModel):
    """Configuration for NMT inference."""
    serviceId: Optional[str] = Field(None, description="Identifier for NMT service/model (optional; Smart Router will assign if omitted)")
    language: NMTLanguagePair = Field(..., description="Language pair configuration")
    # Optional context for context-aware routing. When X-Context-Aware is true,
    # this field becomes required at runtime in the NMT fast-path logic.
    context: Optional[str] = Field(None, description="Optional context string for context-aware translation")

class NMTInferenceRequest(BaseModel):
    """NMT inference request model."""
    input: List[NMTTextInput] = Field(..., description="List of text inputs to translate", min_items=1)
    config: NMTInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

class NMTTranslationOutput(BaseModel):
    """Translation output."""
    source: str = Field(..., description="Source text")
    target: str = Field(..., description="Translated text")

class NMTInferenceResponse(BaseModel):
    """NMT inference response model."""
    output: List[NMTTranslationOutput] = Field(..., description="Translation results")

# Pydantic models for LLM endpoints
class LLMTextInput(BaseModel):
    """Text input for LLM processing."""
    source: str = Field(..., description="Input text to process")

class LLMInferenceConfig(BaseModel):
    """Configuration for LLM inference."""
    serviceId: Optional[str] = Field(None, description="Identifier for LLM service/model (optional; Smart Router will assign if omitted)")
    inputLanguage: Optional[str] = Field(None, description="Input language code (e.g., 'en', 'hi')")
    outputLanguage: Optional[str] = Field(None, description="Output language code")

class LLMInferenceRequest(BaseModel):
    """LLM inference request model."""
    input: List[LLMTextInput] = Field(..., description="List of text inputs to process", min_items=1)
    config: LLMInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

class LLMOutput(BaseModel):
    """LLM output result."""
    source: str = Field(..., description="Source text")
    target: str = Field(..., description="Processed text")

class LLMInferenceResponse(BaseModel):
    """LLM inference response model."""
    output: List[LLMOutput] = Field(..., description="Processing results")

# Pydantic models for TTS endpoints
class Gender(str, Enum):
    """Voice gender options for TTS."""
    MALE = "male"
    FEMALE = "female"

class AudioFormat(str, Enum):
    """Supported audio output formats."""
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    PCM = "pcm"

class TTSLanguageConfig(BaseModel):
    """Language configuration for TTS."""
    sourceLanguage: str = Field(..., description="Language code (e.g., 'en', 'hi', 'ta')")
    sourceScriptCode: Optional[str] = Field(None, description="Script code if applicable")

class TTSTextInput(BaseModel):
    """Individual text input for TTS synthesis."""
    source: str = Field(..., description="Input text to synthesize")
    audioDuration: Optional[float] = Field(None, description="Desired audio duration in seconds")

class TTSInferenceConfig(BaseModel):
    """Configuration for TTS inference."""
    serviceId: Optional[str] = Field(None, description="TTS service/model ID (optional; Smart Router will assign if omitted)")
    language: TTSLanguageConfig = Field(..., description="Language configuration")
    gender: Gender = Field(default=Gender.FEMALE, description="Voice gender")
    audioFormat: AudioFormat = Field(default=AudioFormat.WAV, description="Output audio format")
    samplingRate: int = Field(default=22050, description="Audio sampling rate")
    enableDurationAdjustment: bool = Field(default=True, description="Enable duration adjustment")
    enableFormatConversion: bool = Field(default=True, description="Enable format conversion")

class TTSInferenceRequest(BaseModel):
    """TTS inference request model."""
    input: List[TTSTextInput] = Field(..., description="List of text inputs", min_items=1)
    config: TTSInferenceConfig = Field(..., description="Inference configuration")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

class AudioOutput(BaseModel):
    """Audio output containing synthesized speech."""
    audioContent: str = Field(..., description="Base64-encoded audio data")
    audioUri: Optional[str] = Field(None, description="URL to audio file")

class AudioConfig(BaseModel):
    """Audio configuration metadata for the response."""
    language: TTSLanguageConfig = Field(..., description="Language configuration")
    audioFormat: AudioFormat = Field(..., description="Format of output audio")
    encoding: str = Field("base64", description="Encoding type")
    samplingRate: int = Field(..., description="Sample rate in Hz")
    audioDuration: Optional[float] = Field(None, description="Actual audio duration in seconds")

class TTSInferenceResponse(BaseModel):
    """TTS inference response model."""
    audio: List[AudioOutput] = Field(..., description="List of generated audio outputs")
    config: Optional[AudioConfig] = Field(None, description="Response configuration metadata")

class VoiceMetadata(BaseModel):
    """Voice metadata for voice listing."""
    voiceId: str = Field(..., description="Unique voice identifier")
    name: str = Field(..., description="Voice name")
    language: str = Field(..., description="Language code")
    gender: str = Field(..., description="Voice gender")
    age: str = Field(..., description="Voice age group")
    isActive: bool = Field(..., description="Whether voice is active")

class VoiceListResponse(BaseModel):
    """Response model for voice listing."""
    voices: List[VoiceMetadata] = Field(..., description="List of available voices")
    totalCount: int = Field(..., description="Total number of voices")
    page: int = Field(default=1, description="Current page number")
    pageSize: int = Field(default=50, description="Number of voices per page")



# Pydantic models for OCR endpoints

class OCRLanguageConfig(BaseModel):

    """Language configuration for OCR."""



    sourceLanguage: str = Field(

        ..., description="Source language code (e.g., 'en', 'hi', 'ta')"

    )





class OCRImageInput(BaseModel):

    """Image input for OCR processing."""



    imageContent: Optional[str] = Field(

        None, description="Base64 encoded image content"

    )

    imageUri: Optional[str] = Field(

        None, description="URI to image file (will be downloaded and encoded)"

    )





class OCRInferenceConfig(BaseModel):

    """Configuration for OCR inference."""



    serviceId: Optional[str] = Field(
        None,
        description="OCR service/model ID (optional; Smart Router will assign if omitted)",
    )

    language: OCRLanguageConfig = Field(..., description="Language configuration")

    textDetection: Optional[bool] = Field(

        False,

        description=(

            "Whether to enable advanced text detection (bounding boxes, lines, etc.)."

        ),

    )





class OCRInferenceRequest(BaseModel):

    """OCR inference request model."""



    image: List[OCRImageInput] = Field(

        ..., description="List of images to process", min_items=1

    )

    config: OCRInferenceConfig = Field(..., description="Inference configuration")





class OCRTextOutput(BaseModel):

    """OCR text output for a single image."""



    source: str = Field(..., description="Extracted text from the image")

    target: str = Field("", description="Reserved for future use")





class OCRInferenceResponse(BaseModel):

    """OCR inference response model."""



    output: List[OCRTextOutput] = Field(

        ..., description="List of OCR results (one per image input)"

    )

    config: Optional[Dict[str, Any]] = Field(

        None, description="Response configuration metadata"

    )


# Pydantic models for NER endpoints

class NERLanguageConfig(BaseModel):
    """Language configuration for NER."""
    sourceLanguage: str = Field(
        ..., description="Source language code (e.g., 'en', 'hi', 'ta')"
    )


class NERTextInput(BaseModel):
    """Text input for NER processing."""
    source: str = Field(..., description="Input text to analyze for entities")


class NERInferenceConfig(BaseModel):
    """Configuration for NER inference."""
    serviceId: Optional[str] = Field(
        None, description="NER service/model ID (optional; Smart Router will assign if omitted)"
    )
    language: NERLanguageConfig = Field(..., description="Language configuration")


class NERInferenceRequest(BaseModel):
    """NER inference request model."""
    input: List[NERTextInput] = Field(
        ..., description="List of texts to process", min_items=1
    )
    config: NERInferenceConfig = Field(
        ..., description="Configuration for NER inference"
    )
    controlConfig: Optional[Dict[str, Any]] = Field(
        None, description="Additional control parameters"
    )


class NERTokenPrediction(BaseModel):
    """Token-level NER prediction."""
    token: Optional[str] = Field(None, description="Token text")
    tag: str = Field(..., description="NER tag (e.g., PERSON, ORG, O)")
    tokenIndex: Optional[int] = Field(
        None, description="Index of token within the input text"
    )
    tokenStartIndex: int = Field(
        ..., description="Character start index of token in the input text"
    )
    tokenEndIndex: int = Field(
        ..., description="Character end index of token in the input text"
    )


class NERPrediction(BaseModel):
    """NER prediction for a single input text."""
    source: Optional[str] = Field(None, description="Original source text")
    nerPrediction: List[NERTokenPrediction] = Field(
        ..., description="List of token-level predictions"
    )


class NERInferenceResponse(BaseModel):
    """NER inference response model."""
    taskType: str = Field("ner", description="Type of task (always 'ner')")
    output: List[NERPrediction] = Field(
        ..., description="List of NER predictions (one per input text)"
    )
    config: Optional[Dict[str, Any]] = Field(
        None, description="Response configuration metadata"
    )





class StreamingInfo(BaseModel):
    """Streaming service information."""
    endpoint: str = Field(..., description="WebSocket endpoint URL")
    supported_formats: List[str] = Field(..., description="Supported audio formats")
    max_connections: int = Field(..., description="Maximum concurrent connections")
    response_frequency_ms: int = Field(..., description="Response frequency in milliseconds")

# Pydantic models for Transliteration endpoints

class TransliterationLanguagePair(BaseModel):
    """Language pair configuration for transliteration."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi', 'ta')")
    targetLanguage: str = Field(..., description="Target language code")
    sourceScriptCode: Optional[str] = Field(None, description="Script code for source (e.g., 'Deva', 'Arab')")
    targetScriptCode: Optional[str] = Field(None, description="Script code for target")


class TransliterationTextInput(BaseModel):
    """Text input for transliteration."""
    source: str = Field(..., description="Input text to transliterate")


class TransliterationInferenceConfig(BaseModel):
    """Transliteration inference configuration."""
    serviceId: Optional[str] = Field(
        None,
        description="Identifier for transliteration service/model (optional; Smart Router will assign if omitted)",
    )
    language: TransliterationLanguagePair = Field(..., description="Language pair configuration")
    isSentence: bool = Field(True, description="True for sentence-level, False for word-level transliteration")
    numSuggestions: int = Field(
        0,
        description="Number of top-k suggestions (0 for best, >0 for word-level only, max 10)",
    )


class TransliterationInferenceRequest(BaseModel):
    """Transliteration inference request."""
    input: List[TransliterationTextInput] = Field(
        ...,
        description="List of text inputs to transliterate",
        min_items=1,
        max_items=100,
    )
    config: TransliterationInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional control parameters (optional)",
    )


# Pydantic models for Language Detection endpoints

class LanguageDetectionTextInput(BaseModel):
    """Text input for language detection."""
    source: str = Field(..., description="Input text to detect language")


class LanguageDetectionInferenceConfig(BaseModel):
    """Configuration for language detection inference."""
    serviceId: Optional[str] = Field(
        None,
        description="Language detection service/model ID (optional; Smart Router will assign if omitted)",
    )


class LanguageDetectionInferenceRequest(BaseModel):
    """Request model for language detection inference."""
    input: List[LanguageDetectionTextInput] = Field(
        ...,
        description="List of text inputs to detect language",
        min_items=1,
    )
    config: LanguageDetectionInferenceConfig = Field(
        ...,
        description="Configuration for inference",
    )
    controlConfig: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional control parameters (optional)",
    )

# Pydantic models for Speaker Diarization endpoints
class SpeakerDiarizationControlConfig(BaseModel):
    """Control configuration for speaker diarization."""
    dataTracking: Optional[bool] = Field(True, description="Whether to enable data tracking")

class SpeakerDiarizationConfig(BaseModel):
    """Configuration for speaker diarization inference."""
    serviceId: Optional[str] = Field(
        None,
        description="Identifier for speaker diarization service/model (optional; Smart Router will assign if omitted)",
    )

class SpeakerDiarizationAudioInput(BaseModel):
    """Audio input for speaker diarization."""
    audioContent: Optional[str] = Field(None, description="Base64 encoded audio content")
    audioUri: Optional[str] = Field(None, description="URL from which the audio can be downloaded")

class SpeakerDiarizationInferenceRequest(BaseModel):
    """Speaker diarization inference request model."""
    controlConfig: Optional[SpeakerDiarizationControlConfig] = Field(None, description="Control configuration parameters")
    config: SpeakerDiarizationConfig = Field(..., description="Configuration for speaker diarization inference")
    audio: List[SpeakerDiarizationAudioInput] = Field(..., description="List of audio inputs to process", min_items=1)

class SpeakerDiarizationSegment(BaseModel):
    """A single speaker segment in the audio."""
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    speaker: str = Field(..., description="Speaker identifier (e.g., SPEAKER_00)")

class SpeakerDiarizationOutput(BaseModel):
    """Output for a single audio input."""
    total_segments: int = Field(..., description="Total number of segments")
    num_speakers: int = Field(..., description="Number of speakers detected")
    speakers: List[str] = Field(..., description="List of speaker identifiers")
    segments: List[SpeakerDiarizationSegment] = Field(..., description="List of speaker segments")

class SpeakerDiarizationResponseConfig(BaseModel):
    """Response configuration metadata."""
    serviceId: str = Field(..., description="Service identifier")
    language: Optional[str] = Field(None, description="Language code (if applicable)")

class SpeakerDiarizationInferenceResponse(BaseModel):
    """Speaker diarization inference response model."""
    taskType: str = Field(default="speaker-diarization", description="Task type identifier")
    output: List[SpeakerDiarizationOutput] = Field(..., description="List of speaker diarization results (one per audio input)")
    config: Optional[SpeakerDiarizationResponseConfig] = Field(None, description="Response configuration metadata")

# Pydantic models for Language Diarization endpoints
class LanguageDiarizationControlConfig(BaseModel):
    """Control configuration for language diarization."""
    dataTracking: Optional[bool] = Field(True, description="Whether to enable data tracking")

class LanguageDiarizationConfig(BaseModel):
    """Configuration for language diarization inference."""
    serviceId: Optional[str] = Field(
        None,
        description="Identifier for language diarization service/model (optional; Smart Router will assign if omitted)",
    )

class LanguageDiarizationAudioInput(BaseModel):
    """Audio input for language diarization."""
    audioContent: Optional[str] = Field(None, description="Base64 encoded audio content")
    audioUri: Optional[str] = Field(None, description="URL from which the audio can be downloaded")

class LanguageDiarizationInferenceRequest(BaseModel):
    """Language diarization inference request model."""
    controlConfig: Optional[LanguageDiarizationControlConfig] = Field(None, description="Control configuration parameters")
    config: LanguageDiarizationConfig = Field(..., description="Configuration for language diarization inference")
    audio: List[LanguageDiarizationAudioInput] = Field(..., description="List of audio inputs to process", min_items=1)

class LanguageDiarizationSegment(BaseModel):
    """A single language segment in the audio."""
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    language: str = Field(..., description="Language code with name (e.g., 'hi: Hindi')")
    confidence: float = Field(..., description="Confidence score for the language detection")

class LanguageDiarizationOutput(BaseModel):
    """Output for a single audio input."""
    total_segments: int = Field(..., description="Total number of segments")
    segments: List[LanguageDiarizationSegment] = Field(..., description="List of language segments")
    target_language: str = Field(..., description="Target language code (empty string for all languages)")

class LanguageDiarizationResponseConfig(BaseModel):
    """Response configuration metadata."""
    serviceId: str = Field(..., description="Service identifier")

class LanguageDiarizationInferenceResponse(BaseModel):
    """Language diarization inference response model."""
    taskType: str = Field(default="language-diarization", description="Task type identifier")
    output: List[LanguageDiarizationOutput] = Field(..., description="List of language diarization results (one per audio input)")
    config: Optional[LanguageDiarizationResponseConfig] = Field(None, description="Response configuration metadata")

# Pydantic models for Audio Language Detection endpoints
class AudioLangDetectionControlConfig(BaseModel):
    """Control configuration for audio language detection."""
    dataTracking: Optional[bool] = Field(True, description="Whether to enable data tracking")

class AudioLangDetectionConfig(BaseModel):
    """Configuration for audio language detection inference."""
    serviceId: Optional[str] = Field(
        None,
        description="Identifier for audio language detection service/model (optional; Smart Router will assign if omitted)",
    )

class AudioLangDetectionAudioInput(BaseModel):
    """Audio input for audio language detection."""
    audioContent: Optional[str] = Field(None, description="Base64 encoded audio content")
    audioUri: Optional[str] = Field(None, description="URL from which the audio can be downloaded")

class AudioLangDetectionInferenceRequest(BaseModel):
    """Audio language detection inference request model."""
    controlConfig: Optional[AudioLangDetectionControlConfig] = Field(None, description="Control configuration parameters")
    config: AudioLangDetectionConfig = Field(..., description="Configuration for audio language detection inference")
    audio: List[AudioLangDetectionAudioInput] = Field(..., description="List of audio inputs to process", min_items=1)

class AudioLangDetectionAllScores(BaseModel):
    """All scores from language detection model."""
    predicted_language: str = Field(..., description="Predicted language code with name")
    confidence: float = Field(..., description="Confidence score")
    top_scores: List[float] = Field(..., description="Top confidence scores")

class AudioLangDetectionOutput(BaseModel):
    """Output for a single audio input."""
    language_code: str = Field(..., description="Detected language code with name (e.g., 'ta: Tamil')")
    confidence: float = Field(..., description="Confidence score for the detected language")
    all_scores: AudioLangDetectionAllScores = Field(..., description="All scores from the detection model")

class AudioLangDetectionResponseConfig(BaseModel):
    """Response configuration metadata."""
    serviceId: str = Field(..., description="Service identifier")

class AudioLangDetectionInferenceResponse(BaseModel):
    """Audio language detection inference response model."""
    taskType: str = Field(default="audio-lang-detection", description="Task type identifier")
    output: List[AudioLangDetectionOutput] = Field(..., description="List of audio language detection results (one per audio input)")
    config: Optional[AudioLangDetectionResponseConfig] = Field(None, description="Response configuration metadata")

class TryItRequest(BaseModel):
    """Try-It request wrapper for anonymous access."""
    service_name: str = Field(..., description="Target service name for Try-It (e.g., 'nmt')")
    payload: Dict[str, Any] = Field(..., description="Service request payload")

class StreamingInfo(BaseModel):
    """Streaming service information."""
    endpoint: str = Field(..., description="WebSocket endpoint URL")
    supported_formats: List[str] = Field(..., description="Supported audio formats")
    max_connections: int = Field(..., description="Maximum concurrent connections")
    response_frequency_ms: int = Field(..., description="Response frequency in milliseconds")

# Pydantic models for Pipeline endpoints
class PipelineTaskType(str, Enum):
    """Pipeline task types."""
    ASR = "asr"
    TRANSLATION = "translation"
    TTS = "tts"
    TRANSLITERATION = "transliteration"

class PipelineLanguageConfig(BaseModel):
    """Language configuration for pipeline tasks."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi', 'ta')")
    targetLanguage: Optional[str] = Field(None, description="Target language code (for translation)")
    sourceScriptCode: Optional[str] = Field(None, description="Script code if applicable")
    targetScriptCode: Optional[str] = Field(None, description="Target script code")

class PipelineTaskConfig(BaseModel):
    """Configuration for a pipeline task."""
    serviceId: str = Field(..., description="Identifier for the AI service/model")
    language: PipelineLanguageConfig = Field(..., description="Language configuration")
    audioFormat: Optional[str] = Field(None, description="Audio format")
    preProcessors: Optional[List[str]] = Field(None, description="Preprocessors")
    postProcessors: Optional[List[str]] = Field(None, description="Postprocessors")
    transcriptionFormat: Optional[str] = Field("transcript", description="Transcription format")
    gender: Optional[str] = Field(None, description="Voice gender (male/female)")
    additionalParams: Optional[Dict[str, Any]] = Field(None, description="Additional parameters")

class PipelineTask(BaseModel):
    """Configuration for a pipeline task."""
    taskType: PipelineTaskType = Field(..., description="Type of task to execute")
    config: PipelineTaskConfig = Field(..., description="Configuration for the task")

class PipelineInferenceRequest(BaseModel):
    """Main pipeline inference request model."""
    pipelineTasks: List[PipelineTask] = Field(..., description="List of tasks to execute in sequence", min_items=1)
    inputData: Dict[str, Any] = Field(..., description="Initial input data (audio for ASR-first pipelines)")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

class PipelineTaskOutput(BaseModel):
    """Output from a pipeline task."""
    taskType: str = Field(..., description="Type of task that produced this output")
    serviceId: str = Field(..., description="Service ID used for this task")
    output: Any = Field(..., description="Task output (structure varies by task type)")
    config: Optional[Dict[str, Any]] = Field(None, description="Response configuration")

class PipelineInferenceResponse(BaseModel):
    """Main pipeline inference response model."""
    pipelineResponse: List[PipelineTaskOutput] = Field(..., description="Outputs from each pipeline task")

class PipelineInfo(BaseModel):
    """Pipeline service information."""
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    description: str = Field(..., description="Service description")
    supported_task_types: List[str] = Field(..., description="Supported task types")
    example_pipelines: Dict[str, Any] = Field(..., description="Example pipeline configurations")
    task_sequence_rules: Dict[str, List[str]] = Field(..., description="Task sequence rules")

# Pydantic models for Feature Flag endpoints
class FeatureFlagEvaluationRequest(BaseModel):
    """Request model for feature flag evaluation"""
    flag_name: str = Field(..., description="Feature flag identifier", min_length=1)
    user_id: Optional[str] = Field(None, description="User identifier for targeting")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context attributes")
    default_value: Union[bool, str, int, float, dict] = Field(..., description="Fallback value if flag evaluation fails")
    environment: Optional[str] = Field(None, description="Environment name (development|staging|production).")

class BulkEvaluationRequest(BaseModel):
    """Request model for bulk feature flag evaluation"""
    flag_names: List[str] = Field(..., description="List of flag names to evaluate", min_items=1)
    user_id: Optional[str] = Field(None, description="User identifier for targeting")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context attributes")
    environment: Optional[str] = Field(None, description="Environment name (development|staging|production).")

class FeatureFlagEvaluationResponse(BaseModel):
    """Response model for feature flag evaluation"""
    flag_name: str
    value: Union[bool, str, int, float, dict]
    variant: Optional[str] = None
    reason: str = Field(..., description="Evaluation reason (TARGETING_MATCH, DEFAULT, ERROR)")
    evaluated_at: str

class FeatureFlagResponse(BaseModel):
    """Response model for feature flag details"""
    name: str
    description: Optional[str] = None
    is_enabled: bool
    environment: str
    rollout_percentage: Optional[str] = None
    target_users: Optional[List[str]] = None
    unleash_flag_name: Optional[str] = None
    last_synced_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class FeatureFlagListResponse(BaseModel):
    """Response model for feature flag list"""
    items: List[FeatureFlagResponse]
    total: int
    limit: int
    offset: int

class BooleanEvaluationResponse(BaseModel):
    """Response model for boolean feature flag evaluation"""
    flag_name: str
    value: bool
    reason: str

class BulkEvaluationResponse(BaseModel):
    """Response model for bulk feature flag evaluation"""
    results: Dict[str, Dict[str, Any]]

class SyncResponse(BaseModel):
    """Response model for feature flag sync"""
    synced_count: int
    environment: str

# Pydantic models for Model Management endpoints
class ModelProcessingType(BaseModel):
    """Model processing type."""
    type: str = Field(..., description="Processing type")

class Schema(BaseModel):
    """Schema for inference endpoint."""
    modelProcessingType: ModelProcessingType = Field(..., description="Model processing type")
    request: Dict[str, Any] = Field(default_factory=dict, description="Request schema")
    response: Dict[str, Any] = Field(default_factory=dict, description="Response schema")

class InferenceEndPoint(BaseModel):
    """Inference endpoint configuration."""
    schema: Schema = Field(..., description="Endpoint schema")

class Score(BaseModel):
    """Benchmark score."""
    metricName: str = Field(..., description="Metric name")
    score: str = Field(..., description="Score value")

class BenchmarkLanguage(BaseModel):
    """Benchmark language configuration."""
    sourceLanguage: Optional[str] = Field(None, description="Source language code")
    targetLanguage: Optional[str] = Field(None, description="Target language code")

class Benchmark(BaseModel):
    """Benchmark information."""
    benchmarkId: str = Field(..., description="Benchmark identifier")
    name: str = Field(..., description="Benchmark name")
    description: str = Field(..., description="Benchmark description")
    domain: str = Field(..., description="Domain")
    createdOn: datetime = Field(..., description="Creation timestamp")
    languages: BenchmarkLanguage = Field(..., description="Language configuration")
    score: List[Score] = Field(..., description="List of scores")

class OAuthId(BaseModel):
    """OAuth identifier."""
    oauthId: str = Field(..., description="OAuth ID")
    provider: str = Field(..., description="OAuth provider")

class TeamMember(BaseModel):
    """Team member information."""
    name: str = Field(..., description="Member name")
    aboutMe: Optional[str] = Field(None, description="About member")
    oauthId: Optional[OAuthId] = Field(None, description="OAuth identifier")

class Submitter(BaseModel):
    """Submitter information."""
    name: str = Field(..., description="Submitter name")
    aboutMe: Optional[str] = Field(None, description="About submitter")
    team: List[TeamMember] = Field(..., description="Team members")

class Task(BaseModel):
    """Task type."""
    type: str = Field(..., description="Task type")

# Pydantic models for Smart Model Router / Policy Engine integration


# Policy Enums (matching policy-engine models)
class LatencyPolicy(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class CostPolicy(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"

class AccuracyPolicy(str, Enum):
    SENSITIVE = "sensitive"
    STANDARD = "standard"


class SMRPolicyInput(BaseModel):
    """Optional policy overrides for Smart Model Router."""

    latency: Optional[str] = Field(
        None, description="Desired latency profile (low, medium, high)"
    )
    cost: Optional[str] = Field(
        None, description="Desired cost profile (tier_1, tier_2, tier_3)"
    )
    accuracy: Optional[str] = Field(
        None, description="Desired accuracy profile (sensitive, standard)"
    )


class SMRInferenceRequest(BaseModel):
    """
    Generic Smart Model Routing request.

    - Client sends original inference request body without serviceId.
    - Gateway calls Policy Engine for latency/cost/accuracy policy.
    - Gateway queries Model Management and deterministically selects a serviceId.
    - Gateway injects serviceId into config.serviceId and forwards the inference call.
    """

    task_type: "ModelTaskTypeEnum" = Field(
        ...,
        description="Task type to route for (asr, nmt, tts, llm, ocr, transliteration, etc.)",
    )
    request_body: Dict[str, Any] = Field(
        ..., description="Original inference request body (without serviceId)"
    )
    tenant_id: Optional[str] = Field(
        None, description="Tenant identifier used for policy lookup"
    )
    user_id: Optional[str] = Field(
        None, description="User identifier used for policy evaluation"
    )
    language: Optional[str] = Field(
        None,
        description="Preferred language code for routing (used to prefer matching benchmarks when available)",
    )
    policy: Optional[SMRPolicyInput] = Field(
        None, description="Optional policy overrides for latency/cost/accuracy"
    )
    service_id: Optional[str] = Field(
        None,
        description="Explicit service ID. If provided, router will skip selection and use this directly.",
    )


class SMRSelectedService(BaseModel):
    """Details of the selected service used for routing (for observability/debugging)."""

    service_id: str = Field(..., description="Selected service identifier")
    model_id: Optional[str] = Field(None, description="Associated model identifier")
    name: Optional[str] = Field(None, description="Service name")
    task_type: Optional["ModelTaskTypeEnum"] = Field(
        None, description="Task type of the selected service"
    )
    policy_id: Optional[str] = Field(
        None, description="Policy ID returned by policy-engine"
    )
    policy_version: Optional[str] = Field(
        None, description="Policy version returned by policy-engine"
    )


# pydantic models for model management

class ModelTaskTypeEnum(str, Enum):
    
    nmt = "nmt"
    tts = "tts"
    asr = "asr"
    llm = "llm"
    transliteration = "transliteration"
    language_detection = "language-detection"
    speaker_diarization = "speaker-diarization"
    audio_lang_detection = "audio-lang-detection"
    language_diarization = "language-diarization"
    ocr = "ocr"
    ner = "ner"


# Resolve forward references for SMR models that reference ModelTaskTypeEnum
SMRInferenceRequest.model_rebuild()
SMRSelectedService.model_rebuild()

class VersionStatus(str, Enum):
    """Model version status."""
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"

class LicenseEnum(str, Enum):
    """Enumeration of valid license types for models."""
    # Permissive Licenses
    MIT = "MIT"
    APACHE_2_0 = "Apache-2.0"
    BSD_2_CLAUSE = "BSD-2-Clause"
    BSD_3_CLAUSE = "BSD-3-Clause"
    ISC = "ISC"
    UNLICENSE = "Unlicense"
    ZLIB = "Zlib"
    
    # Copyleft Licenses
    GPL_2_0 = "GPL-2.0"
    GPL_3_0 = "GPL-3.0"
    LGPL_2_1 = "LGPL-2.1"
    LGPL_3_0 = "LGPL-3.0"
    AGPL_3_0 = "AGPL-3.0"
    MPL_2_0 = "MPL-2.0"
    EPL_2_0 = "EPL-2.0"
    CDDL_1_0 = "CDDL-1.0"
    
    # Microsoft Licenses
    MS_PL = "Ms-PL"
    MS_RL = "Ms-RL"
    
    # Creative Commons Licenses
    CC0_1_0 = "CC0-1.0"
    CC_BY_4_0 = "CC-BY-4.0"
    CC_BY_SA_4_0 = "CC-BY-SA-4.0"
    CC_BY_NC_4_0 = "CC-BY-NC-4.0"
    CC_BY_NC_SA_4_0 = "CC-BY-NC-SA-4.0"
    CC_BY_ND_4_0 = "CC-BY-ND-4.0"
    CC_BY_NC_ND_4_0 = "CC-BY-NC-ND-4.0"
    
    # AI/ML Specific Licenses
    OPENRAIL_M = "OpenRAIL-M"
    OPENRAIL_S = "OpenRAIL-S"
    BIGSCIENCE_OPENRAIL_M = "BigScience-OpenRAIL-M"
    CREATIVEML_OPENRAIL_M = "CreativeML-OpenRAIL-M"
    APACHE_2_0_WITH_LLM_EXCEPTION = "Apache-2.0-with-LLM-exception"
    
    # Academic/Research Licenses
    ACADEMIC_FREE_LICENSE_3_0 = "AFL-3.0"
    
    # Other Common Licenses
    ARTISTIC_LICENSE_2_0 = "Artistic-2.0"
    ECLIPSE_PUBLIC_LICENSE_1_0 = "EPL-1.0"
    
    # Special Categories
    PROPRIETARY = "Proprietary"
    CUSTOM = "Custom"
    OTHER = "Other"

class ModelCreateRequest(BaseModel):
    """Request model for creating a new model. Model ID is auto-generated as a hash of (name, version)."""
    version: str = Field(..., description="Model version")
    submittedOn: Optional[int] = Field(None, description="Submission timestamp (auto-generated by backend if not provided)")
    updatedOn: Optional[int] = Field(None, description="Last update timestamp")
    name: str = Field(..., description="Model name")
    description: str = Field(..., description="Model description")
    refUrl: str = Field(..., description="Reference URL")
    task: Task = Field(..., description="Task type")
    languages: List[Dict[str, Any]] = Field(..., description="Supported languages")
    license: str = Field(..., description="License information")
    domain: List[str] = Field(..., description="Domain list")
    inferenceEndPoint: InferenceEndPoint = Field(..., description="Inference endpoint configuration")
    benchmarks: List[Benchmark] = Field(..., description="List of benchmarks")
    submitter: Submitter = Field(..., description="Submitter information")

    @field_validator("name")
    def validate_name(cls, v):
        """Validate model name format: only alphanumeric, hyphen, and forward slash allowed."""
        if not v:
            raise ValueError("Model name is required")
        
        # Pattern: alphanumeric, hyphen, and forward slash only
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Model name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). "
                f"Example: 'ai4bharath/indictrans-gpu'. Got: '{v}'"
            )
        return v

    @field_validator("license", mode="before")
    def validate_license(cls, v):
        if not v:
            raise ValueError("License field is required")
        
        if isinstance(v, str):
            v_normalized = v.strip()
            # Check if the license matches any enum value (case-insensitive)
            for enum_member in LicenseEnum:
                if enum_member.value.lower() == v_normalized.lower():
                    return enum_member.value
            
            # If no match found, raise error with valid options
            valid_licenses = [e.value for e in LicenseEnum]
            raise ValueError(
                f"Invalid license '{v}'. Valid licenses are: {', '.join(valid_licenses)}"
            )
        
        if isinstance(v, LicenseEnum):
            return v.value
        
        return v

class ModelUpdateRequest(BaseModel):
    """Request model for updating an existing model."""
    modelId: str = Field(..., description="Unique model identifier")
    version: Optional[str] = Field(None, description="Model version")
    versionStatus: Optional[VersionStatus] = Field(None, description="Version status (ACTIVE or DEPRECATED)")
    submittedOn: Optional[int] = Field(None, description="Submission timestamp")
    updatedOn: Optional[int] = Field(None, description="Last update timestamp")
    name: Optional[str] = Field(None, description="Model name")
    description: Optional[str] = Field(None, description="Model description")
    refUrl: Optional[str] = Field(None, description="Reference URL")
    task: Optional[Task] = Field(None, description="Task type")
    languages: Optional[List[Dict[str, Any]]] = Field(None, description="Supported languages")
    license: Optional[str] = Field(None, description="License information")
    domain: Optional[List[str]] = Field(None, description="Domain list")
    inferenceEndPoint: Optional[InferenceEndPoint] = Field(None, description="Inference endpoint configuration")
    benchmarks: Optional[List[Benchmark]] = Field(None, description="List of benchmarks")
    submitter: Optional[Submitter] = Field(None, description="Submitter information")

    @field_validator("name")
    def validate_name(cls, v):
        """Validate model name format: only alphanumeric, hyphen, and forward slash allowed."""
        # Allow None for optional field in updates
        if v is None:
            return v
        
        # Pattern: alphanumeric, hyphen, and forward slash only
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Model name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). "
                f"Example: 'ai4bharath/indictrans-gpu'. Got: '{v}'"
            )
        return v

    @field_validator("license", mode="before")
    def validate_license(cls, v):
        # Allow None for optional field in updates
        if v is None:
            return v
        
        if isinstance(v, str):
            v_normalized = v.strip()
            # Check if the license matches any enum value (case-insensitive)
            for enum_member in LicenseEnum:
                if enum_member.value.lower() == v_normalized.lower():
                    return enum_member.value
            
            # If no match found, raise error with valid options
            valid_licenses = [e.value for e in LicenseEnum]
            raise ValueError(
                f"Invalid license '{v}'. Valid licenses are: {', '.join(valid_licenses)}"
            )
        
        if isinstance(v, LicenseEnum):
            return v.value
        
        return v

class ModelViewRequest(BaseModel):
    """Request model for viewing a model."""
    modelId: str = Field(..., description="Unique model identifier")
    version: Optional[str] = Field(None, description="Optional version to get specific version")

class ModelViewRequestWithVersion(BaseModel):
    """Request body for getting a model with optional version."""
    version: Optional[str] = Field(None, description="Optional version to get specific version")

class ModelViewResponse(BaseModel):
    """Response model for model view."""
    modelId: str = Field(..., description="Unique model identifier")
    uuid: str = Field(..., description="Model UUID")
    name: str = Field(..., description="Model name")
    description: str = Field(..., description="Model description")
    languages: List[Dict[str, Any]] = Field(..., description="Supported languages")
    domain: List[str] = Field(..., description="Domain list")
    submitter: Submitter = Field(..., description="Submitter information")
    license: str = Field(..., description="License information")
    inferenceEndPoint: InferenceEndPoint = Field(..., description="Inference endpoint configuration")
    source: Optional[str] = Field(None, description="Source information")
    task: Task = Field(..., description="Task type")
    isPublished: bool = Field(..., description="Publication status")
    publishedAt: Optional[str] = Field(None, description="Publication timestamp")
    unpublishedAt: Optional[str] = Field(None, description="Unpublication timestamp")

class BenchmarkEntry(BaseModel):
    """Benchmark entry for service."""
    output_length: int = Field(..., description="Output length")
    generated: int = Field(..., description="Generated count")
    actual: int = Field(..., description="Actual count")
    throughput: int = Field(..., description="Throughput")
    p50: int = Field(..., alias="50%", serialization_alias="50%", description="50th percentile")
    p99: int = Field(..., alias="99%", serialization_alias="99%", description="99th percentile")
    language: str = Field(..., description="Language code")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "output_length": 100,
                "generated": 50,
                "actual": 50,
                "throughput": 1000,
                "50%": 10,
                "99%": 20,
                "language": "en"
            }
        }

class ServiceStatus(BaseModel):
    """Service health status."""
    status: str = Field(..., description="Status (e.g., healthy, unhealthy)")
    lastUpdated: str = Field(..., description="Last update timestamp")

class ModelManagementServiceCreateRequest(BaseModel):
    """Request model for creating a new service in model management.
    Note: serviceId is auto-generated as hash of (model_name, model_version, service_name)."""
    name: str = Field(..., description="Service name")
    serviceDescription: str = Field(..., description="Service description")
    hardwareDescription: str = Field(..., description="Hardware description")
    publishedOn: Optional[int] = Field(None, description="Publication timestamp (auto-generated if not provided)")
    modelId: str = Field(..., description="Associated model identifier")
    modelVersion: str = Field(..., description="Model version")
    endpoint: str = Field(..., description="Service endpoint URL")
    api_key: str = Field(..., description="API key for the service")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")
    isPublished: Optional[bool] = Field(False, description="Whether the service is published (defaults to false)")

    @field_validator("name")
    def validate_name(cls, v):
        """Validate service name format: only alphanumeric, hyphen, and forward slash allowed."""
        if not v:
            raise ValueError("Service name is required")
        
        # Pattern: alphanumeric, hyphen, and forward slash only
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Service name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). "
                f"Example: 'ai4bharath/indictrans-gpu'. Got: '{v}'"
            )
        return v

class LanguagePair(BaseModel):
    """Language pair configuration."""
    sourceLanguage: Optional[str] = Field(None, description="Source language code")
    sourceScriptCode: Optional[str] = Field("", description="Source script code")
    targetLanguage: str = Field(..., description="Target language code")
    targetScriptCode: Optional[str] = Field("", description="Target script code")

class ModelManagementServiceUpdateRequest(BaseModel):
    """Request model for updating an existing service in model management. 
    Only serviceId is required for identification. name, modelId, and modelVersion are NOT updatable 
    since service_id is derived from them."""
    serviceId: str = Field(..., description="Unique service identifier (used for identification, not updatable)")
    serviceDescription: Optional[str] = Field(None, description="Service description")
    hardwareDescription: Optional[str] = Field(None, description="Hardware description")
    publishedOn: Optional[int] = Field(None, description="Publication timestamp")
    endpoint: Optional[str] = Field(None, description="Service endpoint URL")
    api_key: Optional[str] = Field(None, description="API key for the service")
    languagePair: Optional[LanguagePair] = Field(None, description="Language pair configuration")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")
    isPublished: Optional[bool] = Field(None, description="Set to true to publish, false to unpublish the service")

class ServiceViewRequest(BaseModel):
    """Request model for viewing a service."""
    serviceId: str = Field(..., description="Unique service identifier")

class ServiceHeartbeatRequest(BaseModel):
    """Request model for service health heartbeat."""
    serviceId: str = Field(..., description="Unique service identifier")
    status: str = Field(..., description="Health status")

class ServiceResponse(BaseModel):
    """Base service response model."""
    serviceId: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Service name")
    serviceDescription: str = Field(..., description="Service description")
    hardwareDescription: str = Field(..., description="Hardware description")
    publishedOn: int = Field(..., description="Publication timestamp")
    modelId: str = Field(..., description="Associated model identifier")
    endpoint: Optional[str] = Field(None, description="Service endpoint URL")
    api_key: Optional[str] = Field(None, description="API key for the service")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")

class ServiceViewResponse(BaseModel):
    """Response model for service view."""
    serviceId: str = Field(..., description="Unique service identifier")
    uuid: str = Field(..., description="Service UUID")
    name: str = Field(..., description="Service name")
    serviceDescription: str = Field(..., description="Service description")
    hardwareDescription: str = Field(..., description="Hardware description")
    publishedOn: int = Field(..., description="Publication timestamp")
    modelId: str = Field(..., description="Associated model identifier")
    endpoint: Optional[str] = Field(None, description="Service endpoint URL")
    api_key: Optional[str] = Field(None, description="API key for the service")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")
    model: Optional[ModelCreateRequest] = Field(None, description="Associated model information")
    key_usage: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="API key usage")
    total_usage: int = Field(default=0, description="Total usage count")

class ServiceListResponse(BaseModel):
    """Response model for service list."""
    serviceId: str = Field(..., description="Unique service identifier")
    uuid: Optional[str] = Field(None, description="UUID of the service")
    name: str = Field(..., description="Service name")
    serviceDescription: Optional[str] = Field(None, description="Service description")
    hardwareDescription: Optional[str] = Field(None, description="Hardware description")
    publishedOn: Optional[int] = Field(None, description="Publication timestamp")
    modelId: str = Field(..., description="Associated model identifier")
    endpoint: Optional[str] = Field(None, description="Service endpoint URL")
    api_key: Optional[str] = Field(None, description="API key for the service")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")
    isPublished: bool = Field(False, description="Whether the service is published")
    publishedAt: Optional[str] = Field(None, description="Timestamp when service was published")
    unpublishedAt: Optional[str] = Field(None, description="Timestamp when service was unpublished")
    task: Optional[Task] = Field(None, description="Task type")
    languages: Optional[List[dict]] = Field(None, description="Supported languages")
    modelVersion: Optional[str] = Field(None, description="Model version associated with this service")
    versionStatus: Optional[str] = Field(None, description="Version status of the associated model (ACTIVE or DEPRECATED)")

# A/B Testing Experiment Models
class ExperimentVariantRequest(BaseModel):
    """Request model for creating/updating an experiment variant"""
    variant_name: str = Field(..., description="Name of the variant (e.g., 'control', 'variant-a')")
    service_id: str = Field(..., description="Service ID to use for this variant")
    traffic_percentage: int = Field(..., ge=0, le=100, description="Traffic percentage (0-100)")
    description: Optional[str] = Field(None, description="Optional description of the variant")

class ExperimentVariantResponse(BaseModel):
    """Response model for experiment variant"""
    id: str
    variant_name: str
    service_id: str
    traffic_percentage: int
    description: Optional[str] = None
    created_at: Union[str, datetime]
    updated_at: Union[str, datetime]

class ExperimentCreateRequest(BaseModel):
    """Request model for creating an experiment"""
    name: str = Field(..., min_length=1, max_length=255, description="Experiment name")
    description: Optional[str] = Field(None, description="Experiment description")
    task_type: Optional[List[str]] = Field(None, description="List of task types to filter (e.g., ['asr', 'tts'])")
    languages: Optional[List[str]] = Field(None, description="List of language codes to filter (e.g., ['hi', 'en'])")
    start_date: Optional[Union[datetime, str]] = Field(None, description="Experiment start date (optional, defaults to now)")
    end_date: Optional[Union[datetime, str]] = Field(None, description="Experiment end date (optional)")
    variants: List[ExperimentVariantRequest] = Field(..., min_items=2, description="At least 2 variants required")

class ExperimentUpdateRequest(BaseModel):
    """Request model for updating an experiment"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    start_date: Optional[Union[datetime, str]] = None
    end_date: Optional[Union[datetime, str]] = None
    variants: Optional[List[ExperimentVariantRequest]] = None

class ExperimentStatusUpdateRequest(BaseModel):
    """Request model for updating experiment status"""
    action: str = Field(..., description="Action to perform: 'start', 'stop', 'pause', 'resume', or 'cancel'")

class ExperimentResponse(BaseModel):
    """Response model for experiment"""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    task_type: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    start_date: Optional[Union[datetime, str]] = None
    end_date: Optional[Union[datetime, str]] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]
    started_at: Optional[Union[datetime, str]] = None
    completed_at: Optional[Union[datetime, str]] = None
    variants: List[ExperimentVariantResponse] = []

class ExperimentListResponse(BaseModel):
    """Response model for listing experiments"""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    task_type: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    start_date: Optional[Union[datetime, str]] = None
    end_date: Optional[Union[datetime, str]] = None
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]
    variant_count: int = 0

class ExperimentVariantSelectionRequest(BaseModel):
    """Request model for selecting a variant for a given request"""
    task_type: str = Field(..., description="Task type (e.g., 'asr', 'tts')")
    language: Optional[str] = Field(None, description="Language code (e.g., 'hi', 'en')")
    request_id: Optional[str] = Field(None, description="Optional request ID for consistent routing")
    user_id: Optional[str] = Field(None, description="Optional user ID so same user gets same variant")
    service_id: Optional[str] = Field(
        None,
        description="Optional service ID; when set, only experiments that include this service as a variant are considered"
    )

class ExperimentVariantSelectionResponse(BaseModel):
    """Response model for variant selection"""
    experiment_id: Optional[str] = None
    variant_id: Optional[str] = None
    variant_name: Optional[str] = None
    service_id: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    is_experiment: bool = False


class ExperimentMetricsResponse(BaseModel):
    """Response model for experiment metrics (per variant per day)"""
    experiment_id: str
    variant_id: str
    variant_name: str
    request_count: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: Optional[int] = None
    custom_metrics: Optional[Dict[str, Any]] = None
    metric_date: Union[datetime, str]


# Auth models (for API documentation)
class RegisterUser(BaseModel):
    email: str = Field(..., description="Email address")
    username: str = Field(..., min_length=3, max_length=100, description="Username (3-100 characters)")
    password: str = Field(..., min_length=8, max_length=100, description="Password (minimum 8 characters)")
    confirm_password: str = Field(..., min_length=8, max_length=100, description="Password confirmation (must match password)")
    full_name: Optional[str] = Field(None, description="Full name")
    phone_number: Optional[str] = Field(None, description="Phone number")
    timezone: Optional[str] = Field("UTC", description="Timezone")
    language: Optional[str] = Field("en", description="Language code")
    is_tenant: Optional[bool] = Field(False, description="Whether the user is registering as a tenant")

class LoginRequestBody(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="User password")
    remember_me: bool = Field(False, description="Issue long-lived refresh token")

class TokenRefreshBody(BaseModel):
    refresh_token: str = Field(..., description="Refresh token")

class LogoutBody(BaseModel):
    refresh_token: Optional[str] = Field(None, description="Refresh token to invalidate; if omitted, logs out all sessions")

class UpdateUserBody(BaseModel):
    full_name: Optional[str] = Field(None, description="Full name")
    phone_number: Optional[str] = Field(None, description="Phone number")
    timezone: Optional[str] = Field(None, description="Timezone (e.g., 'UTC')")
    language: Optional[str] = Field(None, description="Language code (e.g., 'en')")
    preferences: Optional[Dict[str, Any]] = Field(None, description="User preferences object")

class PasswordChangeBody(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password (minimum 8 characters)")
    confirm_password: str = Field(..., min_length=8, max_length=100, description="Confirm new password (must match new_password)")

class PasswordResetRequestBody(BaseModel):
    email: str = Field(..., description="Email address associated with the account")

class PasswordResetConfirmBody(BaseModel):
    token: str = Field(..., description="Password reset token received via email")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password (minimum 8 characters)")
    confirm_password: str = Field(..., min_length=8, max_length=100, description="Confirm new password (must match new_password)")

class OAuth2CallbackBody(BaseModel):
    code: str = Field(..., description="Authorization code returned by OAuth2 provider")
    state: str = Field(..., description="State parameter for CSRF protection (must match the state sent initially)")
    provider: str = Field(..., description="OAuth2 provider name (e.g., 'google', 'github')")

class APIKeyCreateBody(BaseModel):
    key_name: str = Field(..., min_length=1, max_length=100, description="Name/label for the API key")
    permissions: Optional[List[str]] = Field(default_factory=list, description="List of permissions for the API key (e.g., ['read:profile', 'update:profile'])")
    expires_days: Optional[int] = Field(None, ge=1, le=365, description="Number of days until the API key expires (1-365 days, optional)")
    userId: Optional[int] = Field(None, description="User ID for whom the API key is created (Admin only). If not provided, creates key for current user.")


class APIKeyUpdateBody(BaseModel):
    """Partial update body for an existing API key (name, permissions)."""
    key_name: Optional[str] = Field(None, min_length=1, max_length=100, description="New name/label for the API key")
    permissions: Optional[List[str]] = Field(
        None,
        description="New list of permissions for the API key (replaces existing permissions)",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Set to true to activate the key, or false to deactivate (soft revoke) the key",
    )

class APIKeySelectBody(BaseModel):
    api_key_id: int = Field(..., description="API key ID to mark as selected for the current user")

class AssignRoleBody(BaseModel):
    user_id: int = Field(..., description="ID of the user to assign role to")
    role_name: str = Field(..., description="Name of the role to assign (e.g., 'USER', 'ADMIN', 'MODERATOR', 'GUEST')")

class RemoveRoleBody(BaseModel):
    user_id: int = Field(..., description="ID of the user to remove role from")
    role_name: str = Field(..., description="Name of the role to remove")

# multi tenant pydantic models
class TenantStatus(str, Enum):
    """Tenant status enumeration."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"

class TenantUserStatus(str, Enum):
    """Tenant user status enumeration."""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"

class SubscriptionType(str, Enum):
    """Subscription type enumeration."""
    TTS = "tts"
    ASR = "asr"
    NMT = "nmt"
    LLM = "llm"
    PIPELINE = "pipeline"
    OCR = "ocr"
    NER = "ner"
    Speech_to_Speech_Pipeline = "speech_to_speech_pipeline"
    Transliteration = "transliteration"
    Langauage_detection = "language_detection"
    Speaker_diarization = "speaker_diarization"
    Language_diarization = "language_diarization"
    Audio_language_detection = "audio_language_detection"

class ServiceUnitType(str, Enum):
    """Service unit type enumeration."""
    CHARACTER = "character"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    REQUEST = "request"

class ServiceCurrencyType(str, Enum):
    """Service currency type enumeration."""
    INR = "INR"

class QuotaStructure(BaseModel):
    """Structure for quota limits"""
    characters_length: Optional[int] = Field(None, ge=0, description="Character length quota")
    audio_length_in_min: Optional[int] = Field(None, ge=0, description="Audio length quota in minutes")

class TenantRegisterRequest(BaseModel):
    """Request model for tenant registration."""
    organization_name: str = Field(..., min_length=2, max_length=255)
    domain: str = Field(..., min_length=3, max_length=255)
    contact_email: EmailStr = Field(..., description="Contact email for the tenant")
    phone_number: Optional[str] = Field(None, max_length=20, description="Contact phone number")
    requested_subscriptions: Optional[List[SubscriptionType]] = Field(default=[], description="List of requested service subscriptions, e.g. ['tts', 'asr']")
    requested_quotas: Optional[QuotaStructure] = Field(None, description="Requested quota limits for the tenant")
    usage_quota: Optional[QuotaStructure] = Field(None, description="Initial usage quota values")

class TenantRegisterResponse(BaseModel):
    """Response model for tenant registration."""
    id: UUID = Field(..., description="Tenant UUID")
    tenant_id: str = Field(..., description="Tenant identifier")
    subdomain: Optional[str] = Field(None, description="Tenant subdomain")
    schema_name: str = Field(..., description="Database schema name")
    subscriptions: List[str] = Field(..., description="List of active subscriptions")
    quotas: Dict[str, Any] = Field(..., description="Quota configuration")
    usage_quota: Optional[Dict[str, Any]] = Field(None, description="Usage quota values")
    status: str = Field(..., description="Tenant status")
    message: Optional[str] = Field(None, description="Additional message")

class UserRegisterRequest(BaseModel):
    """Request model for user registration."""
    tenant_id: str = Field(..., description="Tenant identifier", example="acme-corp-5d448a")
    email: EmailStr = Field(..., description="User email address")
    username: str = Field(..., min_length=3, max_length=100, description="Username")
    full_name: Optional[str] = Field(None, description="Full name of the user")
    phone_number: Optional[str] = Field(None, max_length=20, description="User phone number")
    services: List[str] = Field(..., description="List of services the user has access to", example=["tts", "asr"])
    is_approved: bool = Field(False, description="Indicates if the user is approved by tenant admin")
    role: Optional[str] = Field(
        None,
        description="Role for the user (key-value: {'role': 'USER'}). Allowed: ADMIN, USER, GUEST, MODERATOR.",
        example="USER",
    )

class UserRegisterResponse(BaseModel):
    """Response model for user registration."""
    user_id: int = Field(..., description="User ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="User email")
    services: List[str] = Field(..., description="List of services")
    schema: str = Field(..., description="Tenant schema name")
    created_at: datetime = Field(..., description="Creation timestamp")
    role: str = Field(..., description="Role for the user (key-value: {'role': 'USER'})")

class TenantStatusUpdateRequest(BaseModel):
    """Request model for updating tenant status."""
    tenant_id: str = Field(..., description="Tenant identifier")
    status: TenantStatus = Field(..., description="New tenant status")
    reason: Optional[str] = Field(None, description="Reason for status change (required if changing to SUSPENDED)")
    suspended_until: Optional[date] = Field(None, description="Optional suspension end date in ISO format (YYYY-MM-DD)")

class TenantStatusUpdateResponse(BaseModel):
    """Response model for tenant status update."""
    tenant_id: str = Field(..., description="Tenant identifier")
    old_status: TenantStatus = Field(..., description="Previous status")
    new_status: TenantStatus = Field(..., description="New status")

class TenantUserStatusUpdateRequest(BaseModel):
    """Request model for updating tenant user status."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="User ID")
    status: TenantUserStatus = Field(..., description="New user status")

class TenantUserStatusUpdateResponse(BaseModel):
    """Response model for tenant user status update."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="User ID")
    old_status: TenantUserStatus = Field(..., description="Previous status")
    new_status: TenantUserStatus = Field(..., description="New status")

class TenantResendEmailVerificationRequest(BaseModel):
    """Request model for resending email verification."""
    tenant_id: str = Field(..., description="Tenant identifier (e.g., 'acme-corp')")

class TenantResendEmailVerificationResponse(BaseModel):
    """Response model for resending email verification."""
    tenant_uuid: UUID = Field(..., description="Tenant UUID")
    tenant_id: str = Field(..., description="Tenant identifier")
    token: str = Field(..., description="Verification token")
    message: str = Field(..., description="Response message")


class TenantSendEmailVerificationRequest(BaseModel):
    """Request model for sending initial email verification link."""
    tenant_id: str = Field(..., description="Tenant identifier (e.g., 'acme-corp')")


class TenantSendEmailVerificationResponse(BaseModel):
    """Response model for sending initial email verification link."""
    tenant_uuid: UUID = Field(..., description="Tenant UUID")
    tenant_id: str = Field(..., description="Tenant identifier")
    token: str = Field(..., description="Verification token")
    message: str = Field(..., description="Response message")

class TenantSubscriptionAddRequest(BaseModel):
    """Request model for adding tenant subscriptions."""
    tenant_id: str = Field(..., description="Tenant identifier")
    subscriptions: List[str] = Field(..., min_items=1, description="List of subscriptions to add")

class TenantSubscriptionRemoveRequest(BaseModel):
    """Request model for removing tenant subscriptions."""
    tenant_id: str = Field(..., description="Tenant identifier")
    subscriptions: List[str] = Field(..., min_items=1, description="List of subscriptions to remove")

class TenantSubscriptionResponse(BaseModel):
    """Response model for tenant subscription operations."""
    tenant_id: str = Field(..., description="Tenant identifier")
    subscriptions: List[str] = Field(..., description="Updated list of subscriptions")


class UserSubscriptionAddRequest(BaseModel):
    """Request model for adding user subscriptions under a tenant."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    subscriptions: List[str] = Field(..., min_items=1, description="List of subscriptions to add for the user")


class UserSubscriptionRemoveRequest(BaseModel):
    """Request model for removing user subscriptions under a tenant."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    subscriptions: List[str] = Field(..., min_items=1, description="List of subscriptions to remove for the user")


class UserSubscriptionResponse(BaseModel):
    """Response model for user subscription operations."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    subscriptions: List[str] = Field(..., description="Updated list of user subscriptions")

class ServiceCreateRequest(BaseModel):
    """Request model for creating a service."""
    service_name: SubscriptionType = Field(..., description="Service name", example="asr")
    unit_type: ServiceUnitType = Field(..., description="Unit type for pricing")
    price_per_unit: Decimal = Field(..., gt=0, description="Price per unit")
    currency: ServiceCurrencyType = Field(default=ServiceCurrencyType.INR, description="Currency")
    is_active: bool = Field(..., description="Whether the service is active")

class ServiceResponse(BaseModel):
    """Response model for service information."""
    id: int = Field(..., description="Service ID")
    service_name: str = Field(..., description="Service name")
    unit_type: ServiceUnitType = Field(..., description="Unit type")
    price_per_unit: Decimal = Field(..., description="Price per unit")
    currency: ServiceCurrencyType = Field(..., description="Currency")
    is_active: bool = Field(..., description="Active status")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Update timestamp")

class ListServicesResponse(BaseModel):
    """Response model for listing services."""
    count: int = Field(..., description="Total number of services")
    services: List[ServiceResponse] = Field(..., description="List of services")

class FieldChange(BaseModel):
    """Model for tracking field changes."""
    old: Any = Field(..., description="Old value")
    new: Any = Field(..., description="New value")

class ServiceUpdateRequest(BaseModel):
    """Request model for updating a service."""
    service_id: int = Field(..., description="Service ID")
    price_per_unit: Optional[Decimal] = Field(None, gt=0, description="New price per unit")
    unit_type: Optional[ServiceUnitType] = Field(None, description="New unit type")
    currency: Optional[ServiceCurrencyType] = Field(None, description="New currency")
    is_active: Optional[bool] = Field(None, description="New active status")

class ServiceUpdateResponse(BaseModel):
    """Response model for service update."""
    message: str = Field(..., description="Update message")
    service: ServiceResponse = Field(..., description="Updated service information")
    changes: Dict[str, FieldChange] = Field(..., description="Dictionary of field changes")


class TenantUpdateRequest(BaseModel):
    """Request model for updating tenant information"""
    tenant_id: str = Field(..., description="Tenant identifier")
    organization_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Organization name")
    contact_email: Optional[str] = Field(None, description="Contact email address")
    domain: Optional[str] = Field(None, min_length=3, max_length=255, description="Domain name")
    requested_quotas: Optional[QuotaStructure] = Field(None, description="Requested quota limits (characters_length, audio_length_in_min)")
    usage_quota: Optional[QuotaStructure] = Field(None, description="Usage quota values (characters_length, audio_length_in_min)")
    role: Optional[str] = Field(
        None,
        description="Role for tenant admin (key-value: {'role': 'ADMIN'}). Allowed: ADMIN, USER, GUEST, MODERATOR.",
    )

class TenantUpdateResponse(BaseModel):
    """Response model for tenant update"""
    tenant_id: str = Field(..., description="Tenant identifier")
    message: str = Field(..., description="Update message")
    changes: Dict[str, FieldChange] = Field(..., description="Dictionary of field changes")
    updated_fields: List[str] = Field(..., description="List of updated field names")
    role: Optional[str] = Field(None, description="Current tenant admin role after update")

class TenantViewResponse(BaseModel):
    """Response model for viewing tenant information."""
    id: UUID = Field(..., description="Tenant UUID")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="User ID of the tenant owner")
    organization_name: str = Field(..., description="Organization name")
    email: EmailStr = Field(..., description="Contact email")
    phone_number: Optional[str] = Field(None, description="Contact phone number")
    domain: str = Field(..., description="Tenant domain")
    schema_name: str = Field(..., alias="schema")
    subscriptions: list[str] = Field(..., description="List of subscriptions")
    status: str = Field(..., description="Tenant status")
    quotas: Dict[str , Any] = Field(..., description="Quotas for the tenant")
    usage_quota: Optional[Dict[str, Any]] = Field(None, description="Usage quota values")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Update timestamp")
    role: str = Field("", description="Role for tenant admin (key-value: {'role': 'ADMIN'})")


class TenantUserViewResponse(BaseModel):
    """Response model for viewing tenant user information."""
    id: UUID = Field(..., description="Tenant user UUID")
    user_id: int = Field(..., description="User ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="User email")
    phone_number: Optional[str] = Field(None, description="User phone number")
    subscriptions: list[str] = Field(..., description="List of subscriptions")
    status: str = Field(..., description="User status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Update timestamp")
    is_approved: bool = Field(False, description="Whether the user is approved by tenant admin")
    role: str = Field("", description="Role for the user (key-value: {'role': 'USER'})")


class ListTenantsResponse(BaseModel):
    """Response model for listing all tenants"""
    count: int = Field(..., description="Total number of tenants")
    tenants: List[TenantViewResponse] = Field(..., description="List of tenant details")


class ListUsersResponse(BaseModel):
    """Response model for listing all tenant users"""
    count: int = Field(..., description="Total number of users")
    users: List[TenantUserViewResponse] = Field(..., description="List of user details")


class TenantUserUpdateRequest(BaseModel):
    """Request model for updating tenant user information."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    username: Optional[str] = Field(None,min_length=3,max_length=100,description="Username for the tenant user")
    email: Optional[EmailStr] = Field(None,description="Email address for the tenant user")
    is_approved: Optional[bool] = Field(None,description="Whether the tenant user is approved by the tenant admin")
    role: Optional[str] = Field(
        None,
        description="Role for the user (key-value: {'role': 'USER'}). Allowed: ADMIN, USER, GUEST, MODERATOR.",
    )


class TenantUserUpdateResponse(BaseModel):
    """Response model for tenant user update."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    message: str = Field(..., description="Update message")
    changes: Dict[str, FieldChange] = Field(..., description="Dictionary of field changes")
    updated_fields: List[str] = Field(..., description="List of updated field names")
    role: Optional[str] = Field(None, description="Current role after update (key-value: {'role': 'USER'})")


class TenantUserDeleteRequest(BaseModel):
    """Request model for deleting a tenant user."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="User ID")


class TenantUserDeleteResponse(BaseModel):
    """Response model for tenant user deletion."""
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="User ID")
    message: str = Field(..., description="Deletion message")



class ServiceRegistry:
    """Redis-based service instance management"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.service_ttl = int(os.getenv('SERVICE_REGISTRY_TTL', '300'))
    
    async def register_service(self, service_name: str, instance_id: str, url: str) -> None:
        """Register a service instance"""
        instance_data = {
            'instance_id': instance_id,
            'url': url,
            'health_status': 'healthy',  # Mark as healthy by default
            'last_check_timestamp': str(int(time.time())),
            'avg_response_time': '0.0',
            'consecutive_failures': '0'
        }
        
        # Store instance data
        await self.redis.hset(f"service:{service_name}:instances", instance_id, str(instance_data))
        
        # Add to active instances sorted set (scored by response time)
        await self.redis.zadd(f"service:{service_name}:active", {instance_id: 0.0})
        
        # Set TTL
        await self.redis.expire(f"service:{service_name}:instances", self.service_ttl)
        await self.redis.expire(f"service:{service_name}:active", self.service_ttl)
        
        logger.info(f"Registered service instance: {service_name}:{instance_id} -> {url}")
    
    async def update_health(self, service_name: str, instance_id: str, is_healthy: bool, response_time: float) -> None:
        """Update health status and response time for an instance"""
        instance_key = f"service:{service_name}:instances"
        
        # Get current instance data
        instance_data_raw = await self.redis.hget(instance_key, instance_id)
        if not instance_data_raw:
            return
        
        # Parse and update instance data
        instance_data = eval(instance_data_raw.decode()) if isinstance(instance_data_raw, bytes) else instance_data_raw
        instance_data['health_status'] = 'healthy' if is_healthy else 'unhealthy'
        instance_data['last_check_timestamp'] = str(int(time.time()))
        
        if is_healthy:
            # Update average response time (simple moving average)
            current_avg = float(instance_data.get('avg_response_time', 0.0))
            new_avg = (current_avg + response_time) / 2
            instance_data['avg_response_time'] = str(new_avg)
            instance_data['consecutive_failures'] = '0'
            
            # Update active instances sorted set
            await self.redis.zadd(f"service:{service_name}:active", {instance_id: new_avg})
        else:
            # Increment consecutive failures
            failures = int(instance_data.get('consecutive_failures', 0)) + 1
            instance_data['consecutive_failures'] = str(failures)
            
            # Remove from active instances if too many failures
            max_failures = int(os.getenv('MAX_CONSECUTIVE_FAILURES', '3'))
            if failures >= max_failures:
                await self.redis.zrem(f"service:{service_name}:active", instance_id)
                logger.warning(f"Instance {instance_id} removed from active pool due to {failures} consecutive failures")
        
        # Update instance data
        await self.redis.hset(instance_key, instance_id, str(instance_data))
    
    async def get_healthy_instances(self, service_name: str) -> List[Tuple[str, str]]:
        """Get healthy instances sorted by response time (best first)"""
        active_instances = await self.redis.zrange(f"service:{service_name}:active", 0, -1, withscores=True)
        instances = []
        
        for instance_id, score in active_instances:
            instance_data_raw = await self.redis.hget(f"service:{service_name}:instances", instance_id)
            if instance_data_raw:
                instance_data = eval(instance_data_raw.decode()) if isinstance(instance_data_raw, bytes) else instance_data_raw
                if instance_data.get('health_status') == 'healthy':
                    instances.append((instance_id, instance_data['url']))
        
        return instances
    
    async def remove_instance(self, service_name: str, instance_id: str) -> None:
        """Remove an instance from the registry"""
        await self.redis.hdel(f"service:{service_name}:instances", instance_id)
        await self.redis.zrem(f"service:{service_name}:active", instance_id)
        logger.info(f"Removed instance: {service_name}:{instance_id}")

class LoadBalancer:
    """Health-aware instance selection with weighted round-robin"""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.registry = service_registry
        self.algorithm = os.getenv('LOAD_BALANCER_ALGORITHM', 'weighted_round_robin')
    
    async def select_instance(self, service_name: str) -> Optional[Tuple[str, str]]:
        """Select the best available instance for a service"""
        instances = await self.registry.get_healthy_instances(service_name)
        
        if not instances:
            logger.warning(f"No healthy instances available for service: {service_name}")
            return None
        
        if self.algorithm == 'weighted_round_robin':
            # Return the instance with the lowest response time (best score)
            return instances[0]
        elif self.algorithm == 'random':
            import random
            return random.choice(instances)
        else:
            # Default to first available
            return instances[0]

class RouteManager:
    """Path-to-service mapping management"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.routes = {
            '/api/v1/auth': 'auth-service',
            '/api/v1/config': 'config-service',
            '/api/v1/feature-flags': 'config-service',
            '/api/v1/metrics': 'metrics-service',
            '/api/v1/telemetry': 'telemetry-service',
            '/api/v1/observability': 'telemetry-service',
            '/api/v1/alerting': 'alerting-service',
            '/api/v1/dashboard': 'dashboard-service',
            '/api/v1/asr': 'asr-service',
            '/api/v1/tts': 'tts-service',
            '/api/v1/nmt': 'nmt-service',
            '/api/v1/ocr': 'ocr-service',
            '/api/v1/ner': 'ner-service',
            '/api/v1/transliteration': 'transliteration-service',
            '/api/v1/language-detection': 'language-detection-service',
            '/api/v1/model-management': 'model-management-service',
            '/api/v1/speaker-diarization': 'speaker-diarization-service',
            '/api/v1/language-diarization': 'language-diarization-service',
            '/api/v1/audio-lang-detection': 'audio-lang-detection-service',
            '/api/v1/llm': 'llm-service',
            '/api/v1/pipeline': 'pipeline-service'
        }
    
    async def get_service_for_path(self, path: str) -> Optional[str]:
        """Get service name for a given path using longest prefix matching"""
        # Sort routes by length (longest first) for proper prefix matching
        sorted_routes = sorted(self.routes.items(), key=lambda x: len(x[0]), reverse=True)
        
        for route_prefix, service_name in sorted_routes:
            if path.startswith(route_prefix):
                return service_name
        
        return None
    
    async def load_routes_from_redis(self) -> None:
        """Load route mappings from Redis"""
        if not self.redis:
            return  # Skip if Redis not available
        try:
            route_data = await self.redis.hgetall("routes:mappings")
            if route_data:
                self.routes = {k.decode(): v.decode() for k, v in route_data.items()}
                logger.info(f"Loaded {len(self.routes)} routes from Redis")
        except Exception as e:
            logger.warning(f"Failed to load routes from Redis: {e}")


# OpenAPI Tags Metadata for organizing endpoints by service
tags_metadata = [
    {
        "name": "Role Management",
        "description": "Endpoints for managing user roles and permissions. Admin-only operations for assigning/removing roles and viewing role assignments."
    },
    {
        "name": "Authentication",
        "description": "Authentication and authorization endpoints. Requires authentication headers for protected routes.",
    },
    {
        "name": "OAuth2",
        "description": "OAuth 2.0 authentication endpoints. Sign in with Google and other OAuth providers.",
    },
    {
        "name": "ASR",
        "description": "Automatic Speech Recognition service endpoints. Convert audio to text.",
    },
    {
        "name": "NMT",
        "description": "Neural Machine Translation service endpoints. Translate text between languages.",
    },
    {
        "name": "TTS",
        "description": "Text-to-Speech service endpoints. Convert text to speech audio.",
    },
        {
        "name": "OCR",
        "description": "Optical Character Recognition service endpoints. Extract text from images.",
    },
    {
        "name": "Transliteration",
        "description": "Transliteration service endpoints. Convert text from one script to another.",
    },
    {
        "name": "Language Detection",
        "description": "Language detection service endpoints. Identify text language and script.",
    },
    {
        "name": "Speaker Diarization",
        "description": "Speaker Diarization inference endpoints"
    },
    {
        "name": "Language Diarization",
        "description": "Language Diarization inference endpoints"
    },
    {
        "name": "Audio Language Detection",
        "description": "Audio Language Detection inference endpoints"
    },
    {
        "name": "Model Management",
        "description": "Model catalog management endpoints. Register, update, and list AI models and services.",
    },
    {
        "name": "Pipeline",
        "description": "Pipeline service endpoints. Execute multi-step AI processing pipelines.",
    },
    {
        "name": "Feature Flags",
        "description": "Feature flag management endpoints. Evaluate, list, and manage feature flags using Unleash.",
    },
    {
        "name": "Multi-Tenant",
        "description": "Multi-tenant management endpoints. Tenant registration, user management, billing, and subscriptions.",
    },
    {
        "name": "Observability",
        "description": "Observability endpoints for logs and traces. Search, aggregate, and query logs and distributed traces with RBAC support.",
    },
    {
        "name": "Status",
        "description": "Service status and health check endpoints.",
    },
]

# Pydantic models for Multi-Tenant endpoints

# Initialize FastAPI app
app = FastAPI(
    title="API Gateway Service",
    version="1.0.0",
    description="Central entry point for all microservice requests",
    openapi_tags=tags_metadata
)

# Frontend deep-link support: redirect SPA routes to Simple UI so refreshes on these paths work
FRONTEND_BASE = os.getenv("SIMPLE_UI_URL", "http://simple-ui-frontend:3000")

# Specific SPA redirects (avoid generic catch-all to not shadow /health and API routes)
@app.get("/asr")
async def spa_asr():
    return RedirectResponse(url=f"{FRONTEND_BASE}/asr", status_code=307)

@app.get("/asr/")
async def spa_asr_trailing():
    return RedirectResponse(url=f"{FRONTEND_BASE}/asr", status_code=307)

@app.get("/tts")
async def spa_tts():
    return RedirectResponse(url=f"{FRONTEND_BASE}/tts", status_code=307)

@app.get("/tts/")
async def spa_tts_trailing():
    return RedirectResponse(url=f"{FRONTEND_BASE}/tts", status_code=307)

@app.get("/nmt")
async def spa_nmt():
    return RedirectResponse(url=f"{FRONTEND_BASE}/nmt", status_code=307)

@app.get("/nmt/")
async def spa_nmt_trailing():
    return RedirectResponse(url=f"{FRONTEND_BASE}/nmt", status_code=307)

@app.get("/pipeline")
async def spa_pipeline():
    return RedirectResponse(url=f"{FRONTEND_BASE}/pipeline", status_code=307)

@app.get("/pipeline/")
async def spa_pipeline_trailing():
    return RedirectResponse(url=f"{FRONTEND_BASE}/pipeline", status_code=307)

@app.get("/llm")
async def spa_llm():
    return RedirectResponse(url=f"{FRONTEND_BASE}/llm", status_code=307)

@app.get("/llm/")
async def spa_llm_trailing():
    return RedirectResponse(url=f"{FRONTEND_BASE}/llm", status_code=307)

@app.get("/pipeline-builder")
async def spa_pipeline_builder():
    return RedirectResponse(url=f"{FRONTEND_BASE}/pipeline-builder", status_code=307)

@app.get("/pipeline-builder/")
async def spa_pipeline_builder_trailing():
    return RedirectResponse(url=f"{FRONTEND_BASE}/pipeline-builder", status_code=307)

# OpenAPI/Swagger security scheme (Bearer auth)
bearer_scheme = HTTPBearer(auto_error=False)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")

def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """Infer service and action from path and method."""
    path = request.url.path.lower()
    method = request.method.upper()
    service = "unknown"
    # Check for all services including NER
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm", "ner", "ocr", "transliteration", "language-detection", "speaker-diarization", "language-diarization", "audio-lang-detection"]:
        if f"/api/v1/{svc}" in path:
            service = svc
            break
    action = "read"
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method != "GET":
        action = "inference"
    return service, action

def requires_both_auth_and_api_key(request: Request) -> bool:
    """Check if service requires both Bearer token AND API key."""
    path = request.url.path.lower()
    services_requiring_both = [
        "asr", "nmt", "tts", "pipeline", "llm", "ocr", "transliteration",
        "language-detection", "speaker-diarization", "language-diarization", "audio-lang-detection", "ner"
    ]
    for svc in services_requiring_both:
        if f"/api/v1/{svc}" in path:
            return True
    return False

def is_multi_tenant_request(request: Request) -> bool:
    """Multi-tenant endpoints should use only auth tokens (no API key)."""
    return request.url.path.lower().startswith("/api/v1/multi-tenant")

async def validate_api_key_permissions(api_key: str, service: str, action: str, user_id: Optional[int] = None) -> None:
    """Call auth-service to validate API key permissions.
    
    Args:
        api_key: The API key to validate
        service: Service name (ocr, asr, etc.)
        action: Action type (read, inference)
        user_id: Optional user ID from JWT for ownership check in BOTH mode
    """
    url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
    request_body = {"api_key": api_key, "service": service, "action": action}
    if user_id is not None:
        request_body["user_id"] = user_id
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                json=request_body,
            )
    except httpx.RequestError:
        error_detail = {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Authentication service is temporarily unavailable. Please try again in a few minutes."
        }
        raise HTTPException(status_code=503, detail=error_detail)

    # If auth-service returns non-200, try to extract error message
    if resp.status_code != 200:
        error_message = "API key is required to access this service."
        try:
            error_data = resp.json()
            if isinstance(error_data, dict) and "message" in error_data:
                error_message = error_data["message"]
            elif isinstance(error_data, dict) and "detail" in error_data:
                if isinstance(error_data["detail"], str):
                    error_message = error_data["detail"]
                elif isinstance(error_data["detail"], dict) and "message" in error_data["detail"]:
                    error_message = error_data["detail"]["message"]
        except Exception:
            pass
        
        raise HTTPException(
            status_code=resp.status_code if resp.status_code in [401, 403] else 401,
            detail={
                "error": "INVALID_API_KEY",
                "message": error_message
            }
        )

    # status 200: check body.valid if present
    try:
        data = resp.json()
        if data.get("valid") is False:
            # Extract the actual error message from auth-service
            error_message = data.get("message", "Invalid API key or insufficient permissions")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "AUTHORIZATION_ERROR",
                    "message": error_message
                }
            )
    except HTTPException:
        raise
    except Exception:
        # If body can't be parsed but status was 200, allow
        pass

async def check_permission(
    permission: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials]
) -> None:
    """
    Check if user has the required permission based on Bearer token (JWT) with role-based permissions.
    Model management endpoints only support Bearer token authentication, not API keys.
    
    Args:
        permission: The permission to check (e.g., 'model.create', 'service.update')
        request: FastAPI request object
        credentials: Bearer token credentials
    
    Raises:
        HTTPException: 403 if permission is missing, 401 if not authenticated
    """
    # Model management requires Bearer token authentication only
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated: Bearer access token required for model management",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    payload = await auth_middleware.verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": AUTH_FAILED,
                "message": AUTH_FAILED_MESSAGE
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_permissions = payload.get("permissions", [])
    if permission not in user_permissions:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "PERMISSION_DENIED",
                "message": "Only ADMIN or MODERATOR roles can perform this operation."
            }
        )

def build_auth_headers(request: Request, credentials: Optional[HTTPAuthorizationCredentials], api_key: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    # Copy incoming headers except hop-by-hop, content-length, host, and x-auth-source (we'll set it ourselves)
    for k, v in request.headers.items():
        k_lower = k.lower()
        if k_lower not in ['content-length', 'host', 'x-auth-source'] and not is_hop_by_hop_header(k):
            headers[k] = v
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    # Forward user ID for downstream A/B variant sticky assignment (set by ensure_authenticated_for_request after JWT validation)
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        headers["X-User-Id"] = str(user_id)
    
    # Multi-tenant endpoints: AUTH_TOKEN only (Bearer JWT); API key not required
    if is_multi_tenant_request(request):
        headers.pop("X-API-Key", None)
        headers["X-Auth-Source"] = "AUTH_TOKEN"
        return headers

    # Set X-Auth-Source based on what's present (API Gateway has already validated)
    # Always overwrite X-Auth-Source for services requiring both (don't trust incoming header)
    if requires_both_auth_and_api_key(request):
        if credentials and credentials.credentials and api_key:
            headers['X-Auth-Source'] = 'BOTH'  # Always set to BOTH when both are present
        elif api_key:
            headers['X-Auth-Source'] = 'API_KEY'
        elif credentials and credentials.credentials:
            headers['X-Auth-Source'] = 'AUTH_TOKEN'
    else:
        # For other services, preserve original X-Auth-Source or set based on what's present
        incoming_auth_source = request.headers.get('x-auth-source') or request.headers.get('X-Auth-Source')
        if incoming_auth_source:
            headers['X-Auth-Source'] = incoming_auth_source
        elif api_key:
            headers['X-Auth-Source'] = 'API_KEY'
        elif credentials and credentials.credentials:
            headers['X-Auth-Source'] = 'AUTH_TOKEN'
    
    return headers

# Alert Management Models (for Swagger documentation)
class AlertAnnotation(BaseModel):
    """Alert annotation model"""
    key: str = Field(..., description="Annotation key (summary, description, impact, action)")
    value: str = Field(..., description="Annotation value")

class AlertDefinitionCreate(BaseModel):
    """Request model for creating an alert definition. PromQL is built from alert_type and threshold."""
    name: str = Field(..., description="Alert name (e.g., 'HighLatency')")
    description: Optional[str] = Field(None, description="Alert description")
    threshold_value: float = Field(..., description="Threshold value (e.g. seconds for latency, percent for error_rate/CPU/Memory/Disk)")
    threshold_unit: str = Field(..., description="Threshold unit: 'seconds' (latency), 'percent' or 'ratio' (error_rate), 'percent' (CPU/Memory/Disk)")
    category: str = Field(default="application", description="Category: 'application' or 'infrastructure'")
    severity: str = Field(..., description="Severity: 'critical', 'warning', or 'info'")
    urgency: str = Field(default="medium", description="Urgency: 'high', 'medium', or 'low'")
    alert_type: str = Field(..., description="Application: 'Latency' or 'Error Rate'. Infrastructure: 'CPU', 'Memory', or 'Disk'")
    scope: Optional[str] = Field(None, description="Scope (e.g., 'all_services', 'per_service')")
    evaluation_interval: str = Field(default="30s", description="Prometheus evaluation interval")
    for_duration: str = Field(default="5m", description="Duration before alert fires")
    enabled: Optional[bool] = Field(default=True, description="Whether the alert definition is enabled")
    annotations: Optional[List[AlertAnnotation]] = Field(default_factory=list, description="Alert annotations")

class AlertDefinitionUpdate(BaseModel):
    """Request model for updating an alert definition"""
    description: Optional[str] = None
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    alert_type: Optional[str] = None
    scope: Optional[str] = None
    evaluation_interval: Optional[str] = None
    for_duration: Optional[str] = None
    enabled: Optional[bool] = None
    annotations: Optional[List[AlertAnnotation]] = None

class NotificationReceiverCreate(BaseModel):
    """Request model for creating a notification receiver"""
    category: str = Field(..., description="Category: 'application' or 'infrastructure'")
    severity: str = Field(..., description="Severity: 'critical', 'warning', or 'info'")
    alert_type: Optional[str] = Field(None, description="Optional alert type filter (e.g., 'latency', 'error_rate')")
    email_to: Optional[List[str]] = Field(None, description="Email addresses (required if rbac_role not provided)", min_items=1)
    rbac_role: Optional[str] = Field(None, description="RBAC role name (ADMIN, MODERATOR, USER, GUEST) - if provided, emails will be resolved from users with this role")
    email_subject_template: Optional[str] = Field(None, description="Email subject template")
    email_body_template: Optional[str] = Field(None, description="Email body template (HTML)")

class NotificationReceiverUpdate(BaseModel):
    """Request model for updating a notification receiver"""
    receiver_name: Optional[str] = None
    email_to: Optional[List[str]] = Field(None, description="Email addresses (required if rbac_role not provided)", min_items=1)
    rbac_role: Optional[str] = Field(None, description="RBAC role name (ADMIN, MODERATOR, USER, GUEST) - if provided, emails will be resolved from users with this role")
    email_subject_template: Optional[str] = None
    email_body_template: Optional[str] = None
    enabled: Optional[bool] = None

class RoutingRuleCreate(BaseModel):
    """Request model for creating a routing rule"""
    rule_name: str = Field(..., description="Rule name")
    receiver_id: int = Field(..., description="Notification receiver ID")
    match_severity: Optional[str] = Field(None, description="Match severity (critical, warning, info)")
    match_category: Optional[str] = Field(None, description="Match category (application, infrastructure)")
    match_alert_type: Optional[str] = Field(None, description="Match alert type")
    group_by: Optional[List[str]] = Field(None, description="Group by labels")
    group_wait: Optional[str] = Field(None, description="Group wait time")
    group_interval: Optional[str] = Field(None, description="Group interval")
    repeat_interval: Optional[str] = Field(None, description="Repeat interval")
    continue_routing: Optional[bool] = Field(None, description="Continue routing")
    priority: Optional[int] = Field(None, description="Priority")

class RoutingRuleUpdate(BaseModel):
    """Request model for updating a routing rule"""
    rule_name: Optional[str] = None
    receiver_id: Optional[int] = None
    match_severity: Optional[str] = None
    match_category: Optional[str] = None
    match_alert_type: Optional[str] = None
    group_by: Optional[List[str]] = None
    group_wait: Optional[str] = None
    group_interval: Optional[str] = None
    repeat_interval: Optional[str] = None
    continue_routing: Optional[bool] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None

class RoutingRuleTimingUpdate(BaseModel):
    """Request model for updating routing rule timing parameters"""
    severity: str = Field(..., description="Severity to match (critical, warning, info)")
    category: str = Field(..., description="Category to match (application, infrastructure)")
    alert_type: Optional[str] = Field(None, description="Alert type to match")
    priority: Optional[int] = Field(None, description="Priority to match")
    group_wait: Optional[str] = Field(None, description="Group wait time")
    group_interval: Optional[str] = Field(None, description="Group interval")
    repeat_interval: Optional[str] = Field(None, description="Repeat interval")

async def build_alert_headers(request: Request, credentials: Optional[HTTPAuthorizationCredentials], api_key: Optional[str], organization: Optional[str] = None) -> Dict[str, str]:
    """Build headers for alert management service, including admin/user info"""
    headers = build_auth_headers(request, credentials, api_key)
    
    # Add organization header if provided (admin can specify organization)
    if organization:
        headers["X-Organization"] = organization
    
    # Add username from request state (set by auth middleware from JWT)
    username = getattr(request.state, "username", None)
    # Add admin status, roles, and permissions from token (and ensure X-Username when we have a valid token)
    if credentials and credentials.credentials:
        token = credentials.credentials
        try:
            payload = await auth_middleware.verify_token(token)
            if payload:
                user_permissions = payload.get("permissions", [])
                user_roles = payload.get("roles", [])
                # Use username from token payload if request.state.username was not set (e.g. middleware path or auth response missing username)
                if not username:
                    username = payload.get("username") or (f"user-{payload.get('sub', 'unknown')}" if payload.get("sub") else None)
                # Check if admin
                is_admin = "alerts.admin" in user_permissions or "ADMIN" in [r.upper() for r in user_roles]
                if is_admin:
                    headers["X-Admin"] = "true"
                # Add roles and permissions
                if user_roles:
                    headers["X-User-Roles"] = ",".join(user_roles)
                if user_permissions:
                    headers["X-User-Permissions"] = ",".join(user_permissions)
        except Exception:
            pass  # If token verification fails, headers won't have admin info
    if username:
        headers["X-Username"] = username
    
    return headers

def _get_try_it_key(request: Request) -> str:
    session_id = request.headers.get("X-Anonymous-Session-Id") or request.headers.get("x-anonymous-session-id")
    if session_id:
        return f"tryit:nmt:session:{session_id}"
    client_ip = request.client.host if request.client else "unknown"
    return f"tryit:nmt:ip:{client_ip}"

async def _increment_try_it_count(key: str) -> int:
    # Prefer Redis if available
    if redis_client:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, TRY_IT_TTL_SECONDS)
        return int(count)

    # Fallback: in-memory counter with TTL
    now = time.time()
    entry = try_it_counters.get(key)
    if not entry or (now - entry["started_at"] > TRY_IT_TTL_SECONDS):
        entry = {"count": 0, "started_at": now}
    entry["count"] += 1
    try_it_counters[key] = entry
    return entry["count"]

async def get_verified_tenant_id(request: Request) -> str:
    """
    Extract and verify tenant_id from JWT token.
    
    The tenant_id in JWT is already verified by auth-service when token was issued,
    so we trust it. However, we verify that:
    1. User is authenticated (user_id exists)
    2. Tenant_id is present in JWT (user belongs to a tenant)
    
    Returns:
        str: Verified tenant_id from JWT token
        
    Raises:
        HTTPException: If user_id or tenant_id is missing
    """
    user_id = getattr(request.state, "user_id", None)
    
    # Verify user_id is present (required for authenticated requests)
    if not user_id:
        logger.warning(
            "Tenant verification: user_id missing from authenticated request",
            extra={"context": {"path": request.url.path}}
        )
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTHENTICATION_REQUIRED",
                "message": "User ID not found in authentication token. Please log in again."
            }
        )
    
    # Extract tenant_id from JWT token (set by auth middleware)
    tenant_id = getattr(request.state, "tenant_id", None)
    
    # If tenant_id is missing from JWT, user is not associated with any tenant.
    # For free-user flows we allow this and simply return None so that callers
    # (e.g. SMR) can apply free-user routing logic without tenant context.
    if not tenant_id:
        logger.warning(
            "Tenant verification: tenant_id missing from JWT token (treating as free user)",
            extra={
                "context": {
                    "user_id": user_id,
                    "path": request.url.path,
                    "message": "No tenant_id in token; falling back to free-user routing.",
                }
            },
        )
        return None
    
    logger.debug(
        "Tenant verified from JWT",
        extra={
            "context": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "path": request.url.path
            }
        }
    )
    
    return tenant_id


def extract_and_validate_policy_headers(request: Request) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract and validate policy headers from request.
    
    Headers:
    - X-Latency-Policy: low, medium, or high
    - X-Cost-Policy: tier_1, tier_2, or tier_3
    - X-Accuracy-Policy: sensitive or standard
    
    Returns:
        Tuple[Optional[str], Optional[str], Optional[str]]: (latency_policy, cost_policy, accuracy_policy)
        
    Raises:
        HTTPException: If any header value is invalid or the combination is against policy
    """
    latency_policy = None
    cost_policy = None
    accuracy_policy = None
    
    # Extract latency policy header
    latency_header = request.headers.get("X-Latency-Policy") or request.headers.get("x-latency-policy")
    if latency_header:
        latency_header = latency_header.strip().lower()
        try:
            # Validate against enum
            LatencyPolicy(latency_header)
            latency_policy = latency_header
        except ValueError:
            valid_values = ", ".join([e.value for e in LatencyPolicy])
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_LATENCY_POLICY",
                    "message": f"Invalid X-Latency-Policy header value: '{latency_header}'. Expected one of: {valid_values}"
                }
            )
    
    # Extract cost policy header
    cost_header = request.headers.get("X-Cost-Policy") or request.headers.get("x-cost-policy")
    if cost_header:
        cost_header = cost_header.strip().lower()
        try:
            # Validate against enum
            CostPolicy(cost_header)
            cost_policy = cost_header
        except ValueError:
            valid_values = ", ".join([e.value for e in CostPolicy])
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_COST_POLICY",
                    "message": f"Invalid X-Cost-Policy header value: '{cost_header}'. Expected one of: {valid_values}"
                }
            )
    
    # Extract accuracy policy header
    accuracy_header = request.headers.get("X-Accuracy-Policy") or request.headers.get("x-accuracy-policy")
    if accuracy_header:
        accuracy_header = accuracy_header.strip().lower()
        try:
            # Validate against enum
            AccuracyPolicy(accuracy_header)
            accuracy_policy = accuracy_header
        except ValueError:
            valid_values = ", ".join([e.value for e in AccuracyPolicy])
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_ACCURACY_POLICY",
                    "message": f"Invalid X-Accuracy-Policy header value: '{accuracy_header}'. Expected one of: {valid_values}"
                }
            )
    
    # ------------------------------------------------------------------
    # Cross-header policy constraints (only applied when user passes
    # explicit headers).
    #
    # Business rules:
    # - "High accuracy" (mapped to AccuracyPolicy.SENSITIVE) cannot be
    #   combined with "low cost" (CostPolicy.TIER_1).
    # - "Low latency" (LatencyPolicy.LOW) cannot be combined with
    #   "low cost" (CostPolicy.TIER_1).
    # ------------------------------------------------------------------
    if cost_policy == CostPolicy.TIER_1.value:
        # Low cost + high accuracy (sensitive) is not allowed
        if accuracy_policy == AccuracyPolicy.SENSITIVE.value:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "POLICY_CONSTRAINT_VIOLATION",
                    "message": (
                        "Requested combination X-Accuracy-Policy='sensitive' with "
                        "X-Cost-Policy='tier_1' is against policy. "
                        "Please choose a higher cost tier or lower accuracy profile."
                    ),
                },
            )
        # Low cost + low latency is not allowed
        if latency_policy == LatencyPolicy.LOW.value:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "POLICY_CONSTRAINT_VIOLATION",
                    "message": (
                        "Requested combination X-Latency-Policy='low' with "
                        "X-Cost-Policy='tier_1' is against policy. "
                        "Please choose a higher cost tier or higher latency profile."
                    ),
                },
            )
    
    return latency_policy, cost_policy, accuracy_policy


async def ensure_authenticated_for_request(req: Request, credentials: Optional[HTTPAuthorizationCredentials], api_key: Optional[str]) -> None:
    """Enforce authentication - require BOTH Bearer token AND API key for all services."""
    # Get tracer for creating spans
    tracer = None
    if TRACING_AVAILABLE:
        try:
            tracer = trace.get_tracer("api-gateway-service")
        except Exception:
            pass
    
    # Create main authentication span
    auth_span_context = tracer.start_as_current_span("gateway.authenticate") if tracer else nullcontext()
    
    with auth_span_context as auth_span:
        if auth_span:
            auth_span.set_attribute("gateway.operation", "authenticate_request")
            auth_span.set_attribute("http.method", req.method)
            auth_span.set_attribute("http.route", req.url.path)
        
        requires_both = requires_both_auth_and_api_key(req)
        if auth_span:
            auth_span.set_attribute("auth.requires_both", requires_both)
        
        if requires_both:
            # For ASR, NMT, TTS, Pipeline, LLM: require BOTH Bearer token AND API key
            token = credentials.credentials if credentials else None
            
            # Validate Bearer token with span
            token_span_context = tracer.start_as_current_span("gateway.auth.validate_token") if tracer else nullcontext()
            with token_span_context as token_span:
                if token_span:
                    token_span.set_attribute("auth.method", "Bearer")
                    token_span.set_attribute("auth.token_present", bool(token))
                
                # Check if Bearer token is missing
                if not token:
                    if token_span:
                        token_span.set_attribute("error", True)
                        token_span.set_attribute("error.type", "MissingToken")
                        token_span.set_attribute("error.message", "Bearer token is required")
                        token_span.set_status(Status(StatusCode.ERROR, "Token missing"))
                    if auth_span:
                        auth_span.set_attribute("auth.authenticated", False)
                        auth_span.set_attribute("error.type", "MissingToken")
                        auth_span.set_status(Status(StatusCode.ERROR, "Token missing"))
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "code": AUTH_FAILED,
                            "message": AUTH_FAILED_MESSAGE
                        },
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                # Validate Bearer token
                try:
                    payload = await auth_middleware.verify_token(token)
                    if token_span:
                        token_span.set_attribute("auth.token_valid", payload is not None)
                        if payload:
                            token_span.set_attribute("user.id", str(payload.get("sub", "unknown")))
                            token_span.set_attribute("user.username", payload.get("username", "unknown"))
                            token_span.set_status(Status(StatusCode.OK))
                        else:
                            token_span.set_attribute("error", True)
                            token_span.set_attribute("error.type", "InvalidToken")
                            token_span.set_status(Status(StatusCode.ERROR, "Token validation failed"))
                    
                    if payload is None:
                        if auth_span:
                            auth_span.set_attribute("auth.authenticated", False)
                            auth_span.set_attribute("error.type", "InvalidToken")
                            auth_span.set_status(Status(StatusCode.ERROR, "Token validation failed"))
                        raise HTTPException(
                            status_code=401,
                            detail={
                                "code": AUTH_FAILED,
                                "message": AUTH_FAILED_MESSAGE
                            },
                            headers={"WWW-Authenticate": "Bearer"}
                        )
                    
                    # Set user context in request state (in case middleware didn't set it)
                    if payload:
                        # Basic identity used by downstream (e.g. A/B variant sticky assignment via X-User-Id)
                        req.state.user_id = payload.get("sub") or payload.get("user_id")
                        req.state.username = payload.get("username")
                        req.state.permissions = payload.get("permissions", [])
                        req.state.is_authenticated = True
                        req.state.jwt_payload = payload
                        
                        # Extract tenant information using resolve_tenant_from_jwt
                        # NOTE:
                        #   - If tenant info is present, we treat this as a tenant-scoped request.
                        #   - If tenant info is missing, we now allow "free user" flows (no tenant),
                        #     so we DO NOT raise an error here. Downstream logic (SMR, services)
                        #     can handle tenant_id=None appropriately.
                        tenant_context = resolve_tenant_from_jwt(payload)
                        if tenant_context:
                            req.state.tenant_id = tenant_context.get("tenant_id")
                            req.state.tenant_uuid = tenant_context.get("tenant_uuid")
                            req.state.schema_name = tenant_context.get("schema_name")
                            req.state.subscriptions = tenant_context.get("subscriptions", [])
                            req.state.user_subscriptions = tenant_context.get("user_subscriptions", [])
                except HTTPException:
                    raise
                except Exception as e:
                    if token_span:
                        token_span.set_attribute("error", True)
                        token_span.set_attribute("error.type", type(e).__name__)
                        token_span.set_attribute("error.message", str(e))
                        token_span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
            
            # Validate API key with span
            api_key_span_context = tracer.start_as_current_span("gateway.auth.validate_api_key") if tracer else nullcontext()
            with api_key_span_context as api_key_span:
                if api_key_span:
                    api_key_span.set_attribute("auth.method", "API_KEY")
                    api_key_span.set_attribute("auth.api_key_present", bool(api_key))
                
                # Check if API key is missing
                if not api_key:
                    if api_key_span:
                        api_key_span.set_attribute("error", True)
                        api_key_span.set_attribute("error.type", "MissingAPIKey")
                        api_key_span.set_attribute("error.message", "API key is required")
                        api_key_span.set_status(Status(StatusCode.ERROR, "API key missing"))
                    if auth_span:
                        auth_span.set_attribute("auth.authenticated", False)
                        auth_span.set_attribute("error.type", "MissingAPIKey")
                        auth_span.set_status(Status(StatusCode.ERROR, "API key missing"))
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "error": "API_KEY_MISSING",
                            "message": "API key is required to access this service."
                        }
                    )
                
                # Validate API key permissions
                service, action = determine_service_and_action(req)
                if api_key_span:
                    api_key_span.set_attribute("auth.service", service)
                    api_key_span.set_attribute("auth.action", action)
                
                # Create authorization span for permission check
                authz_span_context = tracer.start_as_current_span("gateway.authorize") if tracer else nullcontext()
                with authz_span_context as authz_span:
                    if authz_span:
                        authz_span.set_attribute("gateway.operation", "authorize_request")
                        authz_span.set_attribute("auth.service", service)
                        authz_span.set_attribute("auth.action", action)
                        authz_span.set_attribute("auth.method", "API_KEY")
                    
                    try:
                        # In BOTH mode, pass user_id to validate API key ownership
                        jwt_user_id = getattr(req.state, "user_id", None)
                        await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
                        if authz_span:
                            authz_span.set_attribute("auth.authorized", True)
                            authz_span.set_status(Status(StatusCode.OK))
                        if api_key_span:
                            api_key_span.set_attribute("auth.api_key_valid", True)
                            api_key_span.set_status(Status(StatusCode.OK))
                        if auth_span:
                            auth_span.set_attribute("auth.authenticated", True)
                            auth_span.set_attribute("auth.authorized", True)
                            auth_span.set_status(Status(StatusCode.OK))
                    except HTTPException as e:
                        if authz_span:
                            authz_span.set_attribute("auth.authorized", False)
                            authz_span.set_attribute("error", True)
                            authz_span.set_attribute("error.type", "AuthorizationFailed")
                            authz_span.set_attribute("error.message", str(e.detail))
                            authz_span.set_attribute("http.status_code", e.status_code)
                            authz_span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                        if api_key_span:
                            api_key_span.set_attribute("auth.api_key_valid", False)
                            api_key_span.set_attribute("error", True)
                            api_key_span.set_attribute("error.type", "AuthorizationFailed")
                            api_key_span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                        if auth_span:
                            auth_span.set_attribute("auth.authenticated", True)  # Token was valid
                            auth_span.set_attribute("auth.authorized", False)
                            auth_span.set_attribute("error.type", "AuthorizationFailed")
                            auth_span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                        # Re-raise with the specific error message from auth-service
                        raise
        else:
            # For other services: existing logic (either Bearer OR API key, or BOTH)
            auth_source = (req.headers.get("x-auth-source") or "").upper()
            if is_multi_tenant_request(req):
                auth_source = "AUTH_TOKEN"
            use_api_key = api_key is not None and auth_source in ("API_KEY", "BOTH")
            if auth_span:
                auth_span.set_attribute("auth.source", auth_source)
                auth_span.set_attribute("auth.use_api_key", use_api_key)

            # If x-auth-source is explicitly set to API_KEY or BOTH, require API key
            if auth_source in ("API_KEY", "BOTH") and not api_key:
                if auth_span:
                    auth_span.set_attribute("auth.authenticated", False)
                    auth_span.set_attribute("error.type", "MissingAPIKey")
                    auth_span.set_status(Status(StatusCode.ERROR, "API key required"))
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": "API_KEY_MISSING",
                        "message": f"API key is required when X-Auth-Source is set to {auth_source}"
                    }
                )
            
            # If x-auth-source is BOTH, also require Bearer token
            if auth_source == "BOTH" and (not credentials or not credentials.credentials):
                if auth_span:
                    auth_span.set_attribute("auth.authenticated", False)
                    auth_span.set_attribute("error.type", "MissingToken")
                    auth_span.set_status(Status(StatusCode.ERROR, "Bearer token required"))
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": "AUTH_TOKEN_MISSING",
                        "message": "Bearer token is required when X-Auth-Source is set to BOTH"
                    },
                    headers={"WWW-Authenticate": "Bearer"}
                )

            if use_api_key:
                # If auth_source is BOTH, validate JWT token first
                jwt_user_id = None
                if auth_source == "BOTH":
                    token = credentials.credentials
                    token_span_context = tracer.start_as_current_span("gateway.auth.validate_token") if tracer else nullcontext()
                    with token_span_context as token_span:
                        if token_span:
                            token_span.set_attribute("auth.method", "Bearer")
                            token_span.set_attribute("auth.token_present", bool(token))
                        
                        try:
                            payload = await auth_middleware.verify_token(token)
                            if token_span:
                                token_span.set_attribute("auth.token_valid", payload is not None)
                                if payload:
                                    token_span.set_attribute("user.id", str(payload.get("sub", "unknown")))
                                    token_span.set_attribute("user.username", payload.get("username", "unknown"))
                                    token_span.set_status(Status(StatusCode.OK))
                            
                            if payload is None:
                                if auth_span:
                                    auth_span.set_attribute("auth.authenticated", False)
                                    auth_span.set_attribute("error.type", "InvalidToken")
                                    auth_span.set_status(Status(StatusCode.ERROR, "Token validation failed"))
                                raise HTTPException(
                                    status_code=401,
                                    detail={
                                        "code": AUTH_FAILED,
                                        "message": AUTH_FAILED_MESSAGE
                                    },
                                    headers={"WWW-Authenticate": "Bearer"}
                                )
                            
                            # Set user context from JWT
                            if payload:
                                req.state.user_id = payload.get("sub") or payload.get("user_id")
                                req.state.username = payload.get("username")
                                req.state.permissions = payload.get("permissions", [])
                                req.state.is_authenticated = True
                                req.state.jwt_payload = payload
                                jwt_user_id = req.state.user_id
                                
                                # Extract tenant information
                                tenant_context = resolve_tenant_from_jwt(payload)
                                if tenant_context:
                                    req.state.tenant_id = tenant_context.get("tenant_id")
                                    req.state.tenant_uuid = tenant_context.get("tenant_uuid")
                                    req.state.schema_name = tenant_context.get("schema_name")
                                    req.state.subscriptions = tenant_context.get("subscriptions", [])
                                    req.state.user_subscriptions = tenant_context.get("user_subscriptions", [])
                        except HTTPException:
                            raise
                        except Exception as e:
                            if token_span:
                                token_span.set_attribute("error", True)
                                token_span.set_attribute("error.type", type(e).__name__)
                                token_span.set_attribute("error.message", str(e))
                                token_span.set_status(Status(StatusCode.ERROR, str(e)))
                            raise
                
                # Validate API key permissions via auth-service
                service, action = determine_service_and_action(req)
                
                # Validate API key with span
                api_key_span_context = tracer.start_as_current_span("gateway.auth.validate_api_key") if tracer else nullcontext()
                with api_key_span_context as api_key_span:
                    if api_key_span:
                        api_key_span.set_attribute("auth.method", "API_KEY")
                        api_key_span.set_attribute("auth.service", service)
                        api_key_span.set_attribute("auth.action", action)
                    
                    # Create authorization span for permission check
                    authz_span_context = tracer.start_as_current_span("gateway.authorize") if tracer else nullcontext()
                    with authz_span_context as authz_span:
                        if authz_span:
                            authz_span.set_attribute("gateway.operation", "authorize_request")
                            authz_span.set_attribute("auth.service", service)
                            authz_span.set_attribute("auth.action", action)
                            authz_span.set_attribute("auth.method", "API_KEY" if auth_source == "API_KEY" else "BOTH")
                        
                        try:
                            # For BOTH mode, pass user_id to check ownership; for API_KEY-only, no user_id
                            await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
                            if authz_span:
                                authz_span.set_attribute("auth.authorized", True)
                                authz_span.set_status(Status(StatusCode.OK))
                            if api_key_span:
                                api_key_span.set_attribute("auth.api_key_valid", True)
                                api_key_span.set_status(Status(StatusCode.OK))
                            if auth_span:
                                auth_span.set_attribute("auth.authenticated", True)
                                auth_span.set_attribute("auth.authorized", True)
                                auth_span.set_status(Status(StatusCode.OK))
                        except HTTPException as e:
                            if authz_span:
                                authz_span.set_attribute("auth.authorized", False)
                                authz_span.set_attribute("error", True)
                                authz_span.set_attribute("error.type", "AuthorizationFailed")
                                authz_span.set_attribute("error.message", str(e.detail))
                                authz_span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                            if api_key_span:
                                api_key_span.set_attribute("auth.api_key_valid", False)
                                api_key_span.set_attribute("error", True)
                                api_key_span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                            if auth_span:
                                auth_span.set_attribute("auth.authenticated", False)
                                auth_span.set_attribute("auth.authorized", False)
                                auth_span.set_attribute("error.type", "AuthorizationFailed")
                                auth_span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                            raise
                return

            # Default: require Bearer token
            token_span_context = tracer.start_as_current_span("gateway.auth.validate_token") if tracer else nullcontext()
            with token_span_context as token_span:
                if token_span:
                    token_span.set_attribute("auth.method", "Bearer")
                    token_span.set_attribute("auth.token_present", bool(credentials and credentials.credentials))
                
                if not credentials or not credentials.credentials:
                    if token_span:
                        token_span.set_attribute("error", True)
                        token_span.set_attribute("error.type", "MissingToken")
                        token_span.set_attribute("error.message", "Bearer token is required")
                        token_span.set_status(Status(StatusCode.ERROR, "Token missing"))
                    if auth_span:
                        auth_span.set_attribute("auth.authenticated", False)
                        auth_span.set_attribute("error.type", "MissingToken")
                        auth_span.set_status(Status(StatusCode.ERROR, "Token missing"))
                    raise HTTPException(
                        status_code=401, 
                        detail="Not authenticated: Bearer access token required (Authorization header)",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                token = credentials.credentials
                try:
                    payload = await auth_middleware.verify_token(token)
                    if token_span:
                        token_span.set_attribute("auth.token_valid", payload is not None)
                        if payload:
                            token_span.set_attribute("user.id", str(payload.get("sub", "unknown")))
                            token_span.set_attribute("user.username", payload.get("username", "unknown"))
                            token_span.set_status(Status(StatusCode.OK))
                        else:
                            token_span.set_attribute("error", True)
                            token_span.set_attribute("error.type", "InvalidToken")
                            token_span.set_status(Status(StatusCode.ERROR, "Token validation failed"))
                    
                    if payload is None:
                        if auth_span:
                            auth_span.set_attribute("auth.authenticated", False)
                            auth_span.set_attribute("error.type", "InvalidToken")
                            auth_span.set_status(Status(StatusCode.ERROR, "Token validation failed"))
                        raise HTTPException(
                            status_code=401,
                            detail={
                                "code": AUTH_FAILED,
                                "message": AUTH_FAILED_MESSAGE
                            },
                            headers={"WWW-Authenticate": "Bearer"}
                        )
                    
                    # Set user context in request state (in case middleware didn't set it)
                    if payload:
                        # Basic identity used by downstream (e.g. A/B variant sticky assignment via X-User-Id)
                        req.state.user_id = payload.get("sub") or payload.get("user_id")
                        req.state.username = payload.get("username")
                        req.state.permissions = payload.get("permissions", [])
                        req.state.is_authenticated = True
                        req.state.jwt_payload = payload
                        
                        # Extract tenant information using resolve_tenant_from_jwt
                        tenant_context = resolve_tenant_from_jwt(payload)
                        if tenant_context:
                            req.state.tenant_id = tenant_context.get("tenant_id")
                            req.state.tenant_uuid = tenant_context.get("tenant_uuid")
                            req.state.schema_name = tenant_context.get("schema_name")
                            req.state.subscriptions = tenant_context.get("subscriptions", [])
                            req.state.user_subscriptions = tenant_context.get("user_subscriptions", [])
                        else:
                            pass
                            # Tenant is required - return error if not present
                            # if auth_span:
                            #     auth_span.set_attribute("error", True)
                            #     auth_span.set_attribute("error.type", "TenantMissing")
                            #     auth_span.set_status(Status(StatusCode.ERROR, "Tenant ID missing from token"))
                            # raise HTTPException(
                            #     status_code=403,
                            #     detail={
                            #         "code": "TENANT_REQUIRED",
                            #         "message": "Tenant ID is required for this operation. Your account is not associated with any tenant. Please contact your administrator."
                            #     }
                            # )
                    if auth_span:
                        auth_span.set_attribute("auth.authenticated", True)
                        auth_span.set_attribute("auth.authorized", True)  # Bearer token implies authorization
                        auth_span.set_status(Status(StatusCode.OK))
                except HTTPException:
                    raise
                except Exception as e:
                    if token_span:
                        token_span.set_attribute("error", True)
                        token_span.set_attribute("error.type", type(e).__name__)
                        token_span.set_attribute("error.message", str(e))
                        token_span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

# --- OpenAPI customization: add x-auth-source dropdown param globally ---
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Point Swagger to API Gateway (port 8080) - same permission logic as Kong
    server_url = os.getenv("SWAGGER_SERVER_URL", "http://localhost:8080")
    openapi_schema["servers"] = [
        {
            "url": server_url,
            "description": "API Gateway (with API Key Permission Validation)",
        }
    ]

    # Ensure top-level tags are set explicitly for Swagger UI grouping
    openapi_schema["tags"] = [{"name": t["name"], "description": t.get("description", "")} for t in tags_metadata]

    # Ensure components exist
    components = openapi_schema.setdefault("components", {})
    parameters = components.setdefault("parameters", {})

    # Define global header parameter with enum dropdown
    parameters["XAuthSource"] = {
        "name": "x-auth-source",
        "in": "header",
        "required": False,
        "description": "Select auth source for testing in Swagger (API_KEY or AUTH_TOKEN)",
        "schema": {
            "type": "string",
            "enum": ["API_KEY", "AUTH_TOKEN"],
            "default": "API_KEY"
        }
    }

    # Endpoints that should NOT get x-auth-source header
    skip_x_auth_source_paths = set([
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/request-password-reset",
        "/api/v1/auth/oauth2/providers",
        "/api/v1/auth/oauth2/callback",
        "/api/v1/auth/oauth2/google/authorize",
        "/api/v1/auth/oauth2/google/callback",
        "/api/v1/multi-tenant/register/tenant",
        "/api/v1/multi-tenant/register/users",
        "/api/v1/multi-tenant/update/tenants/status",
        "/api/v1/multi-tenant/update/users/status",
        "/api/v1/multi-tenant/email/verify",
        "/api/v1/multi-tenant/view/tenant",
        "/api/v1/multi-tenant/view/user",
        "/api/v1/multi-tenant/email/resend",
        "/api/v1/multi-tenant/subscriptions/add",
        "/api/v1/multi-tenant/subscriptions/remove",
        "/api/v1/multi-tenant/user/subscriptions/add",
        "/api/v1/multi-tenant/user/subscriptions/remove",
        "/api/v1/multi-tenant/register/services",
        "/api/v1/multi-tenant/update/services",
        "/api/v1/multi-tenant/list/services",
        "/api/v1/multi-tenant/resolve-tenant-from-user/{user_id}",
    ])

    # Auto-tag operations by path prefix for better grouping in Swagger and inject header where applicable
    path_to_tag = [
        ("/api/v1/auth", "Authentication"),
        ("/api/v1/asr", "ASR"),
        ("/api/v1/tts", "TTS"),
        ("/api/v1/nmt", "NMT"),
        ("/api/v1/ocr", "OCR"),
        ("/api/v1/ner", "NER"),
        ("/api/v1/transliteration", "Transliteration"),
        ("/api/v1/language-detection", "Language Detection"),
        ("/api/v1/model-management", "Model Management"),
        ("/api/v1/speaker-diarization", "Speaker Diarization"),
        ("/api/v1/language-diarization", "Language Diarization"),
        ("/api/v1/audio-lang-detection", "Audio Language Detection"),
        ("/api/v1/pipeline", "Pipeline"),
        ("/api/v1/feature-flags", "Feature Flags"),
        ("/api/v1/observability", "Observability"),
        ("/api/v1/telemetry", "Observability"),
        ("/api/v1/protected", "Protected"),
        ("/api/v1/status", "Status"),
        ("/health", "Status"),
        ("/", "Status"),
    ]

    for path, path_item in openapi_schema.get("paths", {}).items():
        tag = None
        for prefix, t in path_to_tag:
            if path == prefix or path.startswith(prefix):
                tag = t
                break
        if tag:
            for operation in list(path_item.keys()):
                if operation in ["get", "post", "put", "patch", "delete", "options", "head"]:
                    op_obj = path_item[operation]
                    existing_tags = op_obj.get("tags") or []
                    if tag not in existing_tags:
                        # Prepend to make group ordering clearer
                        op_obj["tags"] = [tag] + existing_tags

                    # Inject x-auth-source header except for skip list
                    if path not in skip_x_auth_source_paths:
                        op_params = op_obj.setdefault("parameters", [])
                        if not any(p.get("$ref") == "#/components/parameters/XAuthSource" or p.get("name") == "x-auth-source" for p in op_params):
                            op_params.append({"$ref": "#/components/parameters/XAuthSource"})

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Global variables for connections and components
redis_client = None
http_client = None
service_registry = None
load_balancer = None
route_manager = None
health_monitor_task = None

#
# NOTE: Try-It anonymous access controls (rate limiting, default service, etc.)
# are now fully handled inside nmt-service (see its try_it_router and try_it_utils).
# The API Gateway only exposes /api/v1/try-it and proxies requests to nmt-service.

# Utility functions
def generate_correlation_id() -> str:
    """Generate a new correlation ID"""
    return str(uuid.uuid4())

def is_hop_by_hop_header(header_name: str) -> bool:
    """Check if header is hop-by-hop and should not be forwarded"""
    hop_by_hop_headers = {
        'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
        'te', 'trailers', 'transfer-encoding', 'upgrade'
    }
    return header_name.lower() in hop_by_hop_headers

def prepare_forwarding_headers(request: Request, correlation_id: str, request_id: str) -> Dict[str, str]:
    """Prepare headers for forwarding to downstream services"""
    headers = {}
    
    # Copy all incoming headers except hop-by-hop headers
    for header_name, header_value in request.headers.items():
        if not is_hop_by_hop_header(header_name):
            headers[header_name] = header_value
    
    # Add forwarding headers
    headers['X-Forwarded-For'] = request.client.host if request.client else 'unknown'
    headers['X-Forwarded-Proto'] = request.url.scheme
    headers['X-Forwarded-Host'] = request.headers.get('host', 'unknown')
    headers['X-Correlation-ID'] = correlation_id
    headers['X-Request-ID'] = request_id
    headers['X-Gateway-Timestamp'] = str(int(time.time() * 1000))
    
    # Inject OpenTelemetry trace context for distributed tracing
    if TRACING_AVAILABLE and inject:
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                inject(headers)
                logger.debug("✅ Trace context injected into request headers")
        except Exception as e:
            logger.warning(f"⚠️ Failed to inject trace context: {e}")
    
    return headers

def log_request(method: str, path: str, service: str, instance: str, duration: float, status_code: int) -> None:
    """Log downstream service requests for observability.

    Successful 2xx responses are already logged at the service level, so we
    skip them here to avoid duplicate 200 logs in OpenSearch. 4xx client
    errors are handled by the API gateway's RequestLoggingMiddleware.
    This helper is therefore reserved for server-side failures (5xx) so that
    only one error log is emitted per failing call.
    """
    # Skip 2xx/3xx responses – these are logged by downstream services
    if 200 <= status_code < 400:
        return

    # Skip 4xx client errors – these are logged by RequestLoggingMiddleware
    if 400 <= status_code < 500:
        return

    # Log 5xx errors that originate from downstream services
    logger.error(
        f"Request: {method} {path} -> {service}:{instance} "
        f"({duration:.3f}s, {status_code})"
    )

async def health_monitor():
    """Background task to monitor health of all service instances"""
    global service_registry, http_client
    
    if not service_registry or not http_client:
        logger.error("Health monitor: service registry or HTTP client not initialized")
        return
    
    health_check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))
    health_check_timeout = int(os.getenv('HEALTH_CHECK_TIMEOUT', '5'))
    
    logger.info(f"Starting health monitor (interval: {health_check_interval}s)")
    
    while True:
        try:
            # Get all registered services
            service_keys = await redis_client.keys("service:*:instances")
            
            for service_key in service_keys:
                service_name = service_key.decode().split(':')[1]
                
                # Get ALL instances for this service (not just healthy ones)
                all_instances = await redis_client.hgetall(f"service:{service_name}:instances")
                
                for instance_id_bytes, instance_data_bytes in all_instances.items():
                    instance_id = instance_id_bytes.decode() if isinstance(instance_id_bytes, bytes) else instance_id_bytes
                    instance_data_raw = instance_data_bytes.decode() if isinstance(instance_data_bytes, bytes) else instance_data_bytes
                    
                    try:
                        # Parse instance data
                        instance_data = eval(instance_data_raw) if isinstance(instance_data_raw, str) else instance_data_raw
                        instance_url = instance_data.get('url')
                        
                        if not instance_url:
                            continue
                            
                        # Perform health check
                        start_time = time.time()
                        # Use different health endpoints for different services
                        health_endpoint = "/health"
                        if service_name == "nmt-service":
                            health_endpoint = "/api/v1/nmt/health"
                        elif service_name == "asr-service":
                            health_endpoint = "/api/v1/asr/health"
                        elif service_name == "speaker-diarization-service":
                            health_endpoint = "/health"
                        elif service_name == "language-diarization-service":
                            health_endpoint = "/health"
                        elif service_name == "audio-lang-detection-service":
                            health_endpoint = "/health"
                        
                        response = await http_client.get(
                            f"{instance_url}{health_endpoint}",
                            timeout=health_check_timeout
                        )
                        response_time = time.time() - start_time
                        
                        is_healthy = response.status_code == 200
                        
                        # Update health status
                        await service_registry.update_health(
                            service_name, instance_id, is_healthy, response_time
                        )
                        
                        if is_healthy:
                            logger.debug(f"Health check passed: {service_name}:{instance_id} ({response_time:.3f}s)")
                        else:
                            logger.warning(f"Health check failed: {service_name}:{instance_id} (status: {response.status_code})")
                            
                    except Exception as e:
                        # Health check failed
                        await service_registry.update_health(
                            service_name, instance_id, False, 0.0
                        )
                        logger.warning(f"Health check error: {service_name}:{instance_id} - {e}")
            
            # Wait for next health check cycle
            await asyncio.sleep(health_check_interval)
            
        except Exception as e:
            logger.error(f"Health monitor error: {e}")
            await asyncio.sleep(health_check_interval)

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
if TRACING_AVAILABLE:
    try:
        # Setup tracing and get tracer instance
        setup_tracing("api-gateway-service")
        # Get the tracer instance (OpenTelemetry tracers are singletons per name)
        tracer = trace.get_tracer("api-gateway-service")
        if tracer:
            logger.info("✅ Distributed tracing initialized for API Gateway service")
            
            # Instrument FastAPI with OpenTelemetry
            # Exclude health check and metrics endpoints to reduce span noise
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls="/health,/metrics,/enterprise/metrics,/docs,/redoc,/openapi.json"
            )
            logger.info("✅ FastAPI instrumented for distributed tracing")
            
            # Instrument httpx client in auth_middleware for tracing HTTP calls to auth-service
            # This must happen AFTER tracing is set up
            auth_middleware.instrument_http_client()
        else:
            logger.warning("⚠️ Tracing setup returned None")
    except Exception as e:
        logger.warning(f"⚠️ Failed to setup tracing: {e}")

# Add correlation middleware (must be first to set correlation ID)
app.add_middleware(CorrelationMiddleware)

# Add IP capture middleware (after FastAPIInstrumentor, captures IP for all spans)
if TRACING_AVAILABLE:
    app.add_middleware(IPCaptureMiddleware)

# Add authentication/authorization middleware (after correlation, before logging)
from middleware.auth_middleware_gateway import AuthGatewayMiddleware
app.add_middleware(AuthGatewayMiddleware)

# Add request logging middleware (after correlation middleware)
app.add_middleware(RequestLoggingMiddleware)

# Add response interceptor middleware to mark errors on spans
# This MUST be added first so it runs last (FastAPI middleware runs in reverse order)
# This ensures it runs after all other middleware and can mark errors on the final response
class ErrorMarkingMiddleware(BaseHTTPMiddleware):
    """Middleware to mark spans as errors for 4xx/5xx responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Mark span as error if status code indicates error
        # This runs after all other middleware, so it can mark errors on responses from auth middleware
        if TRACING_AVAILABLE and trace and response.status_code >= 400:
            current_span = trace.get_current_span()
            if current_span:
                # Set error status - this is what makes it appear in red in Jaeger
                current_span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                current_span.set_attribute("http.status_code", response.status_code)
                current_span.set_attribute("error", True)
                
                # Set specific error types
                if response.status_code == 401:
                    current_span.set_attribute("error.type", "authentication_error")
                    # Try to extract error message from response body if available
                    try:
                        if hasattr(response, 'body'):
                            body_str = response.body.decode('utf-8') if isinstance(response.body, bytes) else str(response.body)
                            if 'AUTHENTICATION_REQUIRED' in body_str or 'Invalid or expired token' in body_str:
                                current_span.set_attribute("error.message", "Authentication required or token invalid")
                    except Exception:
                        pass
                elif response.status_code == 403:
                    current_span.set_attribute("error.type", "authorization_error")
                    try:
                        if hasattr(response, 'body'):
                            body_str = response.body.decode('utf-8') if isinstance(response.body, bytes) else str(response.body)
                            if 'AUTHORIZATION_FAILED' in body_str:
                                current_span.set_attribute("error.message", "Authorization failed")
                    except Exception:
                        pass
                else:
                    current_span.set_attribute("error.type", "http_error")
        
        return response

# Add this FIRST so it runs LAST (after all other middleware)
app.add_middleware(ErrorMarkingMiddleware)

# Add CORS middleware. Explicit origins allow credentials (e.g. Swagger UI on docs-manager port).
# Set CORS_ORIGINS env to comma-separated list (e.g. "https://app.example.com") or "*" for allow-all (no credentials).
_cors_origins_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_origins_env == "*":
    _cors_origins = ["*"]
    _cors_credentials = False
elif _cors_origins_env:
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    _cors_credentials = True
else:
    _cors_origins = [
        "http://localhost:8080", "http://127.0.0.1:8080",
        "http://localhost:8103", "http://127.0.0.1:8103",
        "http://localhost:3000", "http://127.0.0.1:3000",
    ]
    _cors_credentials = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)


# Global variables for connections and components
redis_client = None
http_client = None
service_registry = None
load_balancer = None
route_manager = None
health_monitor_task = None

# Alert management is now handled by alert-management-service

@app.on_event("startup")
async def startup_event():
    """Initialize connections and components on startup"""
    global http_client, route_manager
    
    try:
        # Initialize HTTP client
        http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("HTTP client initialized")
        
        # Initialize route manager (can work without Redis)
        route_manager = RouteManager(redis_client=None if not redis_client else redis_client)
        await route_manager.load_routes_from_redis()  # Try to load from Redis if available
        logger.info("Route manager initialized")
        
        logger.info("API Gateway initialized successfully (using direct service URLs)")
        
    except Exception as e:
        logger.error(f"Failed to initialize API Gateway: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections and tasks on shutdown"""
    global http_client
    
    # Close connections
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "API Gateway Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Central entry point for all microservice requests"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker health checks"""
    try:
        # Check Redis connectivity
        if redis_client:
            await redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "unhealthy"
        
        return {
            "status": "healthy",
            "service": "api-gateway-service",
            "redis": redis_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


def _get_downstream_for_task(task_type: ModelTaskTypeEnum) -> Tuple[str, str]:
    """
    Map task_type to (service_name, inference_path) for downstream call.

    This keeps Smart Model Router generic while reusing existing inference endpoints.
    """
    mapping: Dict[ModelTaskTypeEnum, Tuple[str, str]] = {
        ModelTaskTypeEnum.asr: ("asr-service", "/api/v1/asr/inference"),
        ModelTaskTypeEnum.nmt: ("nmt-service", "/api/v1/nmt/inference"),
        ModelTaskTypeEnum.tts: ("tts-service", "/api/v1/tts/inference"),
        ModelTaskTypeEnum.ocr: ("ocr-service", "/api/v1/ocr/inference"),
        ModelTaskTypeEnum.llm: ("llm-service", "/api/v1/llm/inference"),
        ModelTaskTypeEnum.transliteration: (
            "transliteration-service",
            "/api/v1/transliteration/inference",
        ),
        ModelTaskTypeEnum.language_detection: (
            "language-detection-service",
            "/api/v1/language-detection/inference",
        ),
        ModelTaskTypeEnum.speaker_diarization: (
            "speaker-diarization-service",
            "/api/v1/speaker-diarization/inference",
        ),
        ModelTaskTypeEnum.language_diarization: (
            "language-diarization-service",
            "/api/v1/language-diarization/inference",
        ),
        ModelTaskTypeEnum.audio_lang_detection: (
            "audio-lang-detection-service",
            "/api/v1/audio-lang-detection/inference",
        ),
        ModelTaskTypeEnum.ner: ("ner-service", "/api/v1/ner/inference"),
    }

    if task_type not in mapping:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_TASK",
                "message": f"Smart routing does not support task_type '{task_type.value}'",
            },
        )
    return mapping[task_type]

@app.get("/api/v1/status", tags=["Status"])
async def api_status():
    """API status endpoint - Get information about all available services"""
    return {
        "api_version": "v1",
        "status": "operational",
        "services": {
            "auth": os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081"),
            "config": os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082"),
            "metrics": os.getenv("METRICS_SERVICE_URL", "http://metrics-service:8083"),
            "telemetry": os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8084"),
            "alerting": os.getenv("ALERTING_SERVICE_URL", "http://alerting-service:8085"),
            "dashboard": os.getenv("DASHBOARD_SERVICE_URL", "http://dashboard-service:8086"),
            "asr": os.getenv("ASR_SERVICE_URL", "http://asr-service:8087"),
            "tts": os.getenv("TTS_SERVICE_URL", "http://tts-service:8088"),
            "nmt": os.getenv("NMT_SERVICE_URL", "http://nmt-service:8089"),
            "ocr": os.getenv("OCR_SERVICE_URL", "http://ocr-service:8099"),
            "transliteration": os.getenv("TRANSLITERATION_SERVICE_URL", "http://transliteration-service:8090"),
            "language-detection": os.getenv("LANGUAGE_DETECTION_SERVICE_URL", "http://language-detection-service:8090"),
            "speaker-diarization": os.getenv("SPEAKER_DIARIZATION_SERVICE_URL", "http://speaker-diarization-service:8095"),
            "language-diarization": os.getenv("LANGUAGE_DIARIZATION_SERVICE_URL", "http://language-diarization-service:8090"),
            "audio-lang-detection": os.getenv("AUDIO_LANG_DETECTION_SERVICE_URL", "http://audio-lang-detection-service:8096"),
            "model-management": os.getenv("MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8091"),
            "llm": os.getenv("LLM_SERVICE_URL", "http://llm-service:8090"),
            "pipeline": os.getenv("PIPELINE_SERVICE_URL", "http://pipeline-service:8090"),
            "multi-tenant": os.getenv("MULTI_TENANT_SERVICE_URL", "http://multi-tenant-service:8001")
        }
    }


@app.post(
    "/api/v1/smr/inference",
    tags=["Smart Routing"],
    response_model=Dict[str, Any],
)
async def smart_model_routed_inference(
    payload: SMRInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    Deterministic Smart Model Routed inference entrypoint.

    - Accepts an inference request body without serviceId (wrapped in request_body).
    - Calls Policy Engine to evaluate latency/cost/accuracy policies.
    - Fetches candidate services from Model Management for the given task_type.
    - Deterministically selects a serviceId using benchmark latency and health.
    - Injects the selected serviceId into request_body.config.serviceId.
    - Forwards the call to the appropriate downstream inference endpoint.
    """
    # Enforce authentication (same semantics as other inference endpoints)
    await ensure_authenticated_for_request(request, credentials, api_key)

    # Extract verified tenant_id from JWT token (not from request body)
    tenant_id = await get_verified_tenant_id(request)
    user_id = getattr(request.state, "user_id", None)

    # Extract and validate policy headers (prefer headers over payload.policy)
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)
    
    # Fall back to payload.policy if headers not provided
    if not latency_policy and payload.policy and payload.policy.latency:
        latency_policy = payload.policy.latency
    if not cost_policy and payload.policy and payload.policy.cost:
        cost_policy = payload.policy.cost
    if not accuracy_policy and payload.policy and payload.policy.accuracy:
        accuracy_policy = payload.policy.accuracy

    # Reuse global HTTP client and tracing
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    # Short-circuit: explicit service_id provided -> skip policy/model-management
    selected_service_id: Optional[str] = payload.service_id
    policy_result: Optional[Dict[str, Any]] = None

    if not selected_service_id:
        # Determine policy values: prioritize headers, fall back to Policy Engine
        # Check if any policy headers are provided (highest priority)
        headers_provided = latency_policy is not None or cost_policy is not None or accuracy_policy is not None
        
        actual_latency_policy: Optional[str] = None
        actual_cost_policy: Optional[str] = None
        actual_accuracy_policy: Optional[str] = None
        
        if headers_provided:
            # Headers are present: use them directly, skip Policy Engine call
            logger.info(
                "SMR: Using policy headers directly (skipping Policy Engine)",
                extra={
                    "context": {
                        "task_type": payload.task_type.value,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "latency_policy": latency_policy,
                        "cost_policy": cost_policy,
                        "accuracy_policy": accuracy_policy,
                        "decision": "header_priority",
                    }
                },
            )
            # Use header values directly
            actual_latency_policy = latency_policy
            actual_cost_policy = cost_policy
            actual_accuracy_policy = accuracy_policy
        else:
            # No headers provided: call Policy Engine to get tenant-specific policies
            logger.info(
                "SMR: No policy headers provided, calling Policy Engine for tenant policies",
                extra={
                    "context": {
                        "task_type": payload.task_type.value,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "decision": "policy_engine_lookup",
                    }
                },
            )
            
            policy_result = await call_policy_engine_for_smr(
                http_client=http_client,
                user_id=user_id,
                tenant_id=tenant_id,
                latency_policy=None,  # No headers, let Policy Engine determine from tenant
                cost_policy=None,
                accuracy_policy=None,
            )

            # Extract actual policy values from policy_result (policy engine returns tenant-specific policies)
            actual_latency_policy = policy_result.get("latency_policy")
            actual_cost_policy = policy_result.get("cost_policy")
            actual_accuracy_policy = policy_result.get("accuracy_policy")
            
            # Convert enum values to strings if needed
            if actual_latency_policy and hasattr(actual_latency_policy, 'value'):
                actual_latency_policy = actual_latency_policy.value
            if actual_cost_policy and hasattr(actual_cost_policy, 'value'):
                actual_cost_policy = actual_cost_policy.value
            if actual_accuracy_policy and hasattr(actual_accuracy_policy, 'value'):
                actual_accuracy_policy = actual_accuracy_policy.value

        # 2. Fetch candidate services for the given task_type
        candidate_services = await fetch_candidate_services_for_task(
            http_client=http_client,
            task_type=payload.task_type.value,
        )

        if not candidate_services:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "NO_CANDIDATE_SERVICES",
                    "message": "No candidate services found for the given task type.",
                },
            )

        # 3. Deterministically select best service based on policy values and benchmarks/health
        # Use the actual policy values (from headers or Policy Engine)
        selected_service = select_service_deterministically(
            candidate_services,
            preferred_language=payload.language,
            latency_policy=actual_latency_policy,
            cost_policy=actual_cost_policy,
            accuracy_policy=actual_accuracy_policy,
        )
        selected_service_id = str(selected_service.get("serviceId"))

    # 4. Inject selected serviceId into request body under config.serviceId
    body_dict = json.loads(json.dumps(payload.request_body))
    if not isinstance(body_dict, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REQUEST_BODY",
                "message": "request_body must be a JSON object.",
            },
        )

    config_obj = body_dict.get("config") or {}
    if not isinstance(config_obj, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CONFIG",
                "message": "request_body.config must be an object.",
            },
        )
    config_obj["serviceId"] = selected_service_id
    body_dict["config"] = config_obj

    # 5. Determine downstream service and inference path based on task_type
    service_name, inference_path = get_downstream_for_task(payload.task_type.value)

    # 6. Build headers (reuse auth headers helper) and proxy to downstream
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    downstream_body = json.dumps(body_dict).encode("utf-8")

    # Forward to downstream inference endpoint
    downstream_response = await proxy_to_service(
        None,
        inference_path,
        service_name,
        method="POST",
        body=downstream_body,
        headers=headers,
    )

    # Attach routing metadata in response headers for observability
    if isinstance(downstream_response, Response):
        downstream_response.headers["X-SMR-ServiceId"] = selected_service_id or ""
        if policy_result:
            downstream_response.headers["X-SMR-PolicyId"] = str(
                policy_result.get("policy_id", "")
            )
            downstream_response.headers["X-SMR-PolicyVersion"] = str(
                policy_result.get("policy_version", "")
            )
        return downstream_response

    # Fallback: ensure we always return a JSON-like object
    return {
        "detail": "Inference completed via Smart Model Router.",
        "serviceId": selected_service_id,
    }

# Authentication Endpoints (Proxy to Auth Service)

@app.post("/api/v1/auth/register", tags=["Authentication"])
async def register_user(
    body: RegisterUser,
    request: Request
):
    """Register a new user"""
    # Prepare headers without Content-Length (httpx will set it)
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ['content-length', 'host']}
    headers['Content-Type'] = 'application/json'
    
    payload = json.dumps(body.dict()).encode()
    return await proxy_to_service(
        None,
        "/api/v1/auth/register",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/login", tags=["Authentication"])
async def login_user(
    body: LoginRequestBody,
    request: Request
):
    """
    Login user. Returns access_token, refresh_token, and user object.
    For tenant admins/users, the user object includes tenant_id.
    """
    import json
    # Prepare headers without Content-Length (httpx will set it)
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ['content-length', 'host']}
    headers['Content-Type'] = 'application/json'
    
    payload = json.dumps(body.dict()).encode()
    return await proxy_to_service(
        None,
        "/api/v1/auth/login",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/logout", tags=["Authentication"])
async def logout_user(
    body: LogoutBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Logout user"""
    import json
    # Prepare headers without Content-Length (httpx will set it)
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ['content-length', 'host']}
    headers['Content-Type'] = 'application/json'
    
    payload = json.dumps(body.dict()).encode()
    return await proxy_to_service(
        None,
        "/api/v1/auth/logout",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/refresh", tags=["Authentication"])
async def refresh_token(
    body: TokenRefreshBody,
    request: Request
):
    """Refresh access token"""
    import json
    # Prepare headers without Content-Length (httpx will set it)
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ['content-length', 'host']}
    headers['Content-Type'] = 'application/json'
    
    payload = json.dumps(body.dict()).encode()
    return await proxy_to_service(
        None,
        "/api/v1/auth/refresh",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.get("/api/v1/auth/validate", tags=["Authentication"])
async def validate_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Validate token"""
    return await proxy_to_auth_service(request, "/api/v1/auth/validate")

@app.get("/api/v1/auth/me", tags=["Authentication"])
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Get current user info including tenant_id for tenant admins/users"""
    return await proxy_to_auth_service(request, "/api/v1/auth/me")

@app.put("/api/v1/auth/me", tags=["Authentication"])
async def update_current_user(
    body: UpdateUserBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """
    Update current user profile information. You can update:
    - **full_name**: Your display name
    - **phone_number**: Contact phone number
    - **timezone**: Timezone preference (e.g., 'UTC', 'America/New_York')
    - **language**: Language code (e.g., 'en', 'hi', 'ta')
    - **preferences**: JSON object for user preferences
    """
    import json
    # Filter out None values and encode as JSON
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    payload = json.dumps(update_data).encode('utf-8')
    
    # Prepare headers - preserve Authorization, remove Content-Length
    headers = build_auth_headers(request, credentials, None)
    headers['Content-Type'] = 'application/json'
    
    return await proxy_to_service(
        None,
        "/api/v1/auth/me",
        "auth-service",
        method="PUT",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/change-password", tags=["Authentication"])
async def change_password(
    body: PasswordChangeBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """
    Change the current user's password. Requires:
    - **current_password**: Your current password for verification
    - **new_password**: Your new password (minimum 8 characters, must be strong)
    - **confirm_password**: Confirmation of new password (must match new_password)
    """
    import json
    # Encode request body as JSON
    payload = json.dumps(body.dict()).encode('utf-8')
    
    # Prepare headers - preserve Authorization, remove Content-Length
    headers = build_auth_headers(request, credentials, None)
    headers['Content-Type'] = 'application/json'
    
    return await proxy_to_service(
        None,
        "/api/v1/auth/change-password",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/request-password-reset", tags=["Authentication"])
async def request_password_reset(
    body: PasswordResetRequestBody,
    request: Request
):
    """
    Request password reset email.
    
    Initiates a password reset process. The system will:
    1. Check if the email exists in the system
    2. Generate a secure reset token
    3. Send an email with a password reset link containing the token
    
    **Security Note**: The response message is the same whether the email exists or not,
    to prevent email enumeration attacks.
    
    **Parameters**:
    - **email**: The email address associated with your account
    """
    import json
    # Encode request body as JSON
    payload = json.dumps(body.dict()).encode('utf-8')
    
    # Prepare headers
    headers = {}
    for k, v in request.headers.items():
        if k.lower() not in ['content-length', 'host', 'content-type']:
            headers[k] = v
    headers['Content-Type'] = 'application/json'
    
    return await proxy_to_service(
        None,
        "/api/v1/auth/request-password-reset",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/reset-password", tags=["Authentication"])
async def reset_password(
    body: PasswordResetConfirmBody,
    request: Request
):
    """
    Reset password with token
    
    Completes the password reset process using the token received via email.
    
    **How it works**:
    1. User clicks the reset link in their email
    2. Link contains a token (in URL or entered manually)
    3. User provides: token, new password, and confirmation
    4. System validates the token and updates the password
    
    **Parameters**:
    - **token**: The password reset token received via email
    - **new_password**: Your new password (minimum 8 characters, must be strong)
    - **confirm_password**: Confirmation of new password (must match new_password)
    
    **Note**: After successful reset, all existing sessions are invalidated for security.
    """
    import json
    # Encode request body as JSON
    payload = json.dumps(body.dict()).encode('utf-8')
    
    # Prepare headers
    headers = {}
    for k, v in request.headers.items():
        if k.lower() not in ['content-length', 'host', 'content-type']:
            headers[k] = v
    headers['Content-Type'] = 'application/json'
    
    return await proxy_to_service(
        None,
        "/api/v1/auth/reset-password",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.get("/api/v1/auth/api-keys", tags=["Authentication"])
async def list_api_keys(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """List current user's API keys"""
    return await proxy_to_auth_service(request, "/api/v1/auth/api-keys")


@app.get("/api/v1/auth/api-keys/all", tags=["Authentication"])
async def list_all_api_keys_with_users(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
):
    """
    List all API keys (active + inactive) with owning user details.
    Proxies to auth-service `/api/v1/auth/api-keys/all`.
    """
    return await proxy_to_auth_service(request, "/api/v1/auth/api-keys/all")

@app.post("/api/v1/auth/api-keys", tags=["Authentication"])
async def create_api_key(
    body: APIKeyCreateBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Create API key"""
    import json
    # Convert body to dict and map userId to user_id for auth service
    body_dict = body.dict(exclude_none=True)
    if 'userId' in body_dict:
        body_dict['user_id'] = body_dict.pop('userId')
    
    # Encode request body as JSON
    payload = json.dumps(body_dict).encode('utf-8')
    
    # Prepare headers - preserve Authorization, remove Content-Length
    headers = build_auth_headers(request, credentials, None)
    headers['Content-Type'] = 'application/json'
    
    return await proxy_to_service(
        None,
        "/api/v1/auth/api-keys",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )


@app.post("/api/v1/auth/api-keys/select", tags=["Authentication"])
async def select_api_key(
    body: APIKeySelectBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Select an API key for the current user."""
    import json
    payload = json.dumps(body.dict()).encode("utf-8")

    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"

    return await proxy_to_service(
        None,
        "/api/v1/auth/api-keys/select",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.delete("/api/v1/auth/api-keys/{key_id}", tags=["Authentication"])
async def revoke_api_key(
    request: Request,
    key_id: int = Path(..., description="API key ID to revoke"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Revoke API key"""
    return await proxy_to_auth_service(request, f"/api/v1/auth/api-keys/{key_id}")


@app.patch("/api/v1/auth/api-keys/{key_id}", tags=["Authentication"])
async def update_api_key(
    key_id: int = Path(..., description="API key ID to update"),
    body: APIKeyUpdateBody = Body(...),
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
):
    """
    Update an existing API key (name, permissions).
    Proxies to auth-service `/api/v1/auth/api-keys/{key_id}`.
    """
    import json

    # Convert body to dict, dropping nulls
    body_dict = body.dict(exclude_none=True)
    payload = json.dumps(body_dict).encode("utf-8")

    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"

    return await proxy_to_service(
        None,
        f"/api/v1/auth/api-keys/{key_id}",
        "auth-service",
        method="PATCH",
        body=payload,
        headers=headers,
    )

@app.get("/api/v1/auth/oauth2/providers", tags=["OAuth2"])
async def get_oauth2_providers(
    request: Request,
    authorization: Optional[str] = Header(None, description="Optional authorization header")
):
    """
    Get available OAuth2 authentication providers.
    
    **Response:** List of OAuth2 providers (Google, GitHub, etc.) with configuration
    """
    return await proxy_to_auth_service(request, "/api/v1/auth/oauth2/providers")

@app.get("/api/v1/auth/oauth2/google/authorize", tags=["OAuth2"])
async def google_oauth_authorize(request: Request):
    """
    Initiate Google OAuth flow - redirects to Google for authentication.
    
    **Flow:** User is redirected to Google, authenticates, and Google redirects back to callback endpoint.
    """
    return await proxy_to_auth_service(request, "/api/v1/auth/oauth2/google/authorize")

@app.get("/api/v1/auth/oauth2/google/callback", tags=["OAuth2"])
async def google_oauth_callback(request: Request):
    """
    Handle Google OAuth callback - exchange authorization code for tokens and create/login user.
    
    **Flow:** Google redirects here after user authentication. The service exchanges the code for tokens,
    creates or links the user account, and redirects to frontend with JWT tokens.
    """
    return await proxy_to_auth_service(request, "/api/v1/auth/oauth2/google/callback")

@app.post("/api/v1/auth/oauth2/callback", tags=["OAuth2"])
async def oauth2_callback(
    body: OAuth2CallbackBody,
    request: Request
):
    """OAuth2 callback handler"""
    import json
    # Encode request body as JSON
    payload = json.dumps(body.dict()).encode('utf-8')
    
    # Prepare headers
    headers = {}
    for k, v in request.headers.items():
        if k.lower() not in ['content-length', 'host', 'content-type']:
            headers[k] = v
    headers['Content-Type'] = 'application/json'
    
    return await proxy_to_service(
        None,
        "/api/v1/auth/oauth2/callback",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

# Role Management Endpoints (Proxy to Auth Service)

@app.post("/api/v1/auth/roles/assign", tags=["Role Management"])
async def assign_role(
    body: AssignRoleBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Assign a role to a user (Admin only)"""
    import json
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ['content-length', 'host']}
    headers['Content-Type'] = 'application/json'
    
    payload = json.dumps(body.dict()).encode()
    return await proxy_to_service(
        None,
        "/api/v1/auth/roles/assign",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.post("/api/v1/auth/roles/remove", tags=["Role Management"])
async def remove_role(
    body: RemoveRoleBody,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Remove a role from a user (Admin only)"""
    import json
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ['content-length', 'host']}
    headers['Content-Type'] = 'application/json'
    
    payload = json.dumps(body.dict()).encode()
    return await proxy_to_service(
        None,
        "/api/v1/auth/roles/remove",
        "auth-service",
        method="POST",
        body=payload,
        headers=headers
    )

@app.get("/api/v1/auth/roles/user/{user_id}", tags=["Role Management"])
async def get_user_roles(
    user_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Get roles for a user (Admin or self)"""
    return await proxy_to_auth_service(request, f"/api/v1/auth/roles/user/{user_id}")

@app.get("/api/v1/auth/roles/list", tags=["Role Management"])
async def list_roles(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """List all available roles (Admin only)"""
    return await proxy_to_auth_service(request, "/api/v1/auth/roles/list")

@app.get("/api/v1/auth/permission/list", tags=["Role Management"])
async def get_permission_list(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """List inference permissions only (for API keys)"""
    return await proxy_to_auth_service(request, "/api/v1/auth/permission/list")

# Admin Endpoints
@app.get("/api/v1/auth/users/{user_id}", tags=["Admin"])
async def get_user_details(
    user_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """
    Get user details by user ID (Admin only)
    
    Returns user information including:
    - userid
    - username
    - emailid
    - phonenumber
    - full_name
    - is_active
    - is_verified
    - is_superuser
    - created_at
    - last_login
    """
    return await proxy_to_auth_service(request, f"/api/v1/auth/users/{user_id}")

@app.get("/api/v1/auth/permissions", tags=["Admin"])
async def get_all_permissions(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """
    Get all permissions from the permissions table (Admin only)
    
    Returns a list of all permissions with:
    - id
    - name
    - resource
    - action
    - created_at
    """
    return await proxy_to_auth_service(request, "/api/v1/auth/permissions")

@app.get("/api/v1/auth/users", tags=["Admin"])
async def get_all_users(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """
    Get all users (Admin only)
    
    Returns a list of all users with:
    - userid
    - username
    - emailid
    - phonenumber
    """
    return await proxy_to_auth_service(request, "/api/v1/auth/users")

# Alert Management Endpoints (Proxy to Alert Management Service)

@app.post("/api/v1/alerts/definitions", tags=["Alerts"])
async def create_alert_definition_endpoint(
    payload: AlertDefinitionCreate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
):
    """Create a new alert definition - proxied to alert-management-service"""
    await check_permission("alerts.create", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/alerts/definitions",
        "alert-management-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/alerts/definitions", tags=["Alerts"])
async def list_alert_definitions_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    enabled_only: bool = Query(False, description="Only return enabled alerts")
):
    """List alert definitions - proxied to alert-management-service"""
    await check_permission("alerts.read", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key)
    return await proxy_to_service(
        request,
        "/alerts/definitions",
        "alert-management-service",
        headers=headers
    )

@app.get("/api/v1/alerts/definitions/{alert_id}", tags=["Alerts"])
async def get_alert_definition_endpoint(
    alert_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Get a specific alert definition by ID - proxied to alert-management-service"""
    await check_permission("alerts.read", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    return await proxy_to_service(
        request,
        f"/alerts/definitions/{alert_id}",
        "alert-management-service",
        headers=headers
    )

@app.put("/api/v1/alerts/definitions/{alert_id}", tags=["Alerts"])
async def update_alert_definition_endpoint(
    alert_id: int,
    payload: AlertDefinitionUpdate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Update an alert definition - proxied to alert-management-service"""
    await check_permission("alerts.update", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/alerts/definitions/{alert_id}",
        "alert-management-service",
        method="PUT",
        body=body,
        headers=headers
    )

@app.delete("/api/v1/alerts/definitions/{alert_id}", tags=["Alerts"])
async def delete_alert_definition_endpoint(
    alert_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Delete an alert definition - proxied to alert-management-service"""
    await check_permission("alerts.delete", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    return await proxy_to_service(
        request,
        f"/alerts/definitions/{alert_id}",
        "alert-management-service",
        headers=headers
    )

@app.patch("/api/v1/alerts/definitions/{alert_id}/enabled", tags=["Alerts"])
async def toggle_alert_definition_endpoint(
    alert_id: int,
    request: Request,
    enabled: bool = Body(..., embed=True, description="Enable or disable the alert"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Enable or disable an alert definition - proxied to alert-management-service"""
    await check_permission("alerts.update", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps({"enabled": enabled}).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/alerts/definitions/{alert_id}/enabled",
        "alert-management-service",
        method="PATCH",
        body=body,
        headers=headers
    )


@app.post("/api/v1/alerts/receivers", tags=["Alerts"])
async def create_notification_receiver_endpoint(
    payload: NotificationReceiverCreate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Create a new notification receiver - proxied to alert-management-service"""
    await check_permission("alerts.create", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/alerts/receivers",
        "alert-management-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/alerts/receivers", tags=["Alerts"])
async def list_notification_receivers_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    enabled_only: bool = Query(False, description="Only return enabled receivers")
):
    """List notification receivers - proxied to alert-management-service"""
    await check_permission("alerts.read", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key)
    return await proxy_to_service(
        request,
        "/alerts/receivers",
        "alert-management-service",
        headers=headers
    )

@app.get("/api/v1/alerts/receivers/{receiver_id}", tags=["Alerts"])
async def get_notification_receiver_endpoint(
    receiver_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Get a specific notification receiver by ID - proxied to alert-management-service"""
    await check_permission("alerts.read", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    return await proxy_to_service(
        request,
        f"/alerts/receivers/{receiver_id}",
        "alert-management-service",
        headers=headers
    )

@app.put("/api/v1/alerts/receivers/{receiver_id}", tags=["Alerts"])
async def update_notification_receiver_endpoint(
    receiver_id: int,
    payload: NotificationReceiverUpdate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Update a notification receiver - proxied to alert-management-service"""
    await check_permission("alerts.update", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/alerts/receivers/{receiver_id}",
        "alert-management-service",
        method="PUT",
        body=body,
        headers=headers
    )

@app.delete("/api/v1/alerts/receivers/{receiver_id}", tags=["Alerts"])
async def delete_notification_receiver_endpoint(
    receiver_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Delete a notification receiver - proxied to alert-management-service"""
    await check_permission("alerts.delete", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    return await proxy_to_service(
        request,
        f"/alerts/receivers/{receiver_id}",
        "alert-management-service",
        headers=headers
    )

@app.post("/api/v1/alerts/routing-rules", tags=["Alerts"])
async def create_routing_rule_endpoint(
    payload: RoutingRuleCreate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Create a new routing rule - proxied to alert-management-service"""
    await check_permission("alerts.create", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/alerts/routing-rules",
        "alert-management-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/alerts/routing-rules", tags=["Alerts"])
async def list_routing_rules_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    enabled_only: bool = Query(False, description="Only return enabled rules")
):
    """List routing rules - proxied to alert-management-service"""
    await check_permission("alerts.read", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key)
    return await proxy_to_service(
        request,
        "/alerts/routing-rules",
        "alert-management-service",
        headers=headers
    )

@app.get("/api/v1/alerts/routing-rules/{rule_id}", tags=["Alerts"])
async def get_routing_rule_endpoint(
    rule_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Get a specific routing rule by ID - proxied to alert-management-service"""
    await check_permission("alerts.read", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    return await proxy_to_service(
        request,
        f"/alerts/routing-rules/{rule_id}",
        "alert-management-service",
        headers=headers
    )

@app.put("/api/v1/alerts/routing-rules/{rule_id}", tags=["Alerts"])
async def update_routing_rule_endpoint(
    rule_id: int,
    payload: RoutingRuleUpdate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Update a routing rule - proxied to alert-management-service"""
    await check_permission("alerts.update", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/alerts/routing-rules/{rule_id}",
        "alert-management-service",
        method="PUT",
        body=body,
        headers=headers
    )

@app.delete("/api/v1/alerts/routing-rules/{rule_id}", tags=["Alerts"])
async def delete_routing_rule_endpoint(
    rule_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Delete a routing rule - proxied to alert-management-service"""
    await check_permission("alerts.delete", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    return await proxy_to_service(
        request,
        f"/alerts/routing-rules/{rule_id}",
        "alert-management-service",
        headers=headers
    )

@app.patch("/api/v1/alerts/routing-rules/timing", tags=["Alerts"])
async def update_routing_rule_timing_endpoint(
    payload: RoutingRuleTimingUpdate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)")
):
    """Update timing parameters for routing rules - proxied to alert-management-service"""
    await check_permission("alerts.update", request, credentials)
    headers = await build_alert_headers(request, credentials, api_key, organization)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_none=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/alerts/routing-rules/timing",
        "alert-management-service",
        method="PATCH",
        body=body,
        headers=headers
    )

# ASR Service Endpoints (Proxy to ASR Service)

@app.post("/api/v1/asr/transcribe", response_model=ASRInferenceResponse, tags=["ASR"])
async def transcribe_audio(
    payload: ASRInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Transcribe audio to text using ASR service (alias for /inference)"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    # Convert Pydantic model to JSON for proxy
    body = json.dumps(payload.dict()).encode()
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    return await proxy_to_service(None, "/api/v1/asr/inference", "asr-service", method="POST", body=body, headers=headers)

@app.post("/api/v1/asr/inference", response_model=ASRInferenceResponse, tags=["ASR"])
async def asr_inference(
    payload: ASRInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform batch ASR inference on audio inputs.

    If config.serviceId is omitted, Smart Model Router will select the best ASR service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json

    # Convert Pydantic model to dict for routing logic
    body_dict = payload.model_dump(mode="json", exclude_none=True)

    # Derive user/tenant context for policy evaluation
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    # Ensure serviceId via Smart Model Router if missing
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="asr",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(
        None,
        "/api/v1/asr/inference",
        "asr-service",
        method="POST",
        body=body,
        headers=headers,
    )

@app.get("/api/v1/asr/streaming/info", response_model=StreamingInfo, tags=["ASR"])
async def get_streaming_info(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get WebSocket streaming endpoint information"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/streaming/info", "asr-service", headers=headers)

@app.get("/api/v1/asr/models", tags=["ASR"])
async def get_asr_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available ASR models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/asr/models", "asr-service", headers=headers)

@app.get("/api/v1/asr/health", tags=["ASR"])
async def asr_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """ASR service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "asr-service", headers=headers)

# TTS Service Endpoints (Proxy to TTS Service)

@app.get("/api/v1/tts/health", tags=["TTS"])
async def tts_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """TTS service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "tts-service", headers=headers)

@app.get("/api/v1/tts/", tags=["TTS"])
async def tts_root(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """TTS service root endpoint"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/", "tts-service", headers=headers)

@app.get("/api/v1/tts/streaming/info", tags=["TTS"])
async def tts_streaming_info(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """TTS streaming endpoint information"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/streaming/info", "tts-service", headers=headers)

@app.post("/api/v1/tts/inference", response_model=TTSInferenceResponse, tags=["TTS"])
async def tts_inference(
    payload: TTSInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform batch TTS inference on text inputs.

    If config.serviceId is omitted, Smart Model Router will select the best TTS service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="tts",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(
        None,
        "/api/v1/tts/inference",
        "tts-service",
        method="POST",
        body=body,
        headers=headers,
    )

@app.get("/api/v1/tts/models", tags=["TTS"])
async def get_tts_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available TTS models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/tts/models", "tts-service", headers=headers)

@app.get("/api/v1/tts/voices", response_model=VoiceListResponse, tags=["TTS"])
async def get_tts_voices(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    language: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[str] = None,
    is_active: Optional[bool] = True
):
    """Get available TTS voices with optional filtering"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    # Build query parameters
    params = {}
    if language:
        params["language"] = language
    if gender:
        params["gender"] = gender
    if age:
        params["age"] = age
    if is_active is not None:
        params["is_active"] = str(is_active).lower()
    
    # Build query string
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    path = f"/api/v1/tts/voices?{query_string}" if query_string else "/api/v1/tts/voices"
    
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, path, "tts-service", headers=headers)


# Speaker Diarization Service Endpoints (Proxy to Speaker Diarization Service)

@app.get("/api/v1/speaker-diarization/health", tags=["Speaker Diarization"])
async def speaker_diarization_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Speaker Diarization service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "speaker-diarization-service", method="GET", headers=headers)


@app.post("/api/v1/speaker-diarization/inference", response_model=SpeakerDiarizationInferenceResponse, tags=["Speaker Diarization"])
async def speaker_diarization_inference(
    payload: SpeakerDiarizationInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform speaker diarization inference on one or more audio inputs.
    
    If config.serviceId is omitted, Smart Model Router will select the best service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="speaker-diarization",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    headers: Dict[str, str] = {}
    # Use build_auth_headers which automatically forwards all headers including X-Auth-Source
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(
        None, "/api/v1/speaker-diarization/inference", "speaker-diarization-service", method="POST", body=body, headers=headers
    )

# Language Diarization Service Endpoints (Proxy to Language Diarization Service)

@app.get("/api/v1/language-diarization/health", tags=["Language Diarization"])
async def language_diarization_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Language Diarization service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "language-diarization-service", method="GET", headers=headers)


@app.post("/api/v1/language-diarization/inference", response_model=LanguageDiarizationInferenceResponse, tags=["Language Diarization"])
async def language_diarization_inference(
    payload: LanguageDiarizationInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform language diarization inference on one or more audio files.
    
    If config.serviceId is omitted, Smart Model Router will select the best service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="language-diarization",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    # Use build_auth_headers which automatically forwards all headers including X-Auth-Source
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(
        None, "/api/v1/language-diarization/inference", "language-diarization-service", method="POST", body=body, headers=headers
    )

# Audio Language Detection Service Endpoints (Proxy to Audio Language Detection Service)

@app.get("/api/v1/audio-lang-detection/health", tags=["Audio Language Detection"])
async def audio_lang_detection_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Audio Language Detection service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "audio-lang-detection-service", method="GET", headers=headers)


@app.post("/api/v1/audio-lang-detection/inference", response_model=AudioLangDetectionInferenceResponse, tags=["Audio Language Detection"])
async def audio_lang_detection_inference(
    payload: AudioLangDetectionInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform audio language detection inference on one or more audio files.
    
    If config.serviceId is omitted, Smart Model Router will select the best service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    # Log incoming request for debugging
    logger.info(
        f"Received audio-lang-detection inference request - has_token={credentials is not None and credentials.credentials is not None}, has_api_key={api_key is not None}, path={request.url.path}"
    )
    
    try:
        await ensure_authenticated_for_request(request, credentials, api_key)
    except HTTPException as e:
        logger.warning(
            f"Authentication failed for audio-lang-detection inference: status={e.status_code}, detail={e.detail}, path={request.url.path}"
        )
        raise
    
    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="audio-lang-detection",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    # Use build_auth_headers which automatically forwards all headers including X-Auth-Source
    headers = build_auth_headers(request, credentials, api_key)
    
    logger.info(f"Proxying audio-lang-detection inference request to service")
    return await proxy_to_service(
        None, "/api/v1/audio-lang-detection/inference", "audio-lang-detection-service", method="POST", body=body, headers=headers
    )

@app.post("/api/v1/try-it", response_model=Dict[str, Any], tags=["Try It"])
async def try_it_inference(
    payload: TryItRequest,
    request: Request,
):
    """
    Try-It endpoint (anonymous access for NMT only).

    NOTE: All Try-It business logic (rate limiting, default service selection,
    endpoint resolution, etc.) is implemented inside nmt-service.
    API Gateway simply proxies this request to nmt-service.
    """ 
    import json
    body = json.dumps(payload.model_dump(mode="json")).encode()
    # Forward as-is to nmt-service Try-It endpoint  
    # Prepare headers without hop-by-hop and Content-Length/Host (httpx will set these)
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ["content-length", "host", "connection", "keep-alive", "transfer-encoding"]
    }
    headers["Content-Type"] = "application/json"
    # Forward to nmt-service Try-It endpoint
    return await proxy_to_service(
        None,
        "/api/v1/try-it",
        "nmt-service",
        method="POST",
        body=body,
        #headers=request.headers,
        headers=headers,
    )

# NMT Service Endpoints (Proxy to NMT Service)

@app.post("/api/v1/nmt/inference", response_model=NMTInferenceResponse, tags=["NMT"])
async def nmt_inference(
    payload: NMTInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform NMT inference.

    If config.serviceId is omitted, Smart Model Router will select the best NMT service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)

    # ------------------------------------------------------------------
    # Context-awareness fast-path for tenant-scoped requests
    # If tenant_id is present AND header "X-Context-Aware" is truthy,
    # bypass SMR/Policy Engine and call LLM inference directly.
    # ------------------------------------------------------------------
    context_aware_header = request.headers.get("X-Context-Aware")
    is_context_aware = bool(
        context_aware_header
        and context_aware_header.strip().lower() in {"1", "true", "yes", "y"}
    )

    # Log the context-aware decision
    logger.info(
        "NMT inference: context-aware header check",
        extra={
            "context": {
                "context_aware_header": context_aware_header,
                "is_context_aware": is_context_aware,
                "user_id": user_id,
                "tenant_id": tenant_id,
            }
        },
    )

    # Allow context-aware routing even without tenant_id if header is explicitly set
    if is_context_aware:
        logger.info(
            "NMT inference: context-aware routing enabled, calling translate API directly",
            extra={
                "context": {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "context_aware": context_aware_header,
                    "request_body": body_dict,
                }
            },
        )

        try:
            # Language code to full name mapping
            LANGUAGE_CODE_TO_NAME = {
                "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
                "kn": "Kannada", "ml": "Malayalam", "bn": "Bengali", "gu": "Gujarati",
                "mr": "Marathi", "pa": "Punjabi", "or": "Oriya", "as": "Assamese",
                "ur": "Urdu", "sa": "Sanskrit", "ks": "Kashmiri", "ne": "Nepali",
                "sd": "Sindhi", "kok": "Konkani", "doi": "Dogri", "mai": "Maithili",
                "brx": "Bodo", "mni": "Manipuri", "sat": "Santali", "gom": "Goan Konkani",
                "fr": "French", "es": "Spanish", "de": "German", "it": "Italian",
                "pt": "Portuguese", "ru": "Russian", "ja": "Japanese", "ko": "Korean",
                "zh": "Chinese", "ar": "Arabic", "th": "Thai", "vi": "Vietnamese"
            }
            
            # Extract input text, language configuration, and required context
            nmt_config = body_dict.get("config") or {}
            if not isinstance(nmt_config, dict):
                raise HTTPException(status_code=400, detail="config must be an object when X-Context-Aware is true")

            # When context-aware routing is enabled, config.context is required
            if "context" not in nmt_config:
                raise HTTPException(
                    status_code=400,
                    detail="config.context is required when X-Context-Aware is true",
                )
            context_value = nmt_config.get("context")

            lang_cfg = nmt_config.get("language") or {}
            source_lang_code = lang_cfg.get("sourceLanguage", "en")
            target_lang_code = lang_cfg.get("targetLanguage", "en")
            
            # Map language codes to full names
            source_language = LANGUAGE_CODE_TO_NAME.get(source_lang_code, source_lang_code.capitalize())
            target_language = LANGUAGE_CODE_TO_NAME.get(target_lang_code, target_lang_code.capitalize())
            
            # Get input text (use first input if multiple)
            input_list = body_dict.get("input", [])
            if not input_list:
                raise HTTPException(status_code=400, detail="Input text is required")
            
            # Combine all input texts or use first one
            text = " ".join([item.get("source", "") for item in input_list if item.get("source")])
            if not text:
                raise HTTPException(status_code=400, detail="Source text cannot be empty")
            
            # Prepare translate API request (include context from config)
            translate_payload = {
                "text": text,
                "source_language": source_language,
                "target_language": target_language,
                "context": context_value,
            }
            
            logger.debug(
                "NMT inference: calling translate API",
                extra={
                    "context": {
                        "translate_payload": translate_payload,
                        "endpoint": "http://13.201.75.118:8000/api/translate"
                    }
                },
            )
            
            # Call translate API directly
            # Use a local client for this request
            async with httpx.AsyncClient(timeout=30.0) as client:
                translate_response = await client.post(
                    "http://13.201.75.118:8000/api/translate",
                    json=translate_payload,
                    headers={"Content-Type": "application/json"}
                )
                
                translate_response.raise_for_status()
                translate_result = translate_response.json()
                
                # Extract translated text from response
                # Response format: {"success":true,"result":"...","model":"gpt-oss:20b"}
                translated_text = None
                
                # Try common response field names (check if key exists and value is not None/empty)
                if "translated_text" in translate_result and translate_result.get("translated_text"):
                    translated_text = str(translate_result["translated_text"])
                elif "translation" in translate_result and translate_result.get("translation"):
                    translated_text = str(translate_result["translation"])
                elif "result" in translate_result and translate_result.get("result"):
                    translated_text = str(translate_result["result"])
                elif "text" in translate_result and translate_result.get("text"):
                    translated_text = str(translate_result["text"])
                elif "output" in translate_result and translate_result.get("output"):
                    translated_text = str(translate_result["output"])
                elif isinstance(translate_result, str):
                    translated_text = translate_result
                
                if not translated_text:
                    logger.warning(
                        "Translate API response format unexpected",
                        extra={"context": {"response": translate_result}}
                    )
                    translated_text = "Translation unavailable"
            
            # Format response in NMT format
            output_list = []
            for item in input_list:
                output_list.append({
                    "source": item.get("source", ""),
                    "target": translated_text  # Use same translation for all inputs
                })
            
            response_data = {"output": output_list}
            
            downstream_response = Response(
                content=json.dumps(response_data).encode("utf-8"),
                status_code=200,
                headers={"Content-Type": "application/json"},
                media_type="application/json"
            )

            if isinstance(downstream_response, Response):
                downstream_response.headers["X-SMR-ContextAware"] = "true"
                downstream_response.headers["X-SMR-TenantId"] = tenant_id or "free_user"
                downstream_response.headers["X-SMR-ServiceType"] = "llm translate"
                # Expose the underlying LLM service identifier for observability.
                # Prefer the model name from the translate API if present; otherwise
                # fall back to a stable logical service id.
                llm_service_id = None
                if isinstance(translate_result, dict):
                    llm_service_id = str(translate_result.get("model") or "").strip() or None
                downstream_response.headers["X-SMR-ServiceId"] = llm_service_id or "llm_gptoss"
                
                # Log response status for debugging
                if downstream_response.status_code >= 400:
                    logger.warning(
                        "NMT inference: Translate API returned error status",
                        extra={
                            "context": {
                                "status_code": downstream_response.status_code,
                                "tenant_id": tenant_id,
                            }
                        },
                    )
                else:
                    logger.info(
                        "NMT inference: Translate API call successful",
                        extra={
                            "context": {
                                "source_language": source_language,
                                "target_language": target_language,
                                "text_length": len(text)
                            }
                        },
                    )

            return downstream_response
            
        except httpx.HTTPStatusError as e:
            # HTTP error from translate API
            logger.error(
                "NMT inference: Translate API returned error",
                extra={
                    "context": {
                        "status_code": e.response.status_code,
                        "response_text": e.response.text[:500] if e.response else None,
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True,
            )
            raise HTTPException(
                status_code=e.response.status_code if e.response else 500,
                detail={
                    "code": "TRANSLATE_API_ERROR",
                    "message": f"Translation service error: {e.response.text[:200] if e.response else str(e)}",
                },
            )
        except httpx.RequestError as e:
            # Network/connection error
            logger.error(
                "NMT inference: Translate API connection error",
                extra={
                    "context": {
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "TRANSLATE_API_UNAVAILABLE",
                    "message": "Translation service is temporarily unavailable. Please try again later.",
                },
            )
        except HTTPException as e:
            # Re-raise HTTP exceptions (from proxy_to_service)
            logger.error(
                "NMT inference: context-aware routing failed with HTTP exception",
                extra={
                    "context": {
                        "status_code": e.status_code,
                        "detail": e.detail,
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True,
            )
            raise
        except Exception as e:
            # Catch any other unexpected errors
            logger.error(
                "NMT inference: context-aware routing failed with unexpected error",
                extra={
                    "context": {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "CONTEXT_AWARE_ROUTING_ERROR",
                    "message": f"Context-aware routing failed: {str(e)}",
                }
            )

    # ------------------------------------------------------------------
    # Default SMR + Policy Engine flow (including free-user path)
    # This path is taken when X-Context-Aware is "no", missing, or any other value
    # ------------------------------------------------------------------
    logger.info(
        "NMT inference: using normal SMR flow (context-aware disabled or not set)",
        extra={
            "context": {
                "context_aware_header": context_aware_header,
                "user_id": user_id,
                "tenant_id": tenant_id,
            }
        },
    )
    
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(
        request
    )

    # Log incoming request for SMR flow
    logger.info(
        "NMT inference request received",
        extra={
            "context": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "latency_policy": latency_policy,
                "cost_policy": cost_policy,
                "accuracy_policy": accuracy_policy,
                "request_body": body_dict,
            }
        },
    )

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    selected_service_id, body_dict, policy_result = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="nmt",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    # Log final routing decision before calling downstream NMT
    logger.info(
        "NMT inference routing decision",
        extra={
            "context": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "selected_service_id": selected_service_id,
                "policy_result": policy_result,
                "final_request_body": body_dict,
            }
        },
    )

    body = json.dumps(body_dict).encode("utf-8")
    headers = build_auth_headers(request, credentials, api_key)
    downstream_response = await proxy_to_service(
        None,
        "/api/v1/nmt/inference",
        "nmt-service",
        method="POST",
        body=body,
        headers=headers,
    )

    # Attach SMR debug metadata in response headers for observability
    if isinstance(downstream_response, Response):
        downstream_response.headers["X-SMR-ServiceId"] = selected_service_id or ""
        # If no tenant_id in token, mark as "free_user" for observability
        downstream_response.headers["X-SMR-TenantId"] = tenant_id or "free_user"
        # Mark normal NMT SMR flow as translate
        downstream_response.headers["X-SMR-ServiceType"] = "translate"

        if policy_result:
            downstream_response.headers["X-SMR-PolicyId"] = str(
                policy_result.get("policy_id", "")
            )
            downstream_response.headers["X-SMR-PolicyVersion"] = str(
                policy_result.get("policy_version", "")
            )
        # Attach effective latency / cost / accuracy policy details as headers
        # Prefer explicit headers; if not provided, fall back to policy engine result.
        effective_latency_policy = (
            latency_policy.value if hasattr(latency_policy, "value") else latency_policy
        )
        effective_cost_policy = (
            cost_policy.value if hasattr(cost_policy, "value") else cost_policy
        )
        effective_accuracy_policy = (
            accuracy_policy.value if hasattr(accuracy_policy, "value") else accuracy_policy
        )

        if policy_result:
            # If no explicit header, use tenant-specific policy from Policy Engine
            if not effective_latency_policy:
                effective_latency_policy = policy_result.get("latency_policy")
            if not effective_cost_policy:
                effective_cost_policy = policy_result.get("cost_policy")
            if not effective_accuracy_policy:
                effective_accuracy_policy = policy_result.get("accuracy_policy")

        if effective_latency_policy:
            downstream_response.headers["X-SMR-LatencyPolicy"] = str(
                effective_latency_policy
            )
        if effective_cost_policy:
            downstream_response.headers["X-SMR-CostPolicy"] = str(
                effective_cost_policy
            )
        if effective_accuracy_policy:
            downstream_response.headers["X-SMR-AccuracyPolicy"] = str(
                effective_accuracy_policy
            )
    return downstream_response

@app.post("/api/v1/nmt/batch-translate", tags=["NMT"])
async def batch_translate(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Batch translate multiple texts using NMT service"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/nmt/batch-translate", "nmt-service", headers=headers)

@app.get("/api/v1/nmt/languages", response_model=Dict[str, Any], tags=["NMT"])
async def get_nmt_languages(
    request: Request,
    model_id: Optional[str] = Query(None, description="Model ID to get languages for"),
    service_id: Optional[str] = Query(None, description="Service ID to get languages for"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for NMT service"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    
    # Build query parameters dict
    query_params = {}
    if service_id:
        query_params["service_id"] = service_id
    elif model_id:
        query_params["model_id"] = model_id
    # If neither provided, service will default to AI4Bharat
    
    # Build path and pass params separately to avoid httpx param conflicts
    path = "/api/v1/nmt/languages"
    
    # Create a custom proxy call that handles params correctly
    return await proxy_to_service_with_params(None, path, "nmt-service", query_params, headers=headers)

@app.get("/api/v1/nmt/models", response_model=Dict[str, Any], tags=["NMT"])
async def get_nmt_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available NMT models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    return await proxy_to_service(None, "/api/v1/nmt/models", "nmt-service", headers=headers)

@app.get("/api/v1/nmt/services", response_model=Dict[str, Any], tags=["NMT"])
async def get_nmt_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available NMT services"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    return await proxy_to_service(None, "/api/v1/nmt/services", "nmt-service", headers=headers)

@app.get("/api/v1/nmt/health", tags=["NMT"])
async def nmt_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """NMT service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/nmt/health", "nmt-service", headers=headers)
# OCR Service Endpoints (Proxy to OCR Service)



@app.get("/api/v1/ocr/health", tags=["OCR"])

async def ocr_health(

    request: Request,

    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),

    api_key: Optional[str] = Security(api_key_scheme),

):

    """OCR service health check"""

    await ensure_authenticated_for_request(request, credentials, api_key)

    headers = build_auth_headers(request, credentials, api_key)

    return await proxy_to_service(None, "/health", "ocr-service", headers=headers)





@app.post("/api/v1/ocr/inference", response_model=OCRInferenceResponse, tags=["OCR"])
async def ocr_inference(
    payload: OCRInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform OCR inference on one or more images.

    If config.serviceId is omitted, Smart Model Router will select the best OCR service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)

    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="ocr",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")

    # Use build_auth_headers which automatically sets X-Auth-Source to BOTH when both JWT and API key are present
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"

    return await proxy_to_service(
        None, "/api/v1/ocr/inference", "ocr-service", method="POST", body=body, headers=headers
    )


# NER Service Endpoints (Proxy to NER Service)

@app.get("/api/v1/ner/health", tags=["NER"])
async def ner_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """NER service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "ner-service", headers=headers)


@app.post("/api/v1/ner/inference", response_model=NERInferenceResponse, tags=["NER"])
async def ner_inference(
    payload: NERInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform NER inference on one or more text inputs.

    If config.serviceId is omitted, Smart Model Router will select the best NER service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)

    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="ner",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")

    headers = build_auth_headers(request, credentials, api_key)

    result = await proxy_to_service(
        None, "/api/v1/ner/inference", "ner-service", method="POST", body=body, headers=headers
    )
    return result


# LLM Service Endpoints (Proxy to LLM Service)

@app.post("/api/v1/llm/inference", response_model=LLMInferenceResponse, tags=["LLM"])
async def llm_inference(
    payload: LLMInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform LLM inference.

    If config.serviceId is omitted, Smart Model Router will select the best LLM service
    based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)

    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(
        request
    )

    # Log incoming request for SMR flow
    logger.info(
        "LLM inference request received",
        extra={
            "context": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "latency_policy": latency_policy,
                "cost_policy": cost_policy,
                "accuracy_policy": accuracy_policy,
                "request_body": body_dict,
            }
        },
    )

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    selected_service_id, body_dict, policy_result = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="llm",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    # Log final routing decision before calling downstream LLM
    logger.info(
        "LLM inference routing decision",
        extra={
            "context": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "selected_service_id": selected_service_id,
                "policy_result": policy_result,
                "final_request_body": body_dict,
            }
        },
    )

    body = json.dumps(body_dict).encode("utf-8")
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    
    downstream_response = await proxy_to_service(
        None,
        "/api/v1/llm/inference",
        "llm-service",
        method="POST",
        body=body,
        headers=headers,
    )

    # Attach SMR debug metadata in response headers for observability
    if isinstance(downstream_response, Response):
        downstream_response.headers["X-SMR-ServiceId"] = selected_service_id or ""
        downstream_response.headers["X-SMR-TenantId"] = tenant_id or "free_user"
        if policy_result:
            downstream_response.headers["X-SMR-PolicyId"] = str(
                policy_result.get("policy_id", "")
            )
            downstream_response.headers["X-SMR-PolicyVersion"] = str(
                policy_result.get("policy_version", "")
            )

    return downstream_response


# Transliteration Service Endpoints (Proxy to Transliteration Service)

@app.post(
    "/api/v1/transliteration/inference",
    tags=["Transliteration"],
)
async def transliteration_inference(
    payload: TransliterationInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform transliteration inference.

    If config.serviceId is omitted, Smart Model Router will select the best transliteration
    service based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="transliteration",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/transliteration/inference",
        "transliteration-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/transliteration/models", tags=["Transliteration"])
async def get_transliteration_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available transliteration models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/models", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/services", tags=["Transliteration"])
async def get_transliteration_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available transliteration services"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/services", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/languages", tags=["Transliteration"])
async def get_transliteration_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for transliteration"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/languages", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/health", tags=["Transliteration"])
async def transliteration_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Transliteration service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "transliteration-service", headers=headers)

# Language Detection Service Endpoints (Proxy to Language Detection Service)

@app.post(
    "/api/v1/language-detection/inference",
    tags=["Language Detection"],
)
async def language_detection_inference(
    payload: LanguageDetectionInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform language detection inference.

    If config.serviceId is omitted, Smart Model Router will select the best language
    detection service based on Policy Engine + Model Management and inject the chosen serviceId.
    """
    # Ensure authentication/authorization with tracing spans (gateway.authenticate, gateway.authorize, etc.)
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"

    body_dict = payload.model_dump(mode="json", exclude_none=True)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = await get_verified_tenant_id(request)
    
    # Extract and validate policy headers
    latency_policy, cost_policy, accuracy_policy = extract_and_validate_policy_headers(request)

    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    _, body_dict, _ = await inject_service_id_if_missing(
        http_client=http_client,
        task_type="language-detection",
        body_dict=body_dict,
        user_id=user_id,
        tenant_id=tenant_id,
        latency_policy=latency_policy,
        cost_policy=cost_policy,
        accuracy_policy=accuracy_policy,
    )

    body = json.dumps(body_dict).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/language-detection/inference",
        "language-detection-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/language-detection/models", tags=["Language Detection"])
async def get_language_detection_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available language detection models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/models", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/languages", tags=["Language Detection"])
async def get_language_detection_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for language detection"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/languages", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/health", tags=["Language Detection"])
async def language_detection_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Language detection service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/health", "language-detection-service", headers=headers)

# Transliteration Service Endpoints (Proxy to Transliteration Service)

@app.post(
    "/api/v1/transliteration/inference",
    tags=["Transliteration"],
)
async def transliteration_inference(
    payload: TransliterationInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform transliteration inference"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(
        payload.model_dump(mode="json", exclude_none=True)
    ).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/transliteration/inference",
        "transliteration-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/transliteration/models", tags=["Transliteration"])
async def get_transliteration_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available transliteration models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/models", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/services", tags=["Transliteration"])
async def get_transliteration_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available transliteration services"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/services", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/languages", tags=["Transliteration"])
async def get_transliteration_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for transliteration"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/languages", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/health", tags=["Transliteration"])
async def transliteration_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Transliteration service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "transliteration-service", headers=headers)

# Language Detection Service Endpoints (Proxy to Language Detection Service)

@app.post(
    "/api/v1/language-detection/inference",
    tags=["Language Detection"],
)
async def language_detection_inference(
    payload: LanguageDetectionInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform language detection inference"""
    # Ensure authentication/authorization with tracing spans (gateway.authenticate, gateway.authorize, etc.)
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(
        payload.model_dump(mode="json", exclude_none=True)
    ).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/language-detection/inference",
        "language-detection-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/language-detection/models", tags=["Language Detection"])
async def get_language_detection_models(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available language detection models"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/models", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/languages", tags=["Language Detection"])
async def get_language_detection_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for language detection"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/languages", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/health", tags=["Language Detection"])
async def language_detection_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Language detection service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/health", "language-detection-service", headers=headers)

# Model Management Service Endpoints

@app.get("/api/v1/model-management/models", response_model=List[ModelViewResponse], tags=["Model Management"])
async def list_models(
    request: Request,
    task_type: Union[ModelTaskTypeEnum,None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    include_deprecated: bool = Query(True, description="Include deprecated versions. Set to false to show only ACTIVE versions."),
    model_name: Optional[str] = Query(None, description="Filter by model name. Returns all versions of models matching this name."),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the model."),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """List all registered models.

    Use include_deprecated=false to show only ACTIVE versions. Use model_name to filter by model name and get all versions. Use created_by to filter by creator.

    Access: Any authenticated user role (ADMIN, MODERATOR, USER, GUEST)."""
    headers = build_auth_headers(request, credentials, None)
    params = {
        "task_type": task_type.value if task_type else None,
        "include_deprecated": str(include_deprecated).lower()
    }
    if model_name:
        params["model_name"] = model_name
    if created_by:
        params["created_by"] = created_by
    return await proxy_to_service_with_params(
        None, 
        "/api/v1/model-management/models", 
        "model-management-service",
        params, 
        method="GET",
        headers=headers
        )



@app.get("/api/v1/model-management/models/{model_id:path}", response_model=ModelViewResponse, tags=["Model Management"])
async def get_model_get(
    model_id: str,
    request: Request,
    version: Optional[str] = Query(None, description="Optional version to get specific version"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Fetch metadata for a specific model (GET).

    If version is provided, returns that specific version. Otherwise returns the first matching model.

    Access: Any authenticated user role (ADMIN, MODERATOR, USER, GUEST)."""
    headers = build_auth_headers(request, credentials, None)
    query_params = {}
    if version:
        query_params["version"] = version
    return await proxy_to_service_with_params(
        None,
        f"/api/v1/model-management/models/{model_id}",
        "model-management-service",
        query_params,
        method="GET",
        headers=headers,
    )


@app.post("/api/v1/model-management/models/{model_id:path}", response_model=ModelViewResponse, tags=["Model Management"])
async def get_model(
    model_id: str,
    payload: Optional[ModelViewRequestWithVersion] = Body(None, description="Request body with optional version"),
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Fetch metadata for a specific model (POST). If version is provided in the request body, returns that specific version. Otherwise returns the first matching model. Requires Bearer token authentication with 'model.read' permission."""
    await check_permission("model.read", request, credentials)
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    # Use modelId from path, version from request body (if provided)
    payload_dict = {"modelId": model_id}
    if payload and payload.version:
        payload_dict["version"] = payload.version
    payload_body = json.dumps(payload_dict).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/models/{model_id}",
        "model-management-service",
        method="POST",
        body=payload_body,
        headers=headers,
    )


def require_model_permission(permission: str):
    """Dependency factory to check permission before body validation."""
    async def _check(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
    ) -> None:
        await check_permission(permission, request, credentials)
    return _check

@app.post("/api/v1/model-management/models", response_model=str, tags=["Model Management"], dependencies=[Depends(require_model_permission("model.create"))])
async def create_model(
    payload: ModelCreateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Register a new model. Requires Bearer token authentication with 'model.create' permission."""
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/model-management/models",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.patch("/api/v1/model-management/models", response_model=str, tags=["Model Management"], dependencies=[Depends(require_model_permission("model.update"))])
async def update_model(
    payload: ModelUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Update an existing model. Requires Bearer token authentication with 'model.update' permission."""
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/model-management/models",
        "model-management-service",
        method="PATCH",
        body=body,
        headers=headers,
    )


@app.delete("/api/v1/model-management/models/{uuid}", tags=["Model Management"], dependencies=[Depends(require_model_permission("model.delete"))])
async def delete_model(
    uuid: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Delete a model by ID. Requires Bearer token authentication with 'model.delete' permission."""
    headers = build_auth_headers(request, credentials, None)
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/models/{uuid}",
        "model-management-service",
        method="DELETE",
        headers=headers,
    )



@app.get("/api/v1/model-management/services", response_model=List[ServiceListResponse], tags=["Model Management"])
async def list_services(
    request: Request,
    task_type: Union[ModelTaskTypeEnum,None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    is_published: Optional[bool] = Query(None, description="Filter by publish status. True = published only, False = unpublished only, None = all services"),
    created_by: Optional[str] = Query(None, description="Filter by user ID (string) who created the service."),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """List all deployed services.

    Use created_by to filter by creator.

    Access: Any authenticated user role (ADMIN, MODERATOR, USER, GUEST)."""
    headers = build_auth_headers(request, credentials, None)
    params = {"task_type": task_type.value if task_type else None}
    if is_published is not None:
        params["is_published"] = str(is_published).lower()
    if created_by:
        params["created_by"] = created_by
    return await proxy_to_service_with_params(
        None,
        "/api/v1/model-management/services",
        "model-management-service",
        params,
        method="GET",
        headers=headers,
    )


# Note: This route is intentionally placed before the catch-all route
# It handles /api/v1/model-management/services/{service_id} for viewing service details
# Admin routes like /api/v1/model-management/services/admin/* are handled by the catch-all route
@app.post("/api/v1/model-management/services/{service_id:path}", response_model=ServiceViewResponse, tags=["Model Management"])
async def get_service_details(
    service_id: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Fetch metadata for a specific runtime service. Requires Bearer token authentication with 'service.read' permission."""
    # Exclude admin routes - they should be handled by the catch-all route.
    # Only paths whose first segment is "admin" are admin routes (e.g. "admin/add/service/policy").
    if service_id == "admin" or service_id.startswith("admin/"):
        # This is an admin route; forward to catch-all route handler
        # Extract the path after /api/v1/model-management
        full_path = request.url.path
        if full_path.startswith("/api/v1/model-management/"):
            path_after_prefix = full_path[len("/api/v1/model-management/"):]
        else:
            path_after_prefix = full_path.lstrip("/")
        # Call the catch-all handler directly (it's defined later in this file)
        return await proxy_request(request, path_after_prefix)
    
    await check_permission("service.read", request, credentials)
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    payload = json.dumps({"serviceId": service_id}).encode("utf-8")
    # Encode service_id so IDs with "/" (e.g. ai4bharat/surya-ocr-v1--gpu--t4) are one path segment for backend
    encoded_service_id = quote(service_id, safe="")
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/services/{encoded_service_id}",
        "model-management-service",
        method="POST",
        body=payload,
        headers=headers,
    )


@app.post("/api/v1/model-management/services", response_model=str, tags=["Model Management"], dependencies=[Depends(require_model_permission("service.create"))])
async def create_service_entry(
    payload: ModelManagementServiceCreateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Register a new service entry. Requires Bearer token authentication with 'service.create' permission."""
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/model-management/services",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.patch("/api/v1/model-management/services", response_model=str, tags=["Model Management"], dependencies=[Depends(require_model_permission("service.update"))])
async def update_service_entry(
    payload: ModelManagementServiceUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Update a service entry. Requires Bearer token authentication with appropriate permission."""
    # Check if this is a publish/unpublish operation (additional check after basic service.update permission)
    if hasattr(payload, 'isPublished') and payload.isPublished is not None:
        permission = "model.publish" if payload.isPublished else "model.unpublish"
        await check_permission(permission, request, credentials)
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/model-management/services",
        "model-management-service",
        method="PATCH",
        body=body,
        headers=headers,
    )


@app.delete("/api/v1/model-management/services/{uuid}", tags=["Model Management"], dependencies=[Depends(require_model_permission("service.delete"))])
async def delete_service_entry(
    uuid: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Delete a service entry. Requires Bearer token authentication with 'service.delete' permission."""
    headers = build_auth_headers(request, credentials, None)
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/services/{uuid}",
        "model-management-service",
        method="DELETE",
        headers=headers,
    )


@app.patch("/api/v1/model-management/services/{service_id}/health", response_model=str, tags=["Model Management"])
async def update_service_health(
    service_id: str,
    payload: ServiceHeartbeatRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Update the health status reported by a service."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    # Override serviceId from path parameter
    body_data = payload.model_dump(mode='json', exclude_unset=False)
    body_data["serviceId"] = service_id
    body = json.dumps(body_data).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/services/{service_id}/health",
        "model-management-service",
        method="PATCH",
        body=body,
        headers=headers,
    )


# A/B Testing Experiment Endpoints

@app.post("/api/v1/model-management/experiments", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED, tags=["A/B Testing"])
async def create_experiment(
    payload: ExperimentCreateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Create a new A/B testing experiment. Requires at least 2 variants with traffic percentages summing to 100."""
    # await check_permission("experiment.create", request, credentials)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/model-management/experiments",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.get("/api/v1/model-management/experiments", response_model=List[ExperimentListResponse], tags=["A/B Testing"])
async def list_experiments(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by experiment status"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    created_by: Optional[str] = Query(None, description="Filter by creator user ID"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """List all experiments with optional filters."""
    # await check_permission("experiment.read", request, credentials)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, None)
    params = {}
    if status:
        params["status"] = status
    if task_type:
        params["task_type"] = task_type
    if created_by:
        params["created_by"] = created_by
    return await proxy_to_service_with_params(
        None,
        "/api/v1/model-management/experiments",
        "model-management-service",
        params,
        method="GET",
        headers=headers
    )


@app.get("/api/v1/model-management/experiments/{experiment_id}", response_model=ExperimentResponse, tags=["A/B Testing"])
async def get_experiment(
    experiment_id: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Get experiment details by ID."""
    # await check_permission("experiment.read", request, credentials)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, None)
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/experiments/{experiment_id}",
        "model-management-service",
        method="GET",
        headers=headers,
    )


@app.get("/api/v1/model-management/experiments/{experiment_id}/metrics", response_model=List[ExperimentMetricsResponse], tags=["A/B Testing"])
async def get_experiment_metrics(
    experiment_id: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    aggregate: bool = Query(False, description="If true, return one row per variant with totals combined across all dates; if false, return per variant per day."),
):
    """Get metrics for an A/B experiment by ID. Default: per variant per day. Use ?aggregate=true for one row per variant (totals)."""
    headers = build_auth_headers(request, credentials, None)
    path = f"/api/v1/model-management/experiments/{experiment_id}/metrics"
    if aggregate:
        path = f"{path}?aggregate=true"
    return await proxy_to_service(
        None,
        path,
        "model-management-service",
        method="GET",
        headers=headers,
    )


@app.patch("/api/v1/model-management/experiments/{experiment_id}", response_model=ExperimentResponse, tags=["A/B Testing"])
async def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Update an experiment. Cannot update variants of a RUNNING experiment."""
    # await check_permission("experiment.update", request, credentials)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/experiments/{experiment_id}",
        "model-management-service",
        method="PATCH",
        body=body,
        headers=headers,
    )


@app.post("/api/v1/model-management/experiments/{experiment_id}/status", response_model=ExperimentResponse, tags=["A/B Testing"])
async def update_experiment_status(
    experiment_id: str,
    payload: ExperimentStatusUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """
    Update experiment status by action.
    
    Actions:
    - 'start': Start a DRAFT experiment (changes to RUNNING)
    - 'stop': Stop a RUNNING experiment (changes to COMPLETED)
    - 'pause': Pause a RUNNING experiment (changes to PAUSED)
    - 'resume': Resume a PAUSED experiment (changes to RUNNING)
    - 'cancel': Cancel a non-RUNNING experiment (changes to CANCELLED)
    
    """
    # await check_permission("experiment.update", request, credentials)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, None)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/experiments/{experiment_id}/status",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.delete("/api/v1/model-management/experiments/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["A/B Testing"])
async def delete_experiment(
    experiment_id: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Delete an experiment. Cannot delete a RUNNING experiment. Stop it first."""
    # await check_permission("experiment.delete", request, credentials)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, None)
    return await proxy_to_service(
        None,
        f"/api/v1/model-management/experiments/{experiment_id}",
        "model-management-service",
        method="DELETE",
        headers=headers,
    )


@app.post("/api/v1/model-management/experiments/select-variant", response_model=ExperimentVariantSelectionResponse, tags=["A/B Testing"])
async def select_experiment_variant(
    payload: ExperimentVariantSelectionRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Select an experiment variant for a given request. This endpoint is used by services to determine which variant to route a request to."""
    # await ensure_authenticated_for_request(request, credentials, api_key)  # Commented out - no permission requirements for A/B testing
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/api/v1/model-management/experiments/select-variant",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


# Pipeline Service Endpoints (Proxy to Pipeline Service)

@app.post("/api/v1/pipeline/inference", response_model=PipelineInferenceResponse, tags=["Pipeline"])
async def pipeline_inference(
    payload: PipelineInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Execute pipeline inference (e.g., Speech-to-Speech translation)"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    # Convert Pydantic model to JSON for proxy
    body = json.dumps(payload.dict()).encode()
    headers = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    return await proxy_to_service(None, "/api/v1/pipeline/inference", "pipeline-service", method="POST", body=body, headers=headers)

@app.get("/api/v1/pipeline/info", response_model=PipelineInfo, tags=["Pipeline"])
async def get_pipeline_info(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get pipeline service information"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    return await proxy_to_service(None, "/api/v1/pipeline/info", "pipeline-service", headers=headers)

@app.get("/api/v1/pipeline/health", tags=["Pipeline"])
async def pipeline_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Pipeline service health check"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "pipeline-service", headers=headers)

# Feature Flag Service Endpoints (Proxy to Config Service)

@app.post("/api/v1/feature-flags/evaluate", response_model=FeatureFlagEvaluationResponse, tags=["Feature Flags"])
async def evaluate_feature_flag(
    payload: FeatureFlagEvaluationRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Evaluate a single feature flag. Supports boolean, string, integer, float, and object (dict) flag types."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    body = json.dumps(payload.dict()).encode()
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/feature-flags/evaluate", "config-service", method="POST", body=body, headers=headers)

@app.post("/api/v1/feature-flags/evaluate/boolean", response_model=BooleanEvaluationResponse, tags=["Feature Flags"])
async def evaluate_boolean_feature_flag(
    payload: FeatureFlagEvaluationRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Evaluate a boolean feature flag. Returns a simple boolean value indicating if the flag is enabled."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    body = json.dumps(payload.dict()).encode()
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/feature-flags/evaluate/boolean", "config-service", method="POST", body=body, headers=headers)

@app.post("/api/v1/feature-flags/evaluate/bulk", response_model=BulkEvaluationResponse, tags=["Feature Flags"])
async def bulk_evaluate_feature_flags(
    payload: BulkEvaluationRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Bulk evaluate multiple feature flags. Evaluates all specified flags in parallel and returns results as a dictionary."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    body = json.dumps(payload.dict()).encode()
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/feature-flags/evaluate/bulk", "config-service", method="POST", body=body, headers=headers)

@app.get("/api/v1/feature-flags/{name}", response_model=FeatureFlagResponse, tags=["Feature Flags"])
async def get_feature_flag(
    name: str,
    request: Request,
    environment: Optional[str] = Query(None, description="Environment name"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get feature flag by name from Unleash. Retrieves flag details from Unleash API (cached in Redis)."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    # Use default environment if not provided (config service will also default, but we pass it for consistency)
    env = environment or os.getenv("UNLEASH_ENVIRONMENT", "development")
    # Build query string with required parameters
    from urllib.parse import urlencode
    query_params = {"environment": env}
    query_string = urlencode(query_params)
    path_with_params = f"/api/v1/feature-flags/{name}?{query_string}"
    return await proxy_to_service(None, path_with_params, "config-service", method="GET", headers=headers)

# NOTE: config-service exposes list endpoint at "/api/v1/feature-flags/" (trailing slash).
# We expose the same trailing-slash route to avoid downstream 307 redirects to http://config-service:8082/...
@app.get("/api/v1/feature-flags/", response_model=FeatureFlagListResponse, tags=["Feature Flags"])
async def list_feature_flags(
    request: Request,
    environment: Optional[str] = Query(None, description="Environment name"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """List feature flags from Unleash. Returns paginated list of feature flags from Unleash (cached in Redis)."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    # Use default environment if not provided (config service will also default, but we pass it for consistency)
    env = environment or os.getenv("UNLEASH_ENVIRONMENT", "development")
    # Build query string with required parameters
    from urllib.parse import urlencode
    query_params = {"environment": env, "limit": str(limit), "offset": str(offset)}
    query_string = urlencode(query_params)
    path_with_params = f"/api/v1/feature-flags/?{query_string}"
    return await proxy_to_service(None, path_with_params, "config-service", method="GET", headers=headers)


# Backwards-compatible no-trailing-slash route: redirect to gateway (not config-service)
@app.get("/api/v1/feature-flags", include_in_schema=False)
async def list_feature_flags_redirect(request: Request):
    """Redirect /api/v1/feature-flags -> /api/v1/feature-flags/ (preserve query string)."""
    url = str(request.url)
    if "?" in url:
        base, qs = url.split("?", 1)
        target = f"{base}/?{qs}"
    else:
        target = f"{url}/"
    return RedirectResponse(url=target, status_code=307)

@app.post("/api/v1/feature-flags/sync", response_model=SyncResponse, tags=["Feature Flags"])
async def sync_feature_flags(
    request: Request,
    environment: Optional[str] = Query(None, description="Environment name"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Refresh feature flags cache from Unleash (admin). Invalidates Redis cache and fetches fresh data from Unleash API."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    # Use default environment if not provided (config service will also default, but we pass it for consistency)
    env = environment or os.getenv("UNLEASH_ENVIRONMENT", "development")
    # Build query string with required parameters
    from urllib.parse import urlencode
    query_params = {"environment": env}
    query_string = urlencode(query_params)
    path_with_params = f"/api/v1/feature-flags/sync?{query_string}"
    return await proxy_to_service(None, path_with_params, "config-service", method="POST", headers=headers)

# Protected Endpoints (Require Authentication)

@app.get("/api/v1/protected/status")
async def protected_status(request: Request):
    """Protected status endpoint"""
    user = await auth_middleware.require_auth(request)
    return {
        "message": "This is a protected endpoint",
        "user": user,
        "timestamp": time.time()
    }

@app.get("/api/v1/protected/profile")
async def get_user_profile(request: Request):
    """Get user profile (requires authentication)"""
    user = await auth_middleware.require_auth(request)
    return {
        "user_id": user.get("user_id") or user.get("sub"),
        "username": user.get("username"),
        "permissions": user.get("permissions", []),
        "message": "User profile data would be fetched here"
    }


# Multi-Tenant Endpoints (Proxy to Multi-Tenant Service)

@app.post("/api/v1/multi-tenant/admin/register/tenant", response_model=TenantRegisterResponse, tags=["Multi-Tenant"], status_code=201)
async def register_tenant(
    payload: TenantRegisterRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Register a new tenant"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/register/tenant",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.post("/api/v1/multi-tenant/admin/register/users", response_model=UserRegisterResponse, tags=["Multi-Tenant"], status_code=201)
async def register_user_for_multi_tenant(
    payload: UserRegisterRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Register a new user for a tenant"""
    
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/register/users",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.patch("/api/v1/multi-tenant/admin/update/tenants/status", response_model=TenantStatusUpdateResponse, tags=["Multi-Tenant"])
async def update_tenant_status(
    payload: TenantStatusUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Update tenant status"""
    
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/update/tenants/status",
        "multi-tenant-service",
        method="PATCH",
        body=body,
        headers=headers
    )

@app.patch("/api/v1/multi-tenant/admin/update/tenant", response_model=TenantUpdateResponse, tags=["Multi-Tenant"])
async def update_tenant(
    payload: TenantUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Update tenant information including organization_name, contact_email, domain,
    requested_quotas, and usage_quota. Supports partial updates - only provided
    fields will be updated.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/update/tenant",
        "multi-tenant-service",
        method="PATCH",
        body=body,
        headers=headers
    )

@app.delete("/api/v1/multi-tenant/admin/delete/user", response_model=TenantUserDeleteResponse, tags=["Multi-Tenant"])
async def delete_tenant_user(
    payload: TenantUserDeleteRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Delete a tenant user"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/delete/user",
        "multi-tenant-service",
        method="DELETE",
        body=body,
        headers=headers
    )

@app.patch("/api/v1/multi-tenant/admin/update/users/status", response_model=TenantUserStatusUpdateResponse, tags=["Multi-Tenant"])
async def update_tenant_user_status(
    payload: TenantUserStatusUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Update tenant user status"""

    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/update/users/status",
        "multi-tenant-service",
        method="PATCH",
        body=body,
        headers=headers
    )


@app.patch("/api/v1/multi-tenant/admin/update/user", response_model=TenantUserUpdateResponse, tags=["Multi-Tenant"])
async def update_tenant_user_for_multi_tenant(
    payload: TenantUserUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    Update tenant user information (username, email, is_approved, role) via API Gateway.
    Supports partial updates - only provided fields will be updated.
    Role: ADMIN, USER, GUEST, MODERATOR (key-value: {"role": "USER"}).
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/update/user",
        "multi-tenant-service",
        method="PATCH",
        body=body,
        headers=headers,
    )

@app.get("/api/v1/multi-tenant/email/verify", tags=["Multi-Tenant"])
async def verify_email(
    request: Request,
    token: str = Query(..., description="Email verification token"),
):
    """
    Verify tenant email.
    
    This endpoint is PUBLIC (no authentication required) since users
    click the verification link from their email client before logging in.
    """
    return await proxy_to_service_with_params(
        request,
        "/email/verify",
        "multi-tenant-service",
        {"token": token},
        method="GET",
    )


@app.get("/api/v1/multi-tenant/admin/view/tenant",response_model=TenantViewResponse, tags=["Multi-Tenant"])
async def view_tenant(
    tenant_id: str = Query(..., description="Tenant identifier (tenant_id)"),
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    View tenant details by tenant_id via API Gateway.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    return await proxy_to_service_with_params(
        request,
        "/admin/view/tenant",
        "multi-tenant-service",
        {"tenant_id": tenant_id},
        method="GET",
        headers=headers,
    )


@app.get("/api/v1/multi-tenant/admin/view/user",response_model=TenantUserViewResponse, tags=["Multi-Tenant"])
async def view_tenant_user(
    user_id: int = Query(..., description="Auth user id for tenant user"),
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    View tenant user details by user_id via API Gateway.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    return await proxy_to_service_with_params(
        request,
        "/admin/view/user",
        "multi-tenant-service",
        {"user_id": user_id},
        method="GET",
        headers=headers,
    )

@app.get("/api/v1/multi-tenant/admin/list/tenants", response_model=ListTenantsResponse, tags=["Multi-Tenant"])
async def list_tenants(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    List all tenants with their details via API Gateway.
    Returns a list of all tenants registered in the system.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    return await proxy_to_service(
        request,
        "/admin/list/tenants",
        "multi-tenant-service",
        method="GET",
        headers=headers,
    )

@app.get("/api/v1/multi-tenant/admin/list/users", response_model=ListUsersResponse, tags=["Multi-Tenant"])
async def list_users(
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Filter users by tenant_id"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    List all tenant users across all tenants if tenant_id is not provided.
    Returns a list of all users registered under any tenant if tenant_id is provided.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"

    params: Dict[str, Any] = {}
    if tenant_id:
        params["tenant_id"] = tenant_id

    return await proxy_to_service_with_params(
        request,
        "/admin/list/users",
        "multi-tenant-service",
        params,
        method="GET",
        headers=headers,
    )

@app.post("/api/v1/multi-tenant/email/resend", response_model=TenantResendEmailVerificationResponse, tags=["Multi-Tenant"], status_code=201)
async def resend_verification_email(
    payload: TenantResendEmailVerificationRequest,
    request: Request,
):
    """
    Resend email verification (POST version).
    
    This endpoint is PUBLIC (no authentication required) since users
    need to resend verification before they can log in.
    """
    headers = {'Content-Type': 'application/json'}
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/email/resend",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )


@app.post("/api/v1/multi-tenant/admin/email/send/verification", response_model=TenantSendEmailVerificationResponse, tags=["Multi-Tenant"], status_code=201)
async def send_verification_email(
    payload: TenantSendEmailVerificationRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """
    Send the initial email verification link for a tenant.
    This email is intiated by Admin , and is different from the resend endpoint which is initiated by users.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/admin/email/send/verification",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers,
    )

@app.post("/api/v1/multi-tenant/tenant/subscriptions/add", response_model=TenantSubscriptionResponse, tags=["Multi-Tenant"], status_code=201)
async def add_tenant_subscriptions(
    payload: TenantSubscriptionAddRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Add subscriptions to a tenant"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key) 
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/tenant/subscriptions/add",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.post("/api/v1/multi-tenant/tenant/subscriptions/remove", response_model=TenantSubscriptionResponse, tags=["Multi-Tenant"])
async def remove_tenant_subscriptions(
    payload: TenantSubscriptionRemoveRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Remove subscriptions from a tenant"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/tenant/subscriptions/remove",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )


@app.post(
    "/api/v1/multi-tenant/user/subscriptions/add",
    response_model=UserSubscriptionResponse,
    tags=["Multi-Tenant"],
    status_code=201,
)
async def add_user_subscriptions(
    payload: UserSubscriptionAddRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Add subscriptions to a tenant user."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/user/subscriptions/add",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.post(
    "/api/v1/multi-tenant/user/subscriptions/remove",
    response_model=UserSubscriptionResponse,
    tags=["Multi-Tenant"],
)
async def remove_user_subscriptions(
    payload: UserSubscriptionRemoveRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Remove subscriptions from a tenant user."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload.model_dump(mode="json", exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/user/subscriptions/remove",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers,
    )

@app.post("/api/v1/multi-tenant/register/services", response_model=ServiceResponse, tags=["Multi-Tenant"], status_code=201)
async def register_service(
    payload: ServiceCreateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Register a new service"""
    
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/register/services",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.post("/api/v1/multi-tenant/update/services", response_model=ServiceUpdateResponse, tags=["Multi-Tenant"], status_code=201)
async def update_service(
    payload: ServiceUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Update a service"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/update/services",
        "multi-tenant-service",
        method="POST",
        body=body,
        headers=headers
    )

@app.get("/api/v1/multi-tenant/list/services", response_model=ListServicesResponse, tags=["Multi-Tenant"])
async def list_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """List all services"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    return await proxy_to_service(
        request,
        "/list/services",
        "multi-tenant-service",
        method="GET",
        headers=headers
    )

@app.get("/api/v1/multi-tenant/resolve/tenant/from/user/{user_id}", tags=["Multi-Tenant"])
async def resolve_tenant_from_user(
    user_id: int,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Resolve tenant context from user_id.
    Used by services to get tenant schema information for routing.
    """
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers['Content-Type'] = 'application/json'
    return await proxy_to_service_with_params(
        request,
        f"/resolve/tenant/from/user",
        "multi-tenant-service",
        {"user_id": user_id},
        method="GET",
        headers=headers
    )

# ==================== Observability Endpoints ====================

@app.get("/api/v1/observability/logs/search", tags=["Observability"])
async def search_logs(
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID (admin only)"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    level: Optional[str] = Query(None, description="Filter by log level (INFO, WARN, ERROR, DEBUG)"),
    search_text: Optional[str] = Query(None, description="Search text in log messages"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format or timestamp)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format or timestamp)"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Results per page"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Search logs with filters and pagination.
    
    Requires 'logs.read' permission.
    Admin users see all logs, normal users see only their tenant's logs.
    
    The tenant_id parameter can only be used by admin users to filter logs for a specific tenant.
    If provided by a non-admin user, it will be rejected with a 403 error.
    
    Note: In production with APISIX/Kong, this endpoint may not be used as requests go directly to telemetry-service.
    This is kept for development/testing environments that still use the API gateway.
    """
    return await proxy_to_service(request, "/api/v1/telemetry/logs/search", "telemetry-service")


@app.get("/api/v1/observability/logs/aggregate", tags=["Observability"])
async def get_log_aggregations(
    request: Request,
    start_time: Optional[str] = Query(None, description="Start time (ISO format or timestamp)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format or timestamp)"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Get log aggregations and statistics.
    
    Requires 'logs.read' permission.
    Returns total logs, error count, warning count, breakdown by level and service.
    """
    return await proxy_to_service(request, "/api/v1/telemetry/logs/aggregate", "telemetry-service")


@app.get("/api/v1/observability/logs/services", tags=["Observability"])
async def get_log_services(
    request: Request,
    start_time: Optional[str] = Query(None, description="Start time (ISO format or timestamp)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format or timestamp)"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Get list of services that have logs.
    
    Requires 'logs.read' permission.
    Admin users see all services, normal users see only services registered to their tenant.
    """
    return await proxy_to_service(request, "/api/v1/telemetry/logs/services", "telemetry-service")


@app.get("/api/v1/observability/traces/search", tags=["Observability"])
async def search_traces(
    request: Request,
    service: Optional[str] = Query(None, description="Filter by service name"),
    operation: Optional[str] = Query(None, description="Filter by operation name"),
    start_time: Optional[int] = Query(None, description="Start time (microseconds since epoch)"),
    end_time: Optional[int] = Query(None, description="End time (microseconds since epoch)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of traces"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Search traces with filters.
    
    Requires 'traces.read' permission.
    Admin users see all traces, normal users see only their organization's traces.
    """
    return await proxy_to_service(request, "/api/v1/telemetry/traces/search", "telemetry-service")


@app.get("/api/v1/observability/traces/{trace_id}", tags=["Observability"])
async def get_trace_by_id(
    trace_id: str = Path(..., description="Trace ID"),
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Get a specific trace by ID.
    
    Requires 'traces.read' permission.
    Returns 404 if trace not found or not accessible.
    """
    return await proxy_to_service(request, f"/api/v1/telemetry/traces/{trace_id}", "telemetry-service")


@app.get("/api/v1/observability/traces/services", tags=["Observability"])
async def get_trace_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Get list of services that have traces.
    
    Requires 'traces.read' permission.
    """
    return await proxy_to_service(request, "/api/v1/telemetry/traces/services", "telemetry-service")


@app.get("/api/v1/observability/traces/services/{service}/operations", tags=["Observability"])
async def get_trace_operations(
    service: str = Path(..., description="Service name"),
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """
    Get list of operations for a specific service.
    
    Requires 'traces.read' permission.
    """
    return await proxy_to_service(request, f"/api/v1/telemetry/traces/services/{service}/operations", "telemetry-service")


# Helper function to proxy requests to auth service
async def proxy_to_auth_service(request: Request, path: str):
    """Proxy request to auth service"""
    auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
    
    try:
        # Prepare request body
        body = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            body = await request.body()
        
        # Forward request to auth service
        response = await http_client.request(
            method=request.method,
            url=f"{auth_service_url}{path}",
            headers=dict(request.headers),
            params=request.query_params,
            content=body,
            timeout=30.0
        )
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get('content-type')
        )
        
    except Exception as e:
        logger.error(f"Error proxying to auth service: {e}")
        error_detail = {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Auth service is temporarily unavailable. Please try again in a few minutes."
        }
        raise HTTPException(status_code=503, detail=error_detail)

# Helper function to proxy requests to any service
async def proxy_to_service(request: Optional[Request], path: str, service_name: str, method: str = "GET", body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None):
    """Proxy request to any service using direct URLs (bypassing service registry) with tracing"""
    global http_client
    
    # Direct service URL mapping (bypassing service registry)
    service_urls = {
        'auth-service': os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8081'),
        'config-service': os.getenv('CONFIG_SERVICE_URL', 'http://config-service:8082'),
        'metrics-service': os.getenv('METRICS_SERVICE_URL', 'http://metrics-service:8083'),
        'telemetry-service': os.getenv('TELEMETRY_SERVICE_URL', 'http://telemetry-service:8084'),
        'alerting-service': os.getenv('ALERTING_SERVICE_URL', 'http://alerting-service:8085'),
        'dashboard-service': os.getenv('DASHBOARD_SERVICE_URL', 'http://dashboard-service:8086'),
        'asr-service': os.getenv('ASR_SERVICE_URL', 'http://asr-service:8087'),
        'tts-service': os.getenv('TTS_SERVICE_URL', 'http://tts-service:8088'),
        'nmt-service': os.getenv('NMT_SERVICE_URL', 'http://nmt-service:8089'),
        'ocr-service': os.getenv('OCR_SERVICE_URL', 'http://ocr-service:8099'),
        'ner-service': os.getenv('NER_SERVICE_URL', 'http://ner-service:9001'),
        'transliteration-service': os.getenv('TRANSLITERATION_SERVICE_URL', 'http://transliteration-service:8090'),
        'language-detection-service': os.getenv('LANGUAGE_DETECTION_SERVICE_URL', 'http://language-detection-service:8090'),
        'speaker-diarization-service': os.getenv('SPEAKER_DIARIZATION_SERVICE_URL', 'http://speaker-diarization-service:8095'),
        'language-diarization-service': os.getenv('LANGUAGE_DIARIZATION_SERVICE_URL', 'http://language-diarization-service:8090'),
        'audio-lang-detection-service': os.getenv('AUDIO_LANG_DETECTION_SERVICE_URL', 'http://audio-lang-detection-service:8096'),
        'model-management-service': os.getenv('MODEL_MANAGEMENT_SERVICE_URL', 'http://model-management-service:8091'),
        'llm-service': os.getenv('LLM_SERVICE_URL', 'http://llm-service:8090'),
        'pipeline-service': os.getenv('PIPELINE_SERVICE_URL', 'http://pipeline-service:8090'),
        'multi-tenant-service': os.getenv('MULTI_TENANT_SERVICE_URL', 'http://multi-tenant-service:8001'),
        'alert-management-service': os.getenv('ALERT_MANAGEMENT_SERVICE_URL', 'http://alert-management-service:8098')
    }
    
    try:
        # Get service URL directly
        service_url = service_urls.get(service_name)
        if not service_url:
            raise HTTPException(status_code=503, detail=f"Service {service_name} not configured")
        
        # Prepare request body and headers
        if request is not None:
            method = request.method
            if method in ['POST', 'PUT', 'PATCH']:
                body = await request.body()
            out_headers = dict(request.headers)
            # Merge caller-built auth headers (e.g. X-Auth-Source for multi-tenant) so downstream gets correct auth mode
            if headers:
                for k, v in headers.items():
                    if k and v is not None:
                        out_headers[k] = v
            headers = out_headers
            params = request.query_params
            
            # Inject trace context if not already present
            if TRACING_AVAILABLE and inject:
                try:
                    inject(headers)
                except Exception:
                    pass
        else:
            # IMPORTANT: leave params as None so any querystring already present
            # in the URL (e.g. "/path?x=1") is not overwritten by an empty dict.
            params = None
            headers = dict(headers) if headers else {}
            if TRACING_AVAILABLE and inject:
                try:
                    inject(headers)
                except Exception:
                    pass
        
        # Forward request to service
        # Use longer timeout for LLM, shorter for other services to avoid long hangs
        if service_name == 'llm-service':
            timeout_value = 300.0
        elif service_name == 'ner-service':
            # NER needs time for Triton inference (default 30s) + processing overhead
            # Set to 60s to allow for Triton timeout + NER processing time
            timeout_value = float(os.getenv("NER_SERVICE_TIMEOUT_SECONDS", "60.0"))
        else:
            timeout_value = float(os.getenv("DEFAULT_SERVICE_TIMEOUT_SECONDS", "60.0"))
        final_url = f"{service_url}{path}"
        
        # Don't log proxy request details for successful requests - service-level logging handles this
        # Only log proxy details for errors (handled below after response)
        
        start_time = time.time()
        try:
            response = await http_client.request(
                method=method,
                url=final_url,
                headers=headers,
                params=params,
                content=body,
                follow_redirects=True,
                timeout=timeout_value
            )
            
            response_time = time.time() - start_time
            
            # Log non-2xx responses so errors appear in OpenSearch.
            if not (200 <= response.status_code < 300):
                logger.warning(
                    f"Proxy response from {service_name}: {response.status_code} in {response_time:.3f}s",
                    extra={
                        "context": {
                            "method": method,
                            "path": path,
                            "service": service_name,
                            "status_code": response.status_code,
                            "response_time_ms": round(response_time * 1000, 2),
                        }
                    }
                )
            # Log successful 2xx for alert-management so DELETE/POST/PUT to receivers/definitions/rules appear in OpenSearch
            # (alert-management-service may run locally or with plain-text logs, so gateway is the only source for these.)
            elif path.startswith("/alerts"):
                logger.info(
                    f"Proxy response from {service_name}: {response.status_code} in {response_time:.3f}s",
                    extra={
                        "context": {
                            "method": method,
                            "path": path,
                            "service": service_name,
                            "status_code": response.status_code,
                            "response_time_ms": round(response_time * 1000, 2),
                        }
                    }
                )
            
            # Don't log 403 errors here - RequestLoggingMiddleware handles all 400-series errors to avoid duplicates
            
        except httpx.ConnectError as e:
            response_time = time.time() - start_time
            # Mark span as error if tracing is available
            if TRACING_AVAILABLE and trace:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.message", str(e))
                    current_span.set_attribute("error.type", "connection_error")
            logger.error(
                f"Connection error proxying to {service_name}: {e}",
                extra={
                    "context": {
                        "method": method,
                        "path": path,
                        "service": service_name,
                        "service_url": service_url,
                        "error": "connection_error",
                        "response_time_ms": round(response_time * 1000, 2),
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=503, 
                detail={
                    "code": "SERVICE_UNAVAILABLE",
                    "message": f"{service_name.replace('-', ' ').title()} is not reachable. Please check if the service is running.",
                    "service": service_name,
                    "service_url": service_url
                }
            )
        except httpx.TimeoutException as e:
            response_time = time.time() - start_time
            # Mark span as error if tracing is available
            if TRACING_AVAILABLE and trace:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.message", str(e))
                    current_span.set_attribute("error.type", "timeout")
            logger.error(
                f"Timeout proxying to {service_name}: {e}",
                extra={
                    "context": {
                        "method": method,
                        "path": path,
                        "service": service_name,
                        "timeout": timeout_value,
                        "error": "timeout",
                        "response_time_ms": round(response_time * 1000, 2),
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=504, 
                detail={
                    "code": "SERVICE_TIMEOUT",
                    "message": f"{service_name.replace('-', ' ').title()} did not respond within {timeout_value}s. The service may be overloaded.",
                    "service": service_name
                }
            )
        except Exception as e:
            response_time = time.time() - start_time
            # Mark span as error if tracing is available
            if TRACING_AVAILABLE and trace:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.message", str(e))
            logger.error(
                f"Error proxying to {service_name}: {e}",
                extra={
                    "context": {
                        "method": method,
                        "path": path,
                        "service": service_name,
                        "service_url": service_url,
                        "error": "proxy_error",
                        "error_type": type(e).__name__,
                        "response_time_ms": round(response_time * 1000, 2),
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=503, 
                detail={
                    "code": "SERVICE_UNAVAILABLE",
                    "message": f"{service_name.replace('-', ' ').title()} is temporarily unavailable. Please try again later.",
                    "service": service_name
                }
            )
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get('content-type')
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        response_time = time.time() - start_time
        # Mark span as error if tracing is available
        if TRACING_AVAILABLE and trace:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_status(Status(StatusCode.ERROR, str(e)))
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.message", str(e))
        logger.error(
            f"Error proxying to {service_name}: {e}",
            extra={
                "context": {
                    "method": method,
                    "path": path,
                    "service": service_name,
                    "error": "proxy_error",
                    "response_time_ms": round(response_time * 1000, 2),
                }
            },
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"{service_name} temporarily unavailable")


# Helper function to proxy requests with explicit query parameters
async def proxy_to_service_with_params(
    request: Optional[Request], 
    path: str, 
    service_name: str, 
    query_params: Dict[str, str],
    method: str = "GET", 
    body: Optional[bytes] = None, 
    headers: Optional[Dict[str, str]] = None
):
    """Proxy request to service with explicit query parameters"""
    global http_client
    
    # Direct service URL mapping
    service_urls = {
        'auth-service': os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8081'),
        'config-service': os.getenv('CONFIG_SERVICE_URL', 'http://config-service:8082'),
        'metrics-service': os.getenv('METRICS_SERVICE_URL', 'http://metrics-service:8083'),
        'telemetry-service': os.getenv('TELEMETRY_SERVICE_URL', 'http://telemetry-service:8084'),
        'alerting-service': os.getenv('ALERTING_SERVICE_URL', 'http://alerting-service:8085'),
        'dashboard-service': os.getenv('DASHBOARD_SERVICE_URL', 'http://dashboard-service:8086'),
        'asr-service': os.getenv('ASR_SERVICE_URL', 'http://asr-service:8087'),
        'tts-service': os.getenv('TTS_SERVICE_URL', 'http://tts-service:8088'),
        'nmt-service': os.getenv('NMT_SERVICE_URL', 'http://nmt-service:8089'),
        'ocr-service': os.getenv('OCR_SERVICE_URL', 'http://ocr-service:8099'),
        'ner-service': os.getenv('NER_SERVICE_URL', 'http://ner-service:9001'),
        'speaker-diarization-service': os.getenv('SPEAKER_DIARIZATION_SERVICE_URL', 'http://speaker-diarization-service:8095'),
        'language-diarization-service': os.getenv('LANGUAGE_DIARIZATION_SERVICE_URL', 'http://language-diarization-service:8090'),
        'audio-lang-detection-service': os.getenv('AUDIO_LANG_DETECTION_SERVICE_URL', 'http://audio-lang-detection-service:8096'),
        'ocr-service': os.getenv('OCR_SERVICE_URL', 'http://ocr-service:8099'),
        'ner-service': os.getenv('NER_SERVICE_URL', 'http://ner-service:9001'),
        'model-management-service': os.getenv('MODEL_MANAGEMENT_SERVICE_URL', 'http://model-management-service:8091'),
        'llm-service': os.getenv('LLM_SERVICE_URL', 'http://llm-service:8090'),
        'pipeline-service': os.getenv('PIPELINE_SERVICE_URL', 'http://pipeline-service:8090'),
        'multi-tenant-service': os.getenv('MULTI_TENANT_SERVICE_URL', 'http://multi-tenant-service:8001')
    }
    
    try:
        service_url = service_urls.get(service_name)
        if not service_url:
            raise HTTPException(status_code=503, detail=f"Service {service_name} not configured")
        
        # Prepare headers
        if headers is None:
            headers = {}
        
        # Use provided query_params directly, filtering out None values
        params = {k: v for k, v in (query_params or {}).items() if v is not None}
        
        # Forward request to service
        timeout_value = 300.0
        response = await http_client.request(
            method=method,
            url=f"{service_url}{path}",
            headers=headers,
            params=params,
            content=body,
            follow_redirects=True,
            timeout=timeout_value
        )
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get('content-type')
        )
        
    except Exception as e:
        logger.error(f"Error proxying to {service_name}: {e}")
        error_detail = {
            "code": "SERVICE_UNAVAILABLE",
            "message": f"{service_name.replace('-', ' ').title()} is temporarily unavailable. Please try again in a few minutes."
        }
        raise HTTPException(status_code=503, detail=error_detail)

@app.api_route("/{path:path}", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
async def proxy_request(request: Request, path: str):
    """Catch-all route handler for request forwarding with tracing"""
    global service_registry, load_balancer, route_manager, http_client
    
    start_time = time.time()
    correlation_id = request.headers.get('X-Correlation-ID', generate_correlation_id())
    request_id = generate_correlation_id()
    
    try:
        # Create main proxy span FIRST (as child of FastAPI auto-instrumented span)
        # All other spans will be children of this
        # Get tracer dynamically to ensure it's available
        tracer_instance = get_tracer()
        span_context = tracer_instance.start_as_current_span("gateway.proxy") if tracer_instance else nullcontext()
        try:
            with span_context as proxy_span:
                if proxy_span:
                    proxy_span.set_attribute("gateway.path", f"/{path}")
                    proxy_span.set_attribute("gateway.method", request.method)
                    proxy_span.set_attribute("gateway.correlation_id", correlation_id)
                    proxy_span.set_attribute("gateway.request_id", request_id)
                
                # Create span for route resolution (child of proxy span)
                route_span_context = tracer_instance.start_as_current_span("gateway.resolve_route") if tracer_instance else nullcontext()
                with route_span_context as route_span:
                    if route_span:
                        route_span.set_attribute("gateway.path", f"/{path}")
                        route_span.set_attribute("gateway.method", request.method)
                    
                    # Determine target service
                    # Use the full request path for route matching, not just the captured path parameter
                    full_request_path = request.url.path
                    service_name = await route_manager.get_service_for_path(full_request_path)
                    
                    if route_span:
                        if service_name:
                            route_span.set_attribute("gateway.service_resolved", service_name)
                            route_span.set_attribute("gateway.resolution_result", "success")
                            route_span.set_status(Status(StatusCode.OK))
                        else:
                            route_span.set_attribute("gateway.resolution_result", "not_found")
                            route_span.set_status(Status(StatusCode.ERROR, "Service not found"))
                    
                    if not service_name:
                        raise HTTPException(status_code=404, detail=f"No service found for path: /{path}")
                
                # Update proxy span with service name
                if proxy_span:
                    proxy_span.set_attribute("gateway.service", service_name)
                    proxy_span.set_attribute("service.name", service_name)
                
                # Create span for service selection (child of proxy span)
                select_span_context = tracer_instance.start_as_current_span("gateway.select_instance") if tracer_instance else nullcontext()
                with select_span_context as select_span:
                    if select_span:
                        select_span.set_attribute("gateway.service", service_name)
                        select_span.set_attribute("gateway.load_balancer_available", load_balancer is not None)

                    # Fallback to direct service URLs if load_balancer is not available
                    if load_balancer is None:
                        if select_span:
                            select_span.set_attribute("gateway.selection_method", "direct_fallback")
                            select_span.set_status(Status(StatusCode.OK))
                        logger.debug(f"Using direct service URL fallback for {service_name}")
                        # Strip the route prefix from path before forwarding
                        route_prefix = None
                        for route_pref, svc_name in route_manager.routes.items():
                            if svc_name == service_name and full_request_path.startswith(route_pref):
                                route_prefix = route_pref
                                break
                        
                        if route_prefix:
                            # Model-management and llm-service expect full path /api/v1/... (same as gateway)
                            services_full_path = ("model-management-service", "llm-service")
                            service_path = full_request_path if service_name in services_full_path else (full_request_path[len(route_prefix):] or "/")
                        else:
                            service_path = full_request_path
                        return await proxy_to_service(request, service_path, service_name)

                    # Select healthy instance
                    instance_info = await load_balancer.select_instance(service_name)

                    if not instance_info:
                        if select_span:
                            select_span.set_attribute("gateway.selection_result", "no_healthy_instances")
                            select_span.set_status(Status(StatusCode.ERROR, "No healthy instances"))
                        raise HTTPException(status_code=503, detail=f"No healthy instances available for service: {service_name}")
                    
                    instance_id, instance_url = instance_info
                    
                    if select_span:
                        select_span.set_attribute("gateway.instance_id", instance_id)
                        select_span.set_attribute("gateway.instance_url", instance_url)
                        select_span.set_attribute("gateway.selection_result", "success")
                        select_span.set_status(Status(StatusCode.OK))
                
                # Update proxy span with instance info
                if proxy_span:
                    proxy_span.set_attribute("gateway.instance_id", instance_id)
                    proxy_span.set_attribute("gateway.instance_url", instance_url)
                    proxy_span.set_attribute("service.instance", instance_id)
                
                # Prepare forwarding headers (includes trace context injection)
                headers = prepare_forwarding_headers(request, correlation_id, request_id)
                
                # Ensure Content-Type is set for POST/PUT/PATCH requests
                if request.method in ['POST', 'PUT', 'PATCH']:
                    if 'Content-Type' not in headers or not headers.get('Content-Type'):
                        headers['Content-Type'] = 'application/json'
                
                # Strip the route prefix from path before forwarding
                route_prefix = None
                for route_pref, svc_name in route_manager.routes.items():
                    if svc_name == service_name and full_request_path.startswith(route_pref):
                        route_prefix = route_pref
                        break
                
                if route_prefix:
                    # Model-management and llm-service expect full path /api/v1/... (same as gateway)
                    services_full_path = ("model-management-service", "llm-service")
                    service_path = full_request_path if service_name in services_full_path else (full_request_path[len(route_prefix):] or "/")
                else:
                    service_path = full_request_path
                
                # Prepare request body
                body = None
                if request.method in ['POST', 'PUT', 'PATCH']:
                    body = await request.body()
                    # Log body size and content for debugging
                    if body:
                        logger.info(f"Forwarding {len(body)} bytes of body for {request.method} {service_path}")
                        try:
                            body_preview = body.decode('utf-8')[:200] if len(body) > 0 else ""
                            logger.debug(f"Body preview: {body_preview}")
                        except:
                            pass
                    else:
                        logger.warning(f"No body found for {request.method} request to {service_path}")
                
                # Create child span for request preparation
                prep_span_context = tracer_instance.start_as_current_span("gateway.prepare_request") if tracer_instance else nullcontext()
                with prep_span_context as prep_span:
                    if prep_span:
                        prep_span.set_attribute("gateway.headers_prepared", len(headers))
                        prep_span.set_attribute("gateway.body_size", len(body) if body else 0)
                
                # Create child span for HTTP request
                http_span_context = tracer_instance.start_as_current_span("gateway.http_request") if tracer_instance else nullcontext()
                http_start_time = time.time()
                with http_span_context as http_span:
                    if http_span:
                        http_span.set_attribute("http.method", request.method)
                        http_span.set_attribute("http.url", f"{instance_url}{service_path}")
                        http_span.set_attribute("http.target", service_path)
                        http_span.set_attribute("service.name", service_name)
                        http_span.set_attribute("service.instance", instance_id)
                    
                    # Forward request
                    # Log request details for debugging
                    logger.warning(f"🔍 Proxying {request.method} request to {service_name}")
                    logger.warning(f"🔍 Full request path: {full_request_path}")
                    logger.warning(f"🔍 Service path after stripping: {service_path}")
                    logger.warning(f"🔍 Target URL: {instance_url}{service_path}")
                    if body:
                        body_str = body[:200].decode('utf-8', errors='ignore') if len(body) > 0 else 'empty'
                        logger.warning(f"🔍 Request body size: {len(body)} bytes, preview: {body_str}")
                    else:
                        logger.warning(f"🔍 No body for {request.method} request to {service_path}")
                    
                    response = await http_client.request(
                        method=request.method,
                        url=f"{instance_url}{service_path}",
                        headers=headers,
                        params=request.query_params,
                        content=body,
                        timeout=30.0
                    )
                    
                    # Update HTTP span with response info
                    if http_span:
                        http_time = (time.time() - http_start_time) * 1000
                        http_span.set_attribute("http.status_code", response.status_code)
                        http_span.set_attribute("http.response_time_ms", round(http_time, 2))
                        http_span.set_attribute("http.response_size", len(response.content) if hasattr(response, 'content') else 0)
                        if response.status_code >= 400:
                            http_span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                        else:
                            http_span.set_status(Status(StatusCode.OK))
                
                # Calculate total response time
                response_time = time.time() - start_time
                
                # Create child span for response processing
                resp_span_context = tracer_instance.start_as_current_span("gateway.process_response") if tracer_instance else nullcontext()
                with resp_span_context as resp_span:
                    if resp_span:
                        resp_span.set_attribute("http.status_code", response.status_code)
                        resp_span.set_attribute("gateway.response_time_ms", round(response_time * 1000, 2))
                
                # Update proxy span with response info
                if proxy_span:
                    # service_path is already computed above in the http_span context
                    proxy_span.set_attribute("http.status_code", response.status_code)
                    proxy_span.set_attribute("http.url", f"{instance_url}{service_path}")
                    proxy_span.set_attribute("response.time_ms", round(response_time * 1000, 2))
                    proxy_span.set_attribute("gateway.total_time_ms", round(response_time * 1000, 2))
                    
                    # Add user context if available
                    user_id = getattr(request.state, "user_id", None)
                    if user_id:
                        proxy_span.set_attribute("gateway.user_id", str(user_id))
                    
                    if response.status_code >= 400:
                        proxy_span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                    else:
                        proxy_span.set_status(Status(StatusCode.OK))
                
                # Mark main FastAPI span as error if response status is error
                if TRACING_AVAILABLE and trace and response.status_code >= 400:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                        current_span.set_attribute("http.status_code", response.status_code)
                        current_span.set_attribute("error", True)
                        current_span.set_attribute("error.message", f"Downstream service returned {response.status_code}")
                
                # Update load balancer metrics
                await service_registry.update_health(service_name, instance_id, True, response_time)
                
                # Log request
                log_request(request.method, f"/{path}", service_name, instance_id, response_time, response.status_code)
                
                # Mark that this response came from a downstream service (so RequestLoggingMiddleware knows not to log 500+)
                # This prevents duplicate logging when service returns 500+ errors
                request.state.downstream_response = True
                request.state.downstream_status_code = response.status_code
                
                # Don't log 403 errors here - RequestLoggingMiddleware handles all 400-series errors to avoid duplicates
                
                # Prepare response headers
                response_headers = {}
                for header_name, header_value in response.headers.items():
                    if not is_hop_by_hop_header(header_name):
                        response_headers[header_name] = header_value
                
                # Add correlation headers to response
                response_headers['X-Correlation-ID'] = correlation_id
                response_headers['X-Request-ID'] = request_id
                
                # Return response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=response.headers.get('content-type')
                )
                
        except httpx.HTTPStatusError as e:
            response_time = time.time() - start_time
            
            # Extract context for logging
            user_id = getattr(request.state, "user_id", None)
            
            # Mark that this error came from a downstream service response (so RequestLoggingMiddleware knows not to log 500+)
            # This prevents duplicate logging when service returns 500+ errors
            request.state.downstream_response = True
            request.state.downstream_status_code = e.response.status_code
            
            # Mark proxy span as error
            if proxy_span:
                proxy_span.set_status(Status(StatusCode.ERROR, str(e)))
                proxy_span.set_attribute("http.status_code", e.response.status_code)
                proxy_span.set_attribute("error", True)
                proxy_span.set_attribute("error.type", "HTTPStatusError")
                proxy_span.set_attribute("error.message", str(e))
                if user_id:
                    proxy_span.set_attribute("gateway.user_id", str(user_id))
            
            # Mark main FastAPI span as error
            if TRACING_AVAILABLE and trace:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.set_attribute("http.status_code", e.response.status_code)
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPStatusError")
                    current_span.set_attribute("error.message", str(e))
                    if service_name:
                        current_span.set_attribute("gateway.service", service_name)
                    if instance_id:
                        current_span.set_attribute("gateway.instance_id", instance_id)
                    if correlation_id:
                        current_span.set_attribute("gateway.correlation_id", correlation_id)
                    if user_id:
                        current_span.set_attribute("gateway.user_id", str(user_id))
            
            # Don't log 500+ errors here - they are logged at service level to avoid duplicates
            # The response will still be returned to the client with the correct status code
            # For 400-series errors, RequestLoggingMiddleware will handle logging
            if e.response.status_code < 500:
                logger.error(
                    f"HTTP error forwarding request to {service_name}: {e}",
                    extra={
                        "context": {
                            "method": request.method,
                            "path": path,
                            "service": service_name,
                            "status_code": e.response.status_code,
                            "error": "http_error",
                            "correlation_id": correlation_id,
                            "response_time_ms": round(response_time * 1000, 2),
                        }
                    }
                )
            
            # Update health status for the instance
            if 'instance_id' in locals() and 'service_name' in locals():
                await service_registry.update_health(service_name, instance_id, False, response_time)
            
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
            
        except httpx.RequestError as e:
            response_time = time.time() - start_time
            
            # Mark that this is a gateway-generated error (service unavailable)
            # RequestLoggingMiddleware will log this since it's not a downstream response
            # Store service info for better logging context
            request.state.gateway_error_service = service_name
            request.state.gateway_error_type = "service_unavailable"
            
            # Mark proxy span and main FastAPI span as error
            if TRACING_AVAILABLE and trace:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.message", str(e))
            
            # Don't log here - RequestLoggingMiddleware will handle logging for gateway-generated errors
            
            # Update health status for the instance
            if 'instance_id' in locals() and 'service_name' in locals():
                await service_registry.update_health(service_name, instance_id, False, response_time)
            
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        
    except HTTPException as e:
        response_time = time.time() - start_time
        
        # Extract context for logging
        service_name = locals().get('service_name', None)
        instance_id = locals().get('instance_id', None)
        user_id = getattr(request.state, "user_id", None)
        
        # Mark main FastAPI span as error for HTTP exceptions
        if TRACING_AVAILABLE and trace:
            current_span = trace.get_current_span()
            if current_span and e.status_code >= 400:
                current_span.set_status(Status(StatusCode.ERROR, f"HTTP {e.status_code}: {e.detail}"))
                current_span.set_attribute("http.status_code", e.status_code)
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.type", "HTTPException")
                current_span.set_attribute("error.message", str(e.detail))
                if service_name:
                    current_span.set_attribute("gateway.service", service_name)
                if instance_id:
                    current_span.set_attribute("gateway.instance_id", instance_id)
                if correlation_id:
                    current_span.set_attribute("gateway.correlation_id", correlation_id)
                if user_id:
                    current_span.set_attribute("gateway.user_id", str(user_id))
        
        # Don't log HTTP exceptions here - RequestLoggingMiddleware handles all logging
        # This prevents duplicates and ensures consistent logging format
        
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        response_time = time.time() - start_time
        
        # Extract context for logging
        service_name = locals().get('service_name', None)
        instance_id = locals().get('instance_id', None)
        user_id = getattr(request.state, "user_id", None)
        
        # Mark main FastAPI span as error
        if TRACING_AVAILABLE and trace:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_status(Status(StatusCode.ERROR, str(e)))
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.type", type(e).__name__)
                current_span.set_attribute("error.message", str(e))
                current_span.set_attribute("http.status_code", 500)
                current_span.record_exception(e)
                if service_name:
                    current_span.set_attribute("gateway.service", service_name)
                if instance_id:
                    current_span.set_attribute("gateway.instance_id", instance_id)
                if correlation_id:
                    current_span.set_attribute("gateway.correlation_id", correlation_id)
                if user_id:
                    current_span.set_attribute("gateway.user_id", str(user_id))
        
        logger.error(
            f"Unexpected error in API Gateway forwarding request: {e}",
            extra={
                "context": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "status_code": 500,
                    "method": request.method,
                    "path": path,
                    "service": service_name,
                    "instance_id": instance_id,
                    "user_id": user_id,
                    "correlation_id": correlation_id,
                    "request_id": request_id,
                    "response_time_ms": round(response_time * 1000, 2),
                }
            },
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("SERVICE_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port)
