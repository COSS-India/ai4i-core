"""
API Gateway Service - Central entry point for all microservice requests
"""
import os
import asyncio
import logging
import uuid
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from enum import Enum
from urllib.parse import urlencode, urlparse, parse_qs
from fastapi import FastAPI, Request, HTTPException, Response, Query, Header, Path, Body, Security
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.utils import get_openapi
import redis.asyncio as redis
import httpx
from auth_middleware import auth_middleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    serviceId: str = Field(..., description="ASR service/model ID")
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
    serviceId: str = Field(..., description="Identifier for NMT service/model")
    language: NMTLanguagePair = Field(..., description="Language pair configuration")

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
    serviceId: str = Field(..., description="TTS service/model ID")
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



    serviceId: str = Field(

        ..., description="OCR service/model ID (e.g., ai4bharat/surya-ocr-v1--gpu--t4)"

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
    serviceId: str = Field(
        ..., description="NER service/model ID (e.g., Dhruva NER)"
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
    serviceId: str = Field(..., description="Identifier for transliteration service/model")
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
    serviceId: str = Field(..., description="Language detection service/model ID")


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
    serviceId: str = Field(..., description="Identifier for speaker diarization service/model")

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
    serviceId: str = Field(..., description="Identifier for language diarization service/model")

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
    serviceId: str = Field(..., description="Identifier for audio language detection service/model")

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

class ModelTaskTypeEnum(str, Enum):
    
    nmt = "nmt"
    tts = "tts"
    asr = "asr"
    llm = "llm"

class VersionStatus(str, Enum):
    """Model version status."""
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"

class ModelCreateRequest(BaseModel):
    """Request model for creating a new model."""
    modelId: str = Field(..., description="Unique model identifier")
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

class ServiceCreateRequest(BaseModel):
    """Request model for creating a new service."""
    serviceId: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Service name")
    serviceDescription: str = Field(..., description="Service description")
    hardwareDescription: str = Field(..., description="Hardware description")
    publishedOn: int = Field(..., description="Publication timestamp")
    modelId: str = Field(..., description="Associated model identifier")
    modelVersion: str = Field(..., description="Model version")
    endpoint: str = Field(..., description="Service endpoint URL")
    api_key: str = Field(..., description="API key for the service")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")
    isPublished: Optional[bool] = Field(False, description="Whether the service is published (defaults to false)")

class LanguagePair(BaseModel):
    """Language pair configuration."""
    sourceLanguage: Optional[str] = Field(None, description="Source language code")
    sourceScriptCode: Optional[str] = Field("", description="Source script code")
    targetLanguage: str = Field(..., description="Target language code")
    targetScriptCode: Optional[str] = Field("", description="Target script code")

class ServiceUpdateRequest(BaseModel):
    """Request model for updating an existing service. Only serviceId is required, all other fields are optional for partial updates."""
    serviceId: str = Field(..., description="Unique service identifier")
    name: Optional[str] = Field(None, description="Service name")
    serviceDescription: Optional[str] = Field(None, description="Service description")
    hardwareDescription: Optional[str] = Field(None, description="Hardware description")
    publishedOn: Optional[int] = Field(None, description="Publication timestamp")
    modelId: Optional[str] = Field(None, description="Associated model identifier")
    modelVersion: Optional[str] = Field(None, description="Model version")
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
    name: str = Field(..., description="Service name")
    serviceDescription: str = Field(..., description="Service description")
    hardwareDescription: str = Field(..., description="Hardware description")
    publishedOn: int = Field(..., description="Publication timestamp")
    modelId: str = Field(..., description="Associated model identifier")
    endpoint: Optional[str] = Field(None, description="Service endpoint URL")
    api_key: Optional[str] = Field(None, description="API key for the service")
    healthStatus: Optional[ServiceStatus] = Field(None, description="Health status")
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = Field(None, description="Benchmark data")
    task: Task = Field(..., description="Task type")
    languages: List[dict] = Field(..., description="Supported languages")

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

class AssignRoleBody(BaseModel):
    user_id: int = Field(..., description="ID of the user to assign role to")
    role_name: str = Field(..., description="Name of the role to assign (e.g., 'USER', 'ADMIN', 'MODERATOR', 'GUEST')")

class RemoveRoleBody(BaseModel):
    user_id: int = Field(..., description="ID of the user to remove role from")
    role_name: str = Field(..., description="Name of the role to remove")

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
        "name": "Status",
        "description": "Service status and health check endpoints.",
    },
]

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
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
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
        "asr", "nmt", "tts", "pipeline", "llm", "ner", "ocr", "transliteration",
        "language-detection", "speaker-diarization", "language-diarization", "audio-lang-detection"
    ]
    for svc in services_requiring_both:
        if f"/api/v1/{svc}" in path:
            return True
    return False

