"""
Business metrics helpers.
Provides functions to record service-specific metrics (ASR, TTS, NMT).
"""

import logging
from typing import Optional
from prometheus_client import CollectorRegistry, Counter

logger = logging.getLogger(__name__)

# Global metric instances (bound to registry on init)
_inference_requests: Optional[Counter] = None
_tts_characters: Optional[Counter] = None
_asr_audio_seconds: Optional[Counter] = None


def bind_registry(registry: CollectorRegistry, service_name: str):
    """
    Bind business metrics to a Prometheus registry.
    
    This should be called once during observability initialization.
    
    Args:
        registry: Prometheus CollectorRegistry
        service_name: Name of the service (for documentation)
    """
    global _inference_requests, _tts_characters, _asr_audio_seconds
    
    # Inference requests counter (used by all services)
    _inference_requests = Counter(
        "ai4i_inference_request_total",
        "Total inference requests by service, task type, and languages",
        labelnames=(
            "organization",
            "service",
            "task_type",
            "source_language",
            "target_language",
            "api_key_name",
            "user_id",
        ),
        registry=registry,
    )
    
    # TTS-specific: Characters synthesized
    _tts_characters = Counter(
        "ai4i_tts_characters_synthesized",
        "Total characters synthesized by TTS service",
        labelnames=(
            "organization",
            "service",
            "language",
            "api_key_name",
            "user_id",
        ),
        registry=registry,
    )
    
    # ASR-specific: Audio seconds processed
    _asr_audio_seconds = Counter(
        "ai4i_asr_audio_seconds_processed",
        "Total audio seconds processed by ASR service",
        labelnames=(
            "organization",
            "service",
            "language",
            "api_key_name",
            "user_id",
        ),
        registry=registry,
    )
    
    logger.info(f"Business metrics bound to registry for service: {service_name}")


def record_inference_request(
    organization: str,
    service: str,
    task_type: str,
    source_language: str,
    target_language: str,
    api_key_name: str = "unknown",
    user_id: str = "anonymous",
):
    """
    Record a generic inference request.
    
    Args:
        organization: Organization/tenant ID
        service: Service name (e.g., "nmt", "tts", "asr")
        task_type: Task type (e.g., "translate", "synthesize", "transcribe")
        source_language: Source language code
        target_language: Target language code (use "none" for non-translation tasks)
        api_key_name: API key identifier
        user_id: User identifier
    """
    if _inference_requests is None:
        logger.warning("Metrics not initialized. Call bind_registry() first.")
        return
    
    try:
        _inference_requests.labels(
            organization,
            service,
            task_type,
            source_language,
            target_language,
            api_key_name,
            user_id,
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record inference request metric: {e}")


def record_translation(
    organization: str,
    api_key_name: str,
    user_id: str,
    source_language: str,
    target_language: str,
    service: str = "nmt",
):
    """
    Record a translation request (NMT service).
    
    Args:
        organization: Organization/tenant ID
        api_key_name: API key identifier
        user_id: User identifier
        source_language: Source language code
        target_language: Target language code
        service: Service name (default: "nmt")
    
    Example:
        ```python
        from ai4i_observability.metrics import record_translation
        
        record_translation(
            organization="irctc",
            api_key_name="partner_key",
            user_id="u_123",
            source_language="hi",
            target_language="en",
        )
        ```
    """
    record_inference_request(
        organization=organization,
        service=service,
        task_type="translate",
        source_language=source_language,
        target_language=target_language,
        api_key_name=api_key_name,
        user_id=user_id,
    )


def record_tts_characters(
    organization: str,
    api_key_name: str,
    user_id: str,
    language: str,
    characters: int,
    service: str = "tts",
):
    """
    Record TTS characters synthesized.
    
    Args:
        organization: Organization/tenant ID
        api_key_name: API key identifier
        user_id: User identifier
        language: Language code
        characters: Number of characters synthesized
        service: Service name (default: "tts")
    
    Example:
        ```python
        from ai4i_observability.metrics import record_tts_characters
        
        record_tts_characters(
            organization="beml",
            api_key_name="beml_key",
            user_id="u_456",
            language="en",
            characters=1500,
        )
        ```
    """
    if _tts_characters is None:
        logger.warning("Metrics not initialized. Call bind_registry() first.")
        return
    
    try:
        _tts_characters.labels(
            organization=organization,
            service=service,
            language=language,
            api_key_name=api_key_name,
            user_id=user_id,
        ).inc(characters)
    except Exception as e:
        logger.warning(f"Failed to record TTS characters metric: {e}")


def record_asr_seconds(
    organization: str,
    api_key_name: str,
    user_id: str,
    language: str,
    seconds: float,
    service: str = "asr",
):
    """
    Record ASR audio seconds processed.
    
    Args:
        organization: Organization/tenant ID
        api_key_name: API key identifier
        user_id: User identifier
        language: Language code
        seconds: Audio duration in seconds
        service: Service name (default: "asr")
    
    Example:
        ```python
        from ai4i_observability.metrics import record_asr_seconds
        
        record_asr_seconds(
            organization="irctc",
            api_key_name="irctc_key",
            user_id="u_789",
            language="hi",
            seconds=45.5,
        )
        ```
    """
    if _asr_audio_seconds is None:
        logger.warning("Metrics not initialized. Call bind_registry() first.")
        return
    
    try:
        _asr_audio_seconds.labels(
            organization=organization,
            service=service,
            language=language,
            api_key_name=api_key_name,
            user_id=user_id,
        ).inc(seconds)
    except Exception as e:
        logger.warning(f"Failed to record ASR seconds metric: {e}")

