"""PromQL helpers for the metering API — pure functions, no DB, no I/O.

Provides:
  - ``TIME_RANGES``: allowed time-window keys mapped to Prometheus duration strings.
  - ``INFERENCE_ENDPOINT_REGEX``: regex that matches all inference endpoints.
  - ``apply_time_range`` / ``sum_over_window`` / ``sum_over_prev_window``: exact last_over_time delta queries.
  - ``sum_over_window`` / ``sum_over_prev_window``: ready-made sum queries.
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


def delta_expr(metric_expr: str, window: str, snapshot_offset: str = "") -> str:
    """Exact counter delta between two last_over_time snapshots — no extrapolation.

    current  = last_over_time(metric[window] [offset snapshot_offset])
    prev     = last_over_time(metric[window] offset <snapshot_offset + window>)
               OR  current * 0   when the series didn't exist that far back
                   (new deployments, or data older than Prometheus retention)

    clamp_min(..., 0) absorbs counter resets (pod restarts) so they contribute
    their post-reset count rather than a negative delta.

    snapshot_offset (optional): shift both snapshots back by this duration.
    Leave empty for the current window; set to `window` for the previous period.
    """
    if snapshot_offset:
        current = f"last_over_time({metric_expr}[{window}] offset {snapshot_offset})"
        prev    = f"last_over_time({metric_expr}[{window}] offset {DOUBLE_TIME_RANGES.get(snapshot_offset, snapshot_offset)})"
    else:
        current = f"last_over_time({metric_expr}[{window}])"
        prev    = f"last_over_time({metric_expr}[{window}] offset {window})"
    return f"clamp_min({current} - ({prev} or {current} * 0), 0)"


def apply_time_range(metric_expr: str, time_range: str | None) -> str:
    """Wrap metric_expr in an exact windowed delta expression.

    Returns delta_expr(metric, window) when a time range is given,
    or the raw cumulative counter for time_range=None/'all'.
    """
    window = TIME_RANGES.get(time_range or "all")
    if window:
        return delta_expr(metric_expr, window)
    return metric_expr


def sum_over_window(metric_expr: str, time_range: str | None) -> str:
    """Total exact counter delta over a rolling window — no extrapolation.

    Falls back to a plain sum for time_range="all"/None (cumulative counter, no window).
    """
    window = TIME_RANGES.get(time_range or "all")
    if not window:
        return f"sum({metric_expr})"
    return f"sum({delta_expr(metric_expr, window)})"


def sum_over_prev_window(metric_expr: str, time_range: str) -> str:
    """Total exact counter delta over the previous period (for period-over-period comparison).

    For a 1h window: counts requests in [T-2h, T-1h].
    """
    window = TIME_RANGES[time_range]
    return f"sum({delta_expr(metric_expr, window, snapshot_offset=window)})"


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

    Returns a brace-enclosed string like '{endpoint=~"...",tenant="foo"}'
    or an empty string when no filters apply.
    """
    selectors: list[str] = ['tenant!="unknown"']
    if inference_only:
        selectors.append(f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"')
    if tenant:
        selectors.append(f'tenant="{tenant}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')
    if extra:
        selectors.extend(extra)
    return "{" + ",".join(selectors) + "}"
