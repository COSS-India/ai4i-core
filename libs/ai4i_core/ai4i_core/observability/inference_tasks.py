"""Unified inference task registry for observability, tracing, and PPU.

Single source of truth for task_type ↔ service_type ↔ ppu_name mappings,
path hints, billing units, and input modalities. Import from here instead of
defining ad-hoc dictionaries in middleware, payload analysis, or services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple


@dataclass(frozen=True)
class PayloadMetricEmission:
    """Prometheus payload-metric recipe for ObservabilityMiddleware."""

    collector_method: str
    metric_field: str
    value_kwarg: str
    language_from_source: bool = False
    source_lang: bool = False
    target_lang: bool = False


@dataclass(frozen=True)
class InferenceTaskSpec:
    """Canonical definition for one inference task type."""

    task_type: str
    service_type: str
    ppu_name: str
    billing_unit: str
    path_segments: Tuple[str, ...] = ()
    emit_body_metrics: bool = True
    input_modality: Optional[str] = None  # text | audio | image
    payload_metric_emissions: Tuple[PayloadMetricEmission, ...] = ()


# Registry keyed by API task_type (uppercase). Extend this object — do not
# scatter parallel maps across modules.
INFERENCE_TASKS: Dict[str, InferenceTaskSpec] = {
    "NMT": InferenceTaskSpec(
        task_type="NMT",
        service_type="translation",
        ppu_name="nmt",
        billing_unit="characters",
        path_segments=("/translation", "/nmt", "/translate"),
        input_modality="text",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_nmt_characters", "characters", "characters",
                source_lang=True, target_lang=True,
            ),
        ),
    ),
    "TTS": InferenceTaskSpec(
        task_type="TTS",
        service_type="tts",
        ppu_name="tts",
        billing_unit="characters",
        path_segments=("/tts", "/synthesize"),
        input_modality="text",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_tts_characters", "characters", "characters",
                language_from_source=True,
            ),
        ),
    ),
    "ASR": InferenceTaskSpec(
        task_type="ASR",
        service_type="asr",
        ppu_name="asr",
        billing_unit="minutes",
        path_segments=("/asr", "/transcribe", "/speech"),
        input_modality="audio",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_asr_audio_length", "audio_seconds", "audio_seconds",
                language_from_source=True,
            ),
        ),
    ),
    "OCR": InferenceTaskSpec(
        task_type="OCR",
        service_type="ocr",
        ppu_name="ocr",
        billing_unit="images",
        path_segments=("/ocr", "/text-recognition"),
        input_modality="image",
        payload_metric_emissions=(
            PayloadMetricEmission("track_ocr_characters", "ocr_characters", "characters"),
            PayloadMetricEmission("track_ocr_image_size", "ocr_image_kb", "image_size_kb"),
        ),
    ),
    "NER": InferenceTaskSpec(
        task_type="NER",
        service_type="ner",
        ppu_name="ner",
        billing_unit="characters",
        path_segments=("/ner", "/entity", "/entities"),
        input_modality="text",
        payload_metric_emissions=(
            PayloadMetricEmission("track_ner_tokens", "ner_tokens", "tokens"),
        ),
    ),
    "TRANSLITERATION": InferenceTaskSpec(
        task_type="TRANSLITERATION",
        service_type="transliteration",
        ppu_name="transliteration",
        billing_unit="characters",
        path_segments=("/transliteration", "/xlit", "/transliterate"),
        input_modality="text",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_transliteration_characters", "characters", "characters",
                source_lang=True, target_lang=True,
            ),
        ),
    ),
    "LANGUAGE_DETECTION": InferenceTaskSpec(
        task_type="LANGUAGE_DETECTION",
        service_type="language_detection",
        ppu_name="language-detection",
        billing_unit="characters",
        path_segments=("/language-detection", "/lang-detect", "/detect-language"),
        input_modality="text",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_language_detection_characters", "characters", "characters",
            ),
        ),
    ),
    "AUDIO_LANGUAGE_DETECTION": InferenceTaskSpec(
        task_type="AUDIO_LANGUAGE_DETECTION",
        service_type="audio_lang_detection",
        ppu_name="audio-lang-detection",
        billing_unit="minutes",
        path_segments=("/audio-lang-detection", "/audio-language-detection", "/audio-detect"),
        input_modality="audio",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_audio_lang_detection_length", "audio_seconds", "audio_seconds",
            ),
        ),
    ),
    "SPEAKER_DIARIZATION": InferenceTaskSpec(
        task_type="SPEAKER_DIARIZATION",
        service_type="speaker_diarization",
        ppu_name="speaker-diarization",
        billing_unit="minutes",
        path_segments=("/speaker-diarization", "/speaker-diarization-compute-call"),
        input_modality="audio",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_speaker_diarization_length", "audio_seconds", "audio_seconds",
            ),
        ),
    ),
    "LANGUAGE_DIARIZATION": InferenceTaskSpec(
        task_type="LANGUAGE_DIARIZATION",
        service_type="language_diarization",
        ppu_name="language-diarization",
        billing_unit="minutes",
        path_segments=("/language-diarization", "/language-diarization-compute-call"),
        input_modality="audio",
        payload_metric_emissions=(
            PayloadMetricEmission(
                "track_language_diarization_length", "audio_seconds", "audio_seconds",
            ),
        ),
    ),
    "LLM": InferenceTaskSpec(
        task_type="LLM",
        service_type="llm",
        ppu_name="llm",
        billing_unit="tokens",
        path_segments=("/llm", "/generate", "/chat", "/completion"),
        emit_body_metrics=False,
        input_modality="text",
    ),
    "PII": InferenceTaskSpec(
        task_type="PII",
        service_type="pii",
        ppu_name="pii",
        billing_unit="characters",
        path_segments=("/pii",),
        input_modality="text",
    ),
    "SMR": InferenceTaskSpec(
        task_type="SMR",
        service_type="smr",
        ppu_name="smr",
        billing_unit="requests",
        path_segments=("/smr",),
        emit_body_metrics=False,
    ),
}

# Derived views — built from INFERENCE_TASKS, not separate hand-maintained maps.
TASK_TYPE_TO_SERVICE_TYPE: Dict[str, str] = {
    spec.task_type: spec.service_type for spec in INFERENCE_TASKS.values()
}

ALLOWED_TASK_TYPES: Tuple[str, ...] = tuple(INFERENCE_TASKS.keys())

BODY_METRIC_SERVICE_TYPES: FrozenSet[str] = frozenset(
    spec.service_type for spec in INFERENCE_TASKS.values() if spec.emit_body_metrics
)

SERVICE_TYPE_METRIC_EMISSIONS: Dict[str, Tuple[PayloadMetricEmission, ...]] = {
    spec.service_type: spec.payload_metric_emissions
    for spec in INFERENCE_TASKS.values()
    if spec.payload_metric_emissions
}

INFERENCE_JSON_PATH_HINTS: Tuple[str, ...] = (
    "/inference",
    *tuple(
        sorted(
            {seg for spec in INFERENCE_TASKS.values() for seg in spec.path_segments},
            key=len,
            reverse=True,
        )
    ),
)

# Longest segment first so e.g. /audio-language-detection wins over /language-detection.
_PATH_SEGMENT_TO_SERVICE_TYPE: Tuple[Tuple[str, str], ...] = tuple(
    sorted(
        (
            (segment, spec.service_type)
            for spec in INFERENCE_TASKS.values()
            for segment in spec.path_segments
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)


def service_type_from_task_type(task_type: str) -> str:
    """Map API task_type to observability service_type."""
    spec = INFERENCE_TASKS.get(str(task_type or "").upper())
    return spec.service_type if spec else "unknown"


def service_type_from_path(path: str) -> str:
    """Detect service_type from URL path segments (longest match first)."""
    path_lower = path.lower()
    for segment, service_type in _PATH_SEGMENT_TO_SERVICE_TYPE:
        if segment in path_lower:
            return service_type
    if any(p in path_lower for p in ("/speaker", "/speaker-enrollment", "/speaker-verification", "/speak")):
        return "speaker_verification"
    if any(p in path_lower for p in ("/enterprise", "/health", "/metrics", "/config")):
        return "enterprise"
    if any(p in path_lower for p in ("/docs", "/openapi", "/redoc")):
        return "documentation"
    return "unknown"
