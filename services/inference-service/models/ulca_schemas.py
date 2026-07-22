"""
ULCA (ULCA-IN/ulca) request/response schemas — documentation only.

These models exist purely to generate accurate OpenAPI schemas for Swagger/
ReDoc (via openapi_extra in routes/inference.py). Routes still accept a raw
Dict[str, Any] payload and perform their own validation (each TaskService's
validate_request()) — nothing here changes runtime request handling or adds
FastAPI-level validation. Field descriptions call out where this server
accepts-but-ignores an optional ULCA field, so the docs don't overstate what
is actually enforced/honored.

Field names, required/optional cardinality, string length limits, and enums
follow the ULCA spec exactly. `serviceId` on every request body is an
AI4Bharat/Dhruva routing extension — it selects which registered Service to
invoke and has no ULCA equivalent (raw ULCA *Request schemas carry no routing
target).
"""
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


# ── ULCA format/value enums ──────────────────────────────────────────────────

class AudioFormatEnum(str, Enum):
    wav = "wav"
    pcm = "pcm"
    mp3 = "mp3"
    flac = "flac"
    sph = "sph"


class TextFormatEnum(str, Enum):
    srt = "srt"
    transcript = "transcript"
    webvtt = "webvtt"
    alternatives = "alternatives"
    # Not in the TextFormat excerpt reviewed against, but the plain-text I/O
    # value every caller and example in this codebase (and the wider
    # AI4Bharat/Dhruva ULCA ecosystem) actually sends for NMT/NER/
    # Transliteration/LangDetection. Included as a real, accepted value
    # rather than silently rejecting the convention this server's own docs
    # have used all along.
    raw_text = "raw-text"


class ImageFormatEnum(str, Enum):
    jpeg = "jpeg"
    bmp = "bmp"
    png = "png"
    tiff = "tiff"


class TranscriptionFormatValueEnum(str, Enum):
    """ULCA TranscriptionFormat.value — note this enum has no `webvtt`,
    unlike TextFormat."""
    srt = "srt"
    transcript = "transcript"
    alternatives = "alternatives"


class DetectionLevelEnum(str, Enum):
    word = "word"
    line = "line"
    paragraph = "paragraph"
    page = "page"


class ModalityEnum(str, Enum):
    print_ = "print"
    handwritten = "handwritten"
    scenetext = "scenetext"


class ASRModelEnum(str, Enum):
    command_and_search = "command_and_search"
    phone_call = "phone_call"
    video = "video"
    default = "default"


