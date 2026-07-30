"""PromQL helpers for the metering API — pure functions, no DB, no network I/O.

Provides:
  - ``TIME_RANGES``: allowed time-window keys mapped to Prometheus duration strings.
  - ``INFERENCE_ENDPOINT_REGEX``: regex that matches all inference endpoints.
  - ``apply_time_range``: wraps a metric expression in ``increase(...[window])``.
  - ``PROMETHEUS_API_PATH_LABEL``: the one exception — read from settings, since
    which label carries the HTTP path is environment-dependent (see
    ``CoreSettings.prometheus_api_path_label`` in app/core/config.py for why).
"""

from __future__ import annotations

from app.core.config import settings

# See CoreSettings.prometheus_api_path_label (app/core/config.py) for why this
# is env-driven rather than hardcoded. Every selector/groupby here and in
# metering_service.py must match on this label.
PROMETHEUS_API_PATH_LABEL = settings.prometheus_api_path_label

# Allowed time range values mapped to Prometheus duration strings.
# None means no window — returns the cumulative counter value.
TIME_RANGES: dict = {
    "1h":  "1h",
    "24h": "24h",
    "7d":  "7d",
    "30d": "30d",
    "all": None,
}

# Bucket configuration for throughput peak detection.
# Each entry describes how to split the time window into labelled sub-buckets
# (M = minute, H = hour, D = day) so the peak RPS bucket can be identified.
# Bucket i=1 is the oldest; i=count is the newest (offset 0).
THROUGHPUT_BUCKET_CONFIG: dict = {
    "1h":  {"count": 12, "bucket_window": "5m", "offset_unit": "m", "offset_factor": 5,  "label_prefix": "M"},
    "24h": {"count": 24, "bucket_window": "1h", "offset_unit": "h", "offset_factor": 1,  "label_prefix": "H"},
    "7d":  {"count":  7, "bucket_window": "1d", "offset_unit": "d", "offset_factor": 1,  "label_prefix": "D"},
    "30d": {"count": 30, "bucket_window": "1d", "offset_unit": "d", "offset_factor": 1,  "label_prefix": "D"},
}

# Matches endpoints ending in /inference (excludes /inference/health) plus LLM chat paths.
# Anchored in Prometheus =~ so /api/v1/chat(/completions)? matches both label forms.
INFERENCE_ENDPOINT_REGEX = r"(.*/inference|/api/v1/chat(/completions)?)"

# Regex for service-breakdown queries — same coverage as INFERENCE_ENDPOINT_REGEX.
SERVICE_BREAKDOWN_ENDPOINT_REGEX = r"/api/v1/(.+/inference|chat(/completions)?)"

# Maps Prometheus endpoint label values to SERVICE_BREAKDOWN_CONFIG task keys
# for services whose endpoint doesn't follow the /api/v1/{task}/inference pattern.
ENDPOINT_TO_TASK: dict = {
    "/api/v1/chat": "llm",
    "/api/v1/chat/completions": "llm",
    # inference-service abbreviates this route to "audio-lang-detection" —
    # doesn't match the "audio_language_detection" config key via hyphenation.
    "/api/v1/audio-lang-detection/inference": "audio_language_detection",
}

# Bucket size for the Request Volume range chart — chosen so each window renders a
# small, readable set of aggregated bars rather than hundreds of fine-grained points:
#   1h  → 10m buckets (~6 bars, time labels)
#   24h → 4h  buckets (~6 bars, time labels)
#   7d  → 1d  buckets (7 bars, daily date labels)
#   30d → 7d  buckets (date+time labels)
# The frontend label format keys off this step (see formatMeteringTimestamp).
WINDOW_STEP: dict = {
    "1h":  "10m",
    "24h": "4h",
    "7d":  "1d",
    "30d": "7d",
}


def build_task_type_selector(task_types: list[str] | None) -> str | None:
    """Build an extra label-selector fragment restricting queries to specific task types.

    Reverses ENDPOINT_TO_TASK for tasks with a non-standard endpoint (e.g. "llm" ->
    /api/v1/chat, /api/v1/chat/completions) and falls back to the standard
    /api/v1/{task}/inference pattern (hyphenated, matching SERVICE_BREAKDOWN_CONFIG's
    underscore-separated keys) for everything else. An unrecognized task type simply
    yields a pattern that matches no endpoint (lenient — no validation error), matching
    this API's existing lenient task_types= parsing.

    Returns None when task_types is falsy, so callers can skip the selector entirely.
    """
    if not task_types:
        return None
    patterns: list[str] = []
    for task in task_types:
        # No re.escape(): these are fixed, config-controlled endpoint strings (not
        # user input), and PromQL's regex dialect rejects Python's `\-` escape for
        # hyphens with a parse error, so escaping would break e.g. audio-lang-detection.
        literal_endpoints = [ep for ep, t in ENDPOINT_TO_TASK.items() if t == task]
        if literal_endpoints:
            patterns.extend(literal_endpoints)
        else:
            patterns.append(f"/api/v1/{task.replace('_', '-')}/inference")
    regex = "|".join(patterns)
    return f'{PROMETHEUS_API_PATH_LABEL}=~"{regex}"'


def apply_time_range(metric_expr: str, time_range: str | None) -> str:
    """Wrap metric_expr in increase(...[window]) when a time range is given.

    increase() returns how much the counter grew over the window.
    When time_range is None or 'all', returns the raw cumulative counter.
    """
    window = TIME_RANGES.get(time_range or "all")
    if window:
        return f"increase({metric_expr}[{window}])"
    return metric_expr


