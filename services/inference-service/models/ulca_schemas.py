"""
ULCA (ULCA-IN/ulca) request/response schemas — documentation only.

These models exist purely to generate accurate OpenAPI schemas for Swagger/
ReDoc (via openapi_extra in routes/inference.py). Routes still accept a raw
Dict[str, Any] payload and perform their own validation (each TaskService's
validate_request()) — nothing here changes runtime request handling or adds
FastAPI-level validation. Field descriptions call out where this server
accepts-but-ignores an optional ULCA field, so the docs don't overstate what
is actually enforced/honored.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Shared building blocks ───────────────────────────────────────────────────

class LanguageConfig(BaseModel):
    sourceLanguage: str = Field(..., description="ISO language code of the input")
    targetLanguage: Optional[str] = Field(
        None, description="ISO language code of the output (translation/transliteration only)"
    )
    sourceScriptCode: Optional[str] = Field(
        None, description="ISO-15924 script code (accepted; not read by this server)"
    )
    targetScriptCode: Optional[str] = Field(
        None, description="ISO-15924 script code (accepted; not read by this server)"
    )


class SentenceItem(BaseModel):
    source: str = Field(..., description="Input text")
    target: Optional[str] = Field(
        None, description="Reference/expected translation (accepted; not read by this server)"
    )


class AudioFileItem(BaseModel):
    audioContent: Optional[str] = Field(None, description="Base64-encoded audio content")
    audioUri: Optional[str] = Field(None, description="gs://, s3://, or https:// URI to the audio file")

    model_config = {"json_schema_extra": {"description": "One of audioContent or audioUri is required."}}


class ImageFileItem(BaseModel):
    imageContent: Optional[str] = Field(None, description="Base64-encoded image content")
    imageUri: Optional[str] = Field(None, description="gs://, s3://, or https:// URI to the image file")

    model_config = {"json_schema_extra": {"description": "One of imageContent or imageUri is required."}}


class TranscriptionFormat(BaseModel):
    value: Optional[str] = Field(
        "transcript",
        description="One of srt/transcript/alternatives (accepted; not read by this server)",
    )


# ── Per-task config objects ──────────────────────────────────────────────────

class TranslationConfig(BaseModel):
    """NMT and NER both use this config shape."""
    modelId: Optional[int] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    language: LanguageConfig
    inputFormat: Optional[str] = Field("raw-text", description="Accepted; not read by this server")
    outputFormat: Optional[str] = Field("raw-text", description="Accepted; not read by this server")


class TransliterationConfig(BaseModel):
    modelId: Optional[int] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    numSuggestions: Optional[int] = Field(0, description="Number of suggestions to return (word-mode only)")
    isSentence: Optional[bool] = Field(False, description="Sentence-level (true) vs word-level (false) transliteration")
    language: LanguageConfig
    inputFormat: Optional[str] = Field("raw-text", description="Accepted; not read by this server")
    outputFormat: Optional[str] = Field("raw-text", description="Accepted; not read by this server")


class LangDetectionConfig(BaseModel):
    """Shared by text and audio language-detection. ULCA defines no `language`
    field here — the task detects the language, so specifying one as input
    doesn't apply."""
    modelId: Optional[int] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    isSentence: Optional[bool] = Field(False, description="Accepted; not read by this server")
    numSuggestions: Optional[int] = Field(4, description="Accepted; not read by this server")
    inputFormat: Optional[str] = Field(None, description="Accepted; not read by this server")
    outputFormat: Optional[str] = Field(None, description="Accepted; not read by this server")


class OCRConfig(BaseModel):
    modelId: Optional[str] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    detectionLevel: Optional[str] = Field(
        "word", description="One of word/line/paragraph/page (accepted; not read by this server)"
    )
    modality: Optional[str] = Field(
        "print", description="One of print/handwritten/scenetext (accepted; not read by this server)"
    )
    language: LanguageConfig
    inputFormat: Optional[str] = Field(None, description="Accepted; not read by this server")
    outputFormat: Optional[str] = Field(None, description="Accepted; not read by this server")


class TTSConfig(BaseModel):
    modelId: Optional[str] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    language: LanguageConfig
    gender: str = Field("female", description="Voice gender")
    samplingRate: Optional[int] = Field(22050, description="Output sample rate in Hz")
    inputFormat: Optional[str] = Field("raw-text", description="Accepted; not read by this server")
    outputFormat: Optional[str] = Field(
        "wav", description="ULCA's output-format field; NOT read by this server — use audioFormat instead"
    )
    audioFormat: Optional[str] = Field(
        "wav", description="This server's own field (not in ULCA) that actually selects the output container format"
    )