async def validate_api_key_permissions(api_key: str, service: str, action: str) -> None:
    """Call auth-service to validate API key permissions."""
    url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                json={"api_key": api_key, "service": service, "action": action},
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")

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
                    "error": "INVALID_API_KEY",
                    "message": error_message
                }
            )
    except HTTPException:
        raise
    except Exception:
        # If body can't be parsed but status was 200, allow
        pass

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

async def ensure_authenticated_for_request(req: Request, credentials: Optional[HTTPAuthorizationCredentials], api_key: Optional[str]) -> None:
    """Enforce authentication - require BOTH Bearer token AND API key for all services."""
    
    requires_both = requires_both_auth_and_api_key(req)
    
    if requires_both:
        # For ASR, NMT, TTS, Pipeline, LLM: require BOTH Bearer token AND API key
        token = credentials.credentials if credentials else None
        
        # Check if Bearer token is missing
        if not token:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "AUTHENTICATION_REQUIRED",
                    "message": "Authorization token is required."
                },
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate Bearer token
        payload = await auth_middleware.verify_token(token)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "AUTHENTICATION_REQUIRED",
                    "message": "Invalid or expired token"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Check if API key is missing
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "API_KEY_MISSING",
                    "message": "API key is required to access this service."
                }
            )
        
        # Validate API key permissions
        service, action = determine_service_and_action(req)
        try:
            await validate_api_key_permissions(api_key, service, action)
        except HTTPException as e:
            # Re-raise with the specific error message from auth-service
            raise
    else:
        # For other services: existing logic (either Bearer OR API key)
        auth_source = (req.headers.get("x-auth-source") or "").upper()
        use_api_key = api_key is not None and auth_source == "API_KEY"

        if use_api_key:
            # Validate API key permissions via auth-service
            service, action = determine_service_and_action(req)
            await validate_api_key_permissions(api_key, service, action)
            return

        # Default: require Bearer token
        if not credentials or not credentials.credentials:
            raise HTTPException(
                status_code=401, 
                detail="Not authenticated: Bearer access token required (Authorization header)",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = credentials.credentials
        payload = await auth_middleware.verify_token(token)
        
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )

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
    
    return headers

def log_request(method: str, path: str, service: str, instance: str, duration: float, status_code: int) -> None:
    """Log request details for observability"""
    logger.info(
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
            "pipeline": os.getenv("PIPELINE_SERVICE_URL", "http://pipeline-service:8090")
        }
    }

# Authentication Endpoints (Proxy to Auth Service)

@app.post("/api/v1/auth/register", tags=["Authentication"])
async def register_user(
    body: RegisterUser,
    request: Request
):
    """Register a new user"""
    import json
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
    """Login user"""
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
    """Get current user info"""
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
    """List API keys"""
    return await proxy_to_auth_service(request, "/api/v1/auth/api-keys")

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