# `inputFormat`/`outputFormat` are typed as SupportedFormats = anyOf[AudioFormat,
# TextFormat, ImageFormat] per ULCA. "raw-text" is folded into TextFormatEnum
# above so the established convention validates as a real enum member instead
# of falling back to a loose, unchecked string.
SupportedFormats = Union[AudioFormatEnum, TextFormatEnum, ImageFormatEnum]


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
    source: str = Field(..., min_length=1, description="Input text")
    target: Optional[str] = Field(
        None, min_length=1, description="Reference/expected translation (accepted; not read by this server)"
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
    value: Optional[TranscriptionFormatValueEnum] = Field(
        TranscriptionFormatValueEnum.transcript,
        description="Accepted; not read by this server",
    )


# ── Per-task config objects ──────────────────────────────────────────────────

class TranslationConfig(BaseModel):
    """NMT and NER both use this config shape."""
    modelId: Optional[int] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    language: LanguageConfig
    inputFormat: Optional[SupportedFormats] = Field(TextFormatEnum.raw_text, description="Accepted; not read by this server")
    outputFormat: Optional[SupportedFormats] = Field(TextFormatEnum.raw_text, description="Accepted; not read by this server")


class TransliterationConfig(BaseModel):
    modelId: Optional[int] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    numSuggestions: Optional[int] = Field(0, description="Number of suggestions to return (word-mode only)")
    isSentence: Optional[bool] = Field(False, description="Sentence-level (true) vs word-level (false) transliteration")
    language: LanguageConfig
    inputFormat: Optional[SupportedFormats] = Field(TextFormatEnum.raw_text, description="Accepted; not read by this server")
    outputFormat: Optional[SupportedFormats] = Field(TextFormatEnum.raw_text, description="Accepted; not read by this server")


class LangDetectionConfig(BaseModel):
    """Shared by text and audio language-detection. ULCA defines no `language`
    field here — the task detects the language, so specifying one as input
    doesn't apply."""
    modelId: Optional[int] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    isSentence: Optional[bool] = Field(False, description="Accepted; not read by this server")
    numSuggestions: Optional[int] = Field(4, description="Accepted; not read by this server")
    inputFormat: Optional[SupportedFormats] = Field(None, description="Accepted; not read by this server")
    outputFormat: Optional[SupportedFormats] = Field(None, description="Accepted; not read by this server")


class OCRConfig(BaseModel):
    modelId: Optional[str] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    detectionLevel: Optional[DetectionLevelEnum] = Field(
        DetectionLevelEnum.word, description="Accepted; not read by this server"
    )
    modality: Optional[ModalityEnum] = Field(
        ModalityEnum.print_, description="Accepted; not read by this server"
    )
    language: LanguageConfig
    inputFormat: Optional[SupportedFormats] = Field(None, description="Accepted; not read by this server")
    outputFormat: Optional[SupportedFormats] = Field(None, description="Accepted; not read by this server")


class TTSConfig(BaseModel):
    modelId: Optional[str] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    language: LanguageConfig
    gender: str = Field(..., description="Voice gender (required by ULCA)")
    samplingRate: Optional[int] = Field(22050, description="Output sample rate in Hz")
    inputFormat: Optional[SupportedFormats] = Field(TextFormatEnum.raw_text, description="Accepted; not read by this server")
    outputFormat: Optional[SupportedFormats] = Field(
        AudioFormatEnum.wav, description="ULCA's output-format field; NOT read by this server — use audioFormat instead"
    )
    audioFormat: Optional[str] = Field(
        "wav", description="This server's own field (not in ULCA) that actually selects the output container format"
    )


class AudioConfig(BaseModel):
    modelId: Optional[str] = Field(None, description="Accepted; not read — model is resolved via serviceId")
    language: LanguageConfig
    audioFormat: AudioFormatEnum = Field(
        ..., description="Required by ULCA; not read — format is auto-detected from the audio"
    )
    channel: Optional[int] = Field(1, description="Accepted; not read by this server")
    samplingRate: Optional[int] = Field(None, description="Accepted; not read — audio is always resampled to 16kHz")
    bitsPerSample: Optional[int] = Field(None, description="Accepted; not read by this server")
    transcriptionFormat: Optional[TranscriptionFormat] = Field(None, description="Accepted; not read by this server")
    postProcessors: Optional[List[str]] = Field(None, description="Accepted; not read by this server")
    domain: Optional[List[str]] = Field(None, description="Accepted; not read by this server")
    detailed: Optional[bool] = Field(False, description="Accepted; not read by this server")
    punctuation: Optional[bool] = Field(None, description="Accepted; not read by this server")
    model: Optional[ASRModelEnum] = Field(None, description="Accepted; not read by this server")
    encoding: Optional[str] = Field(None, description="Accepted; not read by this server")


# ── Per-task request bodies ──────────────────────────────────────────────────
# `serviceId` on every request below is an AI4Bharat/Dhruva routing extension,
# not part of the raw ULCA *Request schema (see module docstring).

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
    score: Optional[float] = Field(None, description="Present only when the model emits a per-token confidence")
    tokenIndex: Optional[int] = Field(None, description="Accepted per ULCA; not always emitted")
    tokenStartIndex: Optional[int] = Field(None, description="Accepted per ULCA; not always emitted")
    tokenEndIndex: Optional[int] = Field(None, description="Accepted per ULCA; not always emitted")


class NerOutputItemSchema(BaseModel):
    source: str = Field(..., min_length=1)
    nerPrediction: List[NerPredictionSchema]


class NerResponseSchema(BaseModel):
    taskType: str = "ner"
    output: List[NerOutputItemSchema]
    config: Optional[dict] = None


class TransliterationOutputItemSchema(BaseModel):
    source: str = Field(..., min_length=1)
    target: List[str] = Field(
        ..., min_length=1, description="One entry per suggestion (always a list, even for a single result)"
    )


class TransliterationResponseSchema(BaseModel):
    output: List[TransliterationOutputItemSchema]


class LangPredictionSchema(BaseModel):
    langCode: str
    ScriptCode: Optional[str] = None
    langScore: Optional[float] = None


class TextLangDetectionOutputItemSchema(BaseModel):
    source: str = Field(..., min_length=1)
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