class AudioConfig(BaseModel):
    modelId: Optional[str] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    language: LanguageConfig
    audioFormat: str = Field("wav", description="Required by ULCA; not read — format is auto-detected from the audio")
    channel: Optional[int] = Field(1, description="Accepted; not read by this server")
    samplingRate: Optional[int] = Field(None, description="Accepted; not read — audio is always resampled to 16kHz")
    bitsPerSample: Optional[int] = Field(None, description="Accepted; not read by this server")
    transcriptionFormat: Optional[TranscriptionFormat] = Field(None, description="Accepted; not read by this server")
    postProcessors: Optional[List[str]] = Field(None, description="Accepted; not read by this server")
    domain: Optional[List[str]] = Field(None, description="Accepted; not read by this server")
    detailed: Optional[bool] = Field(False, description="Accepted; not read by this server")
    punctuation: Optional[bool] = Field(None, description="Accepted; not read by this server")
    model: Optional[str] = Field(None, description="Accepted; not read by this server")
    encoding: Optional[str] = Field(None, description="Accepted; not read by this server")


# ── Per-task request bodies ──────────────────────────────────────────────────

class NMTRequestSchema(BaseModel):
    serviceId: str
    input: List[SentenceItem]
    config: TranslationConfig


class NERRequestSchema(BaseModel):
    """NER reuses the TranslationRequest shape per ULCA's discriminator mapping."""
    serviceId: str
    input: List[SentenceItem]
    config: TranslationConfig


class TransliterationRequestSchema(BaseModel):
    serviceId: str
    input: List[SentenceItem]
    config: TransliterationConfig


class TextLanguageDetectionRequestSchema(BaseModel):
    serviceId: str
    input: List[SentenceItem]
    config: LangDetectionConfig


class AudioLanguageDetectionRequestSchema(BaseModel):
    serviceId: str
    audio: List[AudioFileItem]
    config: LangDetectionConfig


class ASRRequestSchema(BaseModel):
    serviceId: str
    audio: List[AudioFileItem]
    config: AudioConfig


class TTSRequestSchema(BaseModel):
    serviceId: str
    input: List[SentenceItem]
    config: TTSConfig


class OCRRequestSchema(BaseModel):
    serviceId: str
    image: List[ImageFileItem]
    config: OCRConfig


# ── Response bodies for the endpoints whose shape changed in this pass ──────

class NerPredictionSchema(BaseModel):
    token: str
    tag: str
    tokenIndex: int
    tokenStartIndex: int
    tokenEndIndex: int
    score: Optional[float] = Field(None, description="Present only when the model emits a per-token confidence")


class NerOutputItemSchema(BaseModel):
    source: str
    nerPrediction: List[NerPredictionSchema]


class NerResponseSchema(BaseModel):
    taskType: str = "ner"
    output: List[NerOutputItemSchema]
    config: Optional[dict] = None


class TransliterationOutputItemSchema(BaseModel):
    source: str
    target: List[str] = Field(..., description="One entry per suggestion (always a list, even for a single result)")


class TransliterationResponseSchema(BaseModel):
    output: List[TransliterationOutputItemSchema]


class LangPredictionSchema(BaseModel):
    langCode: str
    ScriptCode: Optional[str] = None
    langScore: Optional[float] = None


class TextLangDetectionOutputItemSchema(BaseModel):
    source: str
    langPrediction: List[LangPredictionSchema]


class TextLangDetectionResponseSchema(BaseModel):
    output: List[TextLangDetectionOutputItemSchema]


class AudioLangDetectionOutputItemSchema(BaseModel):
    langPrediction: List[LangPredictionSchema]


class AudioLangDetectionResponseSchema(BaseModel):
    taskType: str = "audio-lang-detection"
    output: List[AudioLangDetectionOutputItemSchema]
    config: Optional[dict] = None


class TTSAudioItemSchema(BaseModel):
    audioContent: Optional[str] = Field(None, description="Base64-encoded synthesized audio")
    audioUri: Optional[str] = None
    audioDuration: Optional[float] = None


class TTSResponseLanguageSchema(BaseModel):
    sourceLanguage: str
    sourceScriptCode: Optional[str] = None


class TTSResponseConfigSchema(BaseModel):
    language: TTSResponseLanguageSchema
    audioFormat: str
    encoding: str = "base64"
    samplingRate: int
    audioDuration: float


class TTSResponseSchema(BaseModel):
    audio: List[TTSAudioItemSchema]
    config: TTSResponseConfigSchema
    smr_response: Optional[dict] = None