@app.delete("/api/v1/auth/api-keys/{key_id}", tags=["Authentication"])
async def revoke_api_key(
    request: Request,
    key_id: int = Path(..., description="API key ID to revoke"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Revoke API key"""
    return await proxy_to_auth_service(request, f"/api/v1/auth/api-keys/{key_id}")

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
    """List all available permission names"""
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
    """Perform batch ASR inference on audio inputs"""
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
    """Perform batch TTS inference on text inputs"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    # Convert Pydantic model to JSON for proxy
    body = json.dumps(payload.dict()).encode()
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers['Authorization'] = f"Bearer {credentials.credentials}"
    if api_key:
        headers['X-API-Key'] = api_key
    return await proxy_to_service(None, "/api/v1/tts/inference", "tts-service", method="POST", body=body, headers=headers)

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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "speaker-diarization-service", method="GET", headers=headers)


@app.post("/api/v1/speaker-diarization/inference", response_model=SpeakerDiarizationInferenceResponse, tags=["Speaker Diarization"])
async def speaker_diarization_inference(
    payload: SpeakerDiarizationInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform speaker diarization inference on one or more audio inputs"""
    ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body = json.dumps(payload.dict()).encode()
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers["Authorization"] = f"Bearer {credentials.credentials}"
    if api_key:
        headers["X-API-Key"] = api_key
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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "language-diarization-service", method="GET", headers=headers)


@app.post("/api/v1/language-diarization/inference", response_model=LanguageDiarizationInferenceResponse, tags=["Language Diarization"])
async def language_diarization_inference(
    payload: LanguageDiarizationInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform language diarization inference on one or more audio files"""
    ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body = json.dumps(payload.dict()).encode()
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers["Authorization"] = f"Bearer {credentials.credentials}"
    if api_key:
        headers["X-API-Key"] = api_key
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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "audio-lang-detection-service", method="GET", headers=headers)


@app.post("/api/v1/audio-lang-detection/inference", response_model=AudioLangDetectionInferenceResponse, tags=["Audio Language Detection"])
async def audio_lang_detection_inference(
    payload: AudioLangDetectionInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform audio language detection inference on one or more audio files"""
    ensure_authenticated_for_request(request, credentials, api_key)
    import json

    body = json.dumps(payload.dict()).encode()
    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers["Authorization"] = f"Bearer {credentials.credentials}"
    if api_key:
        headers["X-API-Key"] = api_key
    return await proxy_to_service(
        None, "/api/v1/audio-lang-detection/inference", "audio-lang-detection-service", method="POST", body=body, headers=headers
    )

# NMT Service Endpoints (Proxy to NMT Service)

@app.post("/api/v1/nmt/inference", response_model=NMTInferenceResponse, tags=["NMT"])
async def nmt_inference(
    payload: NMTInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform NMT inference"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    import json
    # Convert Pydantic model to JSON for proxy
    body = json.dumps(payload.dict()).encode()
    # Use build_auth_headers which automatically forwards all headers including X-Auth-Source
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/nmt/inference", "nmt-service", method="POST", body=body, headers=headers)

@app.post("/api/v1/nmt/batch-translate", tags=["NMT"])
async def batch_translate(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Batch translate multiple texts using NMT service"""
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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

    ensure_authenticated_for_request(request, credentials, api_key)

    headers = build_auth_headers(request, credentials, api_key)

    return await proxy_to_service(None, "/health", "ocr-service", headers=headers)





@app.post("/api/v1/ocr/inference", response_model=OCRInferenceResponse, tags=["OCR"])
async def ocr_inference(
    payload: OCRInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform OCR inference on one or more images"""
    ensure_authenticated_for_request(request, credentials, api_key)

    import json

    body = json.dumps(payload.dict()).encode()

    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers["Authorization"] = f"Bearer {credentials.credentials}"
    if api_key:
        headers["X-API-Key"] = api_key

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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/health", "ner-service", headers=headers)


@app.post("/api/v1/ner/inference", response_model=NERInferenceResponse, tags=["NER"])
async def ner_inference(
    payload: NERInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Perform NER inference on one or more text inputs"""
    ensure_authenticated_for_request(request, credentials, api_key)

    import json

    body = json.dumps(payload.dict()).encode()

    headers: Dict[str, str] = {}
    if credentials and credentials.credentials:
        headers["Authorization"] = f"Bearer {credentials.credentials}"
    if api_key:
        headers["X-API-Key"] = api_key

    return await proxy_to_service(
        None, "/api/v1/ner/inference", "ner-service", method="POST", body=body, headers=headers
    )


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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/models", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/services", tags=["Transliteration"])
async def get_transliteration_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available transliteration services"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/services", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/languages", tags=["Transliteration"])
async def get_transliteration_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for transliteration"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/languages", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/health", tags=["Transliteration"])
async def transliteration_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Transliteration service health check"""
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/models", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/languages", tags=["Language Detection"])
async def get_language_detection_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for language detection"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/languages", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/health", tags=["Language Detection"])
async def language_detection_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Language detection service health check"""
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/models", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/services", tags=["Transliteration"])
async def get_transliteration_services(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get available transliteration services"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/services", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/languages", tags=["Transliteration"])
async def get_transliteration_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for transliteration"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/transliteration/languages", "transliteration-service", headers=headers)

@app.get("/api/v1/transliteration/health", tags=["Transliteration"])
async def transliteration_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Transliteration service health check"""
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/models", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/languages", tags=["Language Detection"])
async def get_language_detection_languages(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Get supported languages for language detection"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/languages", "language-detection-service", headers=headers)

@app.get("/api/v1/language-detection/health", tags=["Language Detection"])
async def language_detection_health(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Language detection service health check"""
    ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service(None, "/api/v1/language-detection/health", "language-detection-service", headers=headers)

# Model Management Service Endpoints

@app.get("/api/v1/model-management/models", response_model=List[ModelViewResponse], tags=["Model Management"])
async def list_models(
    request: Request,
    task_type: Union[ModelTaskTypeEnum,None] = Query(None, description="Filter by task type (asr, nmt, tts, etc.)"),
    include_deprecated: bool = Query(True, description="Include deprecated versions. Set to false to show only ACTIVE versions."),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """List all registered models. Use include_deprecated=false to show only ACTIVE versions."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service_with_params(
        None, 
        "/services/details/list_models", 
        "model-management-service",
        {
            "task_type": task_type.value if task_type else None,
            "include_deprecated": str(include_deprecated).lower()
        }, 
        method="GET",
        headers=headers
        )



@app.get("/api/v1/model-management/models/{model_id:path}", response_model=ModelViewResponse, tags=["Model Management"])
async def get_model_get(
    model_id: str,
    request: Request,
    version: Optional[str] = Query(None, description="Optional version to get specific version"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Fetch metadata for a specific model (GET). If version is provided, returns that specific version. Otherwise returns the first matching model."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    query_params = {}
    if version:
        query_params["version"] = version
    return await proxy_to_service_with_params(
        None,
        f"/models/{model_id}",
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
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Fetch metadata for a specific model (POST). If version is provided in the request body, returns that specific version. Otherwise returns the first matching model."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    # Use modelId from path, version from request body (if provided)
    payload_dict = {"modelId": model_id}
    if payload and payload.version:
        payload_dict["version"] = payload.version
    payload_body = json.dumps(payload_dict).encode("utf-8")
    return await proxy_to_service(
        None,
        "/services/details/view_model",
        "model-management-service",
        method="POST",
        body=payload_body,
        headers=headers,
    )


@app.post("/api/v1/model-management/models", response_model=str, tags=["Model Management"])
async def create_model(
    payload: ModelCreateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Register a new model."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/services/admin/create/model",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.patch("/api/v1/model-management/models", response_model=str, tags=["Model Management"])
async def update_model(
    payload: ModelUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Update an existing model."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/services/admin/update/model",
        "model-management-service",
        method="PATCH",
        body=body,
        headers=headers,
    )


@app.delete("/api/v1/model-management/models/{uuid}", tags=["Model Management"])
async def delete_model(
    uuid: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Delete a model by ID."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service_with_params(
        None,
        "/services/admin/delete/model",
        "model-management-service",
        {"id": uuid},
        method="DELETE",
        headers=headers,
    )



@app.get("/api/v1/model-management/services/", response_model=List[ServiceListResponse], tags=["Model Management"])
async def list_services(
    request: Request,
    task_type: Union[ModelTaskTypeEnum,None] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """List all deployed services."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service_with_params(
        None, 
        "/services/details/list_services", 
        "model-management-service",
        {"task_type": task_type.value if task_type else None}, 
        method="GET", 
        headers=headers
        )


@app.post("/api/v1/model-management/services/{service_id:path}", response_model=ServiceViewResponse, tags=["Model Management"])
async def get_service_details(
    service_id: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Fetch metadata for a specific runtime service."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    payload = json.dumps({"serviceId": service_id}).encode("utf-8")
    return await proxy_to_service(
        None,
        "/services/details/view_service",
        "model-management-service",
        method="POST",
        body=payload,
        headers=headers,
    )


@app.post("/api/v1/model-management/services", response_model=str, tags=["Model Management"])
async def create_service_entry(
    payload: ServiceCreateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Register a new service entry."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=False)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/services/admin/create/service",
        "model-management-service",
        method="POST",
        body=body,
        headers=headers,
    )


@app.patch("/api/v1/model-management/services", response_model=str, tags=["Model Management"])
async def update_service_entry(
    payload: ServiceUpdateRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Update a service entry."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    headers["Content-Type"] = "application/json"
    # Use model_dump with json mode to properly serialize datetime objects
    body = json.dumps(payload.model_dump(mode='json', exclude_unset=True)).encode("utf-8")
    return await proxy_to_service(
        None,
        "/services/admin/update/service",
        "model-management-service",
        method="PATCH",
        body=body,
        headers=headers,
    )


@app.delete("/api/v1/model-management/services/{uuid}", tags=["Model Management"])
async def delete_service_entry(
    uuid: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Delete a service entry."""
    await ensure_authenticated_for_request(request, credentials, api_key)
    headers = build_auth_headers(request, credentials, api_key)
    return await proxy_to_service_with_params(
        None,
        "/services/admin/delete/service",
        "model-management-service",
        {"id": uuid},
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
        "/services/admin/health",
        "model-management-service",
        method="PATCH",
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
    ensure_authenticated_for_request(request, credentials, api_key)
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
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "permissions": user.get("permissions", []),
        "message": "User profile data would be fetched here"
    }

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
        raise HTTPException(status_code=500, detail="Auth service temporarily unavailable")

# Helper function to proxy requests to any service
async def proxy_to_service(request: Optional[Request], path: str, service_name: str, method: str = "GET", body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None):
    """Proxy request to any service using direct URLs (bypassing service registry)"""
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
        'pipeline-service': os.getenv('PIPELINE_SERVICE_URL', 'http://pipeline-service:8090')
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
            headers = dict(request.headers)
            params = request.query_params
        else:
            # IMPORTANT: leave params as None so any querystring already present
            # in the URL (e.g. "/path?x=1") is not overwritten by an empty dict.
            params = None
            if headers is None:
                headers = {}
        
        # Forward request to service (5 minute timeout for LLM service, 300s for others)
        timeout_value = 300.0 if service_name == 'llm-service' else 300.0
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
        'pipeline-service': os.getenv('PIPELINE_SERVICE_URL', 'http://pipeline-service:8090')
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
        raise HTTPException(status_code=500, detail=f"{service_name} temporarily unavailable")

@app.api_route("/{path:path}", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
async def proxy_request(request: Request, path: str):
    """Catch-all route handler for request forwarding"""
    global service_registry, load_balancer, route_manager, http_client
    
    start_time = time.time()
    correlation_id = request.headers.get('X-Correlation-ID', generate_correlation_id())
    request_id = generate_correlation_id()
    
    try:
        # Determine target service
        service_name = await route_manager.get_service_for_path(f"/{path}")
        if not service_name:
            raise HTTPException(status_code=404, detail=f"No service found for path: /{path}")
        
        # Fallback to direct service URLs if load_balancer is not available
        if load_balancer is None:
            logger.debug(f"Using direct service URL fallback for {service_name}")
            return await proxy_to_service(request, f"/{path}", service_name)
        
        # Select healthy instance
        instance_info = await load_balancer.select_instance(service_name)
        if not instance_info:
            raise HTTPException(status_code=503, detail=f"No healthy instances available for service: {service_name}")
        
        instance_id, instance_url = instance_info
        
        # Prepare forwarding headers
        headers = prepare_forwarding_headers(request, correlation_id, request_id)
        
        # Prepare request body
        body = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            body = await request.body()
        
        # Forward request
        response = await http_client.request(
            method=request.method,
            url=f"{instance_url}/{path}",
            headers=headers,
            params=request.query_params,
            content=body,
            timeout=30.0
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Update load balancer metrics
        await service_registry.update_health(service_name, instance_id, True, response_time)
        
        # Log request
        log_request(request.method, f"/{path}", service_name, instance_id, response_time, response.status_code)
        
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
        logger.error(f"HTTP error forwarding request: {e}")
        
        # Update health status for the instance
        if 'instance_id' in locals() and 'service_name' in locals():
            await service_registry.update_health(service_name, instance_id, False, response_time)
        
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
        
    except httpx.RequestError as e:
        response_time = time.time() - start_time
        logger.error(f"Request error forwarding request: {e}")
        
        # Update health status for the instance
        if 'instance_id' in locals() and 'service_name' in locals():
            await service_registry.update_health(service_name, instance_id, False, response_time)
        
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"Unexpected error forwarding request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("SERVICE_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port)
