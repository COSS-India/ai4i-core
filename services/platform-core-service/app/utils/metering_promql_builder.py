"""PromQL helpers for the metering API — pure functions, no DB, no I/O.

Provides:
  - ``TIME_RANGES``: allowed time-window keys mapped to Prometheus duration strings.
  - ``INFERENCE_ENDPOINT_REGEX``: regex that matches all inference endpoints.
  - ``apply_time_range``: wraps a metric expression in ``increase(...[window])``.
"""

from __future__ import annotations

# Allowed time range values mapped to Prometheus duration strings.
# None means no window — returns the cumulative counter value.
TIME_RANGES: dict = {
    "1h":  "1h",
    "24h": "24h",
    "7d":  "7d",
    "30d": "30d",
    "all": None,
}

# Two-window offsets used to query the *previous* period.
# e.g. for a 24h window, prev_period = counter@48h_ago - counter@24h_ago.
# Prometheus duration strings don't support arithmetic so we precompute them.
DOUBLE_TIME_RANGES: dict = {
    "1h":  "2h",
    "24h": "48h",
    "7d":  "14d",
    "30d": "60d",
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

# Matches endpoints ending in /inference (excludes /inference/health) plus /api/v1/chat (LLM).
INFERENCE_ENDPOINT_REGEX = r"(.*/inference|/api/v1/chat)"

# Regex for service-breakdown queries — covers all inference-style endpoints
# plus non-standard ones (e.g. LLM uses /api/v1/chat, not /api/v1/llm/inference).
SERVICE_BREAKDOWN_ENDPOINT_REGEX = r"/api/v1/(.+/inference|chat)"

# Maps Prometheus endpoint label values to SERVICE_BREAKDOWN_CONFIG task keys
# for services whose endpoint doesn't follow the /api/v1/{task}/inference pattern.
ENDPOINT_TO_TASK: dict = {
    "/api/v1/chat": "llm",
}


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

    Two-part approach so no data is lost:
    1. increase() >= 0  — established series (2+ scrape points); handles counter
       resets across service restarts automatically.
    2. metric unless metric offset window — raw counter for brand-new series that
       have only 1 scrape point (increase() returns NaN for them). The `unless`
       guard ensures only truly new series (didn't exist at window-start) use the
       raw counter, preventing old series from inflating the total with their
       all-time value.
    Falls back to a plain sum for time_range="all"/None.
    """
    window = TIME_RANGES.get(time_range or "all")
    if not window:
        return f"sum({metric_expr})"
    return (
        f"sum("
        f"(increase({metric_expr}[{window}]) > 0)"
        f" or ({metric_expr} unless {metric_expr} offset {window})"
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
        # Prometheus metric name is *_seconds_processed — not minutes.
        "metering_unit": "Audio seconds processed",
        "native_unit_suffix": "sec",
        "native_metric": "telemetry_obsv_asr_audio_seconds_processed_sum",
        "native_extra_labels": None,
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
        # metrics.py tracks characters and image KB — no "pages" counter exists.
        "metering_unit": "Characters processed",
        "native_unit_suffix": "chars",
        "native_metric": "telemetry_obsv_ocr_characters_processed_sum",
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
        # Prometheus metric name is *_seconds_processed — not minutes.
        "metering_unit": "Audio seconds processed",
        "native_unit_suffix": "sec",
        "native_metric": "telemetry_obsv_speaker_diarization_seconds_processed_sum",
        "native_extra_labels": None,
    },
}


def build_base_selectors(
    inference_only: bool = True,
    tenant: str | None = None,
    service_id: str | None = None,
    extra: list[str] | None = None,
) -> str:
    """Build a PromQL label selector string for telemetry_obsv_requests_total.

    Returns a brace-enclosed string like '{endpoint=~"...",tenant="foo"}'
    or an empty string when no filters apply.
    """
    selectors: list[str] = []
    if inference_only:
        selectors.append(f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"')
    if tenant:
        selectors.append(f'tenant="{tenant}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')
    if extra:
        selectors.extend(extra)
    return "{" + ",".join(selectors) + "}" if selectors else ""