def sum_over_window(metric_expr: str, time_range: str | None) -> str:
    """Build a PromQL sum that captures every request, including very recent ones.

    Two-part hybrid so no data is lost:
    1. metric unless metric offset window — raw counter for brand-new pods that
       have no data at offset w (increase() would extrapolate on those). The
       `unless` guard ensures only truly new series use the raw counter.
    2. increase() — established series (existed before window-start); reset-aware
       and falls through only when arm 1 yields empty.

    Arm order matters: `unless` must be first so new pods (multiple scrape points
    but none at offset w) never reach the increase() arm. If increase() fired first,
    its large extrapolated value (observed_increase × window/observed_duration) would
    be > 0 and the unless arm would never run.

    Falls back to a plain sum for time_range="all"/None.
    Accepts a TIME_RANGES key ("7d") or a raw Prometheus duration string ("1d").
    """
    window = TIME_RANGES.get(time_range or "all") or (
        time_range if time_range and time_range != "all" else None
    )
    if not window:
        return f"sum({metric_expr})"
    return (
        f"sum("
        f"({metric_expr} unless {metric_expr} offset {window})"
        f" or (increase({metric_expr}[{window}]) > 0)"
        f")"
    )


# Per-task display metadata for the service breakdown table.
# Keys match the URL task segment: /api/v1/{task}/inference.
#
# native_metric: the Prometheus Histogram _sum series that accumulates the
#   native unit (characters, seconds, tokens). Use the _sum suffix because
#   that is what Prometheus appends to a Histogram name.  None means the
#   task has no dedicated native-unit metric — the API returns null for
#   native_units in that case.
# native_extra_labels: additional label selectors applied only to the
#   native query (e.g. token_type="total" for LLM to avoid double-counting
#   prompt + completion + total series).
SERVICE_BREAKDOWN_CONFIG: dict = {
    "nmt": {
        "display_name": "NMT",
        "metering_unit": "Characters translated",
        "native_unit_suffix": "chars",
        "native_metric": "telemetry_obsv_nmt_characters_translated_sum",
        "native_extra_labels": None,
    },
    "asr": {
        "display_name": "ASR",
        "metering_unit": "Audio minutes processed",
        "native_unit_suffix": "min",
        "native_metric": "telemetry_obsv_asr_audio_seconds_processed_sum",
        "native_extra_labels": None,
        "divide_by_60": True,
    },
    "tts": {
        "display_name": "TTS",
        "metering_unit": "Characters synthesized",
        "native_unit_suffix": "chars",
        "native_metric": "telemetry_obsv_tts_characters_synthesized_sum",
        "native_extra_labels": None,
    },
    "llm": {
        "display_name": "LLM",
        "metering_unit": "Tokens processed",
        "native_unit_suffix": "tokens",
        "native_metric": "telemetry_obsv_llm_tokens_processed_sum",
        # The LLM histogram emits three series per request (prompt / completion / total).
        # Filter to token_type="total" so we count each request's aggregate once.
        "native_extra_labels": ['token_type="total"'],
    },
    "ocr": {
        "display_name": "OCR",
        "metering_unit": "Image KB processed",
        "native_unit_suffix": "KB",
        "native_metric": "telemetry_obsv_ocr_image_size_kb_sum",
        "native_extra_labels": None,
    },
    "transliteration": {
        "display_name": "Transliteration",
        "metering_unit": "Characters processed",
        "native_unit_suffix": "chars",
        "native_metric": "telemetry_obsv_transliteration_characters_processed_sum",
        "native_extra_labels": None,
    },
    "pipeline": {
        "display_name": "Pipeline",
        # No dedicated native-unit metric defined in metrics.py.
        "metering_unit": "Jobs executed",
        "native_unit_suffix": "jobs",
        "native_metric": None,
        "native_extra_labels": None,
    },
    "ner": {
        "display_name": "NER",
        # metrics.py tracks tokens (words), not bare request counts.
        "metering_unit": "Tokens processed",
        "native_unit_suffix": "tokens",
        "native_metric": "telemetry_obsv_ner_tokens_processed_sum",
        "native_extra_labels": None,
    },
    "language_detection": {
        "display_name": "Language Detection",
        # metrics.py tracks characters sent for detection, not request counts.
        "metering_unit": "Characters processed",
        "native_unit_suffix": "chars",
        "native_metric": "telemetry_obsv_language_detection_characters_processed_sum",
        "native_extra_labels": None,
    },
    "speaker_diarization": {
        "display_name": "Speaker Diarization",
        "metering_unit": "Audio minutes processed",
        "native_unit_suffix": "min",
        "native_metric": "telemetry_obsv_speaker_diarization_seconds_processed_sum",
        "native_extra_labels": None,
        "divide_by_60": True,
    },
    "audio_language_detection": {
        "display_name": "Audio Language Detection",
        "metering_unit": "Audio minutes processed",
        "native_unit_suffix": "min",
        "native_metric": "telemetry_obsv_audio_lang_detection_seconds_processed_sum",
        "native_extra_labels": None,
        "divide_by_60": True,
    },
}


def build_base_selectors(
    inference_only: bool = True,
    tenant: str | None = None,
    service_id: str | None = None,
    extra: list[str] | None = None,
) -> str:
    """Build a PromQL label selector string for telemetry_obsv_requests_total.

    Returns a brace-enclosed string like '{exported_endpoint=~"...",tenant="foo"}'
    or an empty string when no filters apply.
    """
    selectors: list[str] = ['tenant!="unknown"']
    if inference_only:
        selectors.append(f'{PROMETHEUS_API_PATH_LABEL}=~"{INFERENCE_ENDPOINT_REGEX}"')
    if tenant:
        selectors.append(f'tenant="{tenant}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')
    if extra:
        selectors.extend(extra)
    return "{" + ",".join(selectors) + "}"
