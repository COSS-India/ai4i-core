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

# The single auth_type value the Metering Dashboard restricts itself to —
# UI/playground calls authenticate via JWT, not this. Defined once here (not
# repeated as a literal at every call site in metering_service.py) so the
# policy has one home; every selector below also matches it fail-open (see
# api_key_auth_type_selector) rather than by exact equality, since an exact
# match would silently drop every series recorded before this label existed,
# and any request the gateway doesn't stamp with X-Auth-Type at all —
# payperuse_consumer/handler.py fails open the same way for billing.
API_KEY_AUTH_TYPE = "api_key"

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

# LLM chat paths only — narrower than INFERENCE_ENDPOINT_REGEX, which also
# matches non-LLM /inference endpoints. Used by the model-consumption tab,
# which is LLM-only.
LLM_CHAT_ENDPOINT_REGEX = r"/api/v1/chat(/completions)?"

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
    underscore-separated keys) for everything else. Callers are expected to have
    already rejected unrecognized task types (see `_parse_task_types` in
    routes/metering.py, which 422s on anything outside SERVICE_BREAKDOWN_CONFIG)
    before reaching this helper.

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


def api_key_auth_type_selector() -> str:
    """Build the ``auth_type`` selector fragment (no braces) that restricts
    the Metering Dashboard to API-key traffic, fail-open on absence.

    ``auth_type=~"api_key|"`` — not the exact-equality ``auth_type="api_key"``
    — because Prometheus treats an absent label as the empty string for
    matching purposes: every series recorded before this label existed, and
    any request the gateway doesn't stamp with X-Auth-Type at all, has no
    ``auth_type`` label rather than one set to something else. An equality
    match would silently exclude those series for as long as they remain in
    the query window (up to the full 7d/30d retention), rather than just the
    JWT/UI traffic it's meant to exclude. Self-heals as pre-rollout series
    age out — see payperuse_consumer/handler.py for the same fail-open
    reasoning applied to billing.
    """
    return f'auth_type=~"{API_KEY_AUTH_TYPE}|"'


def escape_label_value(value: str) -> str:
    """Escape a value for interpolation into a PromQL string literal.

    The ``tenant`` label now carries the tenant's organisation name (free
    text set by an admin), not a numeric id — unlike an id, it can contain
    ``"`` or ``\\``, which would otherwise break out of the label selector's
    quotes and let one value inject extra selectors into the query.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


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


def sum_over_window_by(metric_expr: str, by_label: str, time_range: str | None) -> str:
    """Same reset-aware hybrid as sum_over_window(), grouped by ``by_label``.

    Used to break a counter down per label value (e.g. per model) instead of
    collapsing it to a single total.
    """
    window = TIME_RANGES.get(time_range or "all") or (
        time_range if time_range and time_range != "all" else None
    )
    if not window:
        return f"sum by({by_label}) ({metric_expr})"
    return (
        f"sum by({by_label}) ("
        f"({metric_expr} unless {metric_expr} offset {window})"
        f" or (increase({metric_expr}[{window}]) > 0)"
        f")"
    )


# Per-task display metadata for the service breakdown table.
# Keys match the URL task segment: /api/v1/{task}/inference.
#
# native_metric: the Prometheus Histogram _sum series that accumulates the
#   native unit (characters, minutes, tokens, images). Use the _sum suffix
#   because that is what Prometheus appends to a Histogram name. None means
#   the task has no dedicated native-unit metric — the API returns null for
#   native_units in that case.
# native_extra_labels: additional label selectors applied only to the
#   native query (e.g. token_type="total" for LLM to avoid double-counting
#   prompt + completion + total series).
# round_2dp: the underlying histogram already reports minutes (not seconds),
#   so display at 2-decimal precision instead of the whole-number rounding
#   used for character/token/image counts.
# native_unit_suffix: kept here as a fallback ONLY. The actual value shown
#   to callers is read from the PPU config
#   (libs/ai4i_core/ai4i_core/ppu/inference_types.yaml, via
#   metering_service.py's _native_unit_suffix_for_registry_task_type) —
#   the single canonical definition of each task type's billing/consumption
#   unit, shared with quota/pricing enforcement. This field is only used
#   when that yaml has no entry for a task type at all.
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
        "native_metric": "telemetry_obsv_asr_audio_minutes_processed_sum",
        "native_extra_labels": None,
        "round_2dp": True,
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
        "metering_unit": "Images processed",
        "native_unit_suffix": "images",
        "native_metric": "telemetry_obsv_ocr_images_processed_sum",
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
        # Despite the metric's own name (a legacy artifact — see
        # telemetry_obsv_ner_tokens_processed_sum), the PPU canonical unit
        # for "ner" (libs/ai4i_core/ai4i_core/ppu/inference_types.yaml) is
        # "characters", not tokens — that yaml is the actual source of truth
        # metering_service.py's native_unit_suffix lookups read from; this
        # field is kept in sync as a same-value fallback only.
        "metering_unit": "Characters processed",
        "native_unit_suffix": "chars",
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
        "native_metric": "telemetry_obsv_speaker_diarization_minutes_processed_sum",
        "native_extra_labels": None,
        "round_2dp": True,
    },
    "language_diarization": {
        "display_name": "Language Diarization",
        "metering_unit": "Audio minutes processed",
        "native_unit_suffix": "min",
        "native_metric": "telemetry_obsv_language_diarization_minutes_processed_sum",
        "native_extra_labels": None,
        "round_2dp": True,
    },
    "audio_language_detection": {
        "display_name": "Audio Language Detection",
        "metering_unit": "Audio minutes processed",
        "native_unit_suffix": "min",
        "native_metric": "telemetry_obsv_audio_lang_detection_minutes_processed_sum",
        "native_extra_labels": None,
        "round_2dp": True,
    },
}


def build_base_selectors(
    inference_only: bool = True,
    tenant: str | None = None,
    service_id: str | None = None,
    extra: list[str] | None = None,
    endpoint_regex: str | None = None,
    tenant_id: str | None = None,
    auth_type: str | None = None,
) -> str:
    """Build a PromQL label selector string for telemetry_obsv_requests_total.

    Returns a brace-enclosed string like '{exported_endpoint=~"...",tenant="foo"}'
    or an empty string when no filters apply. ``endpoint_regex`` overrides the
    default INFERENCE_ENDPOINT_REGEX (e.g. to scope to LLM-only endpoints);
    ignored when ``inference_only`` is False. ``auth_type`` restricts to a
    single auth_type label value (e.g. "api_key") — the request counter
    started carrying this label once ObservabilityMiddleware began forwarding
    X-Auth-Type, so callers can filter UI/JWT traffic out of request counts
    the same way payperuse_consumer/handler.py already restricts billing to
    API-key calls. Matched fail-open (``=~"value|"``, not ``="value"``) so a
    series with no auth_type label at all (recorded before this label
    existed, or a request the gateway never stamped) isn't silently dropped
    — see api_key_auth_type_selector's docstring.

    ``tenant_id`` scopes to a single tenant by its immutable numeric id —
    prefer it over ``tenant`` (the organisation name) wherever the caller has
    it, since the name changes on a tenant rename and orphans historical
    series (see ObservabilityMiddleware). When both are given, ``tenant_id``
    is the effective filter; ``tenant`` is only applied when ``tenant_id`` is
    absent, so older call sites that still pass just a name keep working.

    KNOWN CUTOVER GAP (accepted, tracked in the ticket, not fixed here):
    when ``tenant_id`` is given, this selector matches ONLY series written
    after tenant_id started being emitted — pre-cutover series for that same
    tenant have no tenant_id label at all and are silently excluded. Unlike
    the platform-wide views (active_tenants/usage_concentration/
    tenant_ranking/heatmap), which recover this data via a (tenant_id,
    tenant) group-by + merge, a single-tenant filter can't do the same
    without either an invalid PromQL construct (an `or` of two selectors
    can't be wrapped in a range vector like `increase(...[24h])`, which
    every windowed query here uses) or doubling every tenant-scoped query
    and merging in Python — a real fix, deliberately deferred. Every caller
    that passes ``tenant_id`` through to a windowed query (request_total,
    avg_per_active_tenant_previous, service_breakdown, model_breakdown,
    tenant_ranking(tenant_id=...), usage_by_tenant_service, and
    _native_unit_queries in metering_service.py) inherits this gap: a
    single-tenant view can be missing up to ~30 days of that tenant's
    history right after this label's rollout. QA should expect this when
    re-testing by selecting a specific (especially a just-renamed) tenant.
    """
    selectors: list[str] = ['tenant!="unknown"']
    if inference_only:
        selectors.append(f'{PROMETHEUS_API_PATH_LABEL}=~"{endpoint_regex or INFERENCE_ENDPOINT_REGEX}"')
    if tenant_id:
        selectors.append(f'tenant_id="{escape_label_value(tenant_id)}"')
    elif tenant:
        selectors.append(f'tenant="{escape_label_value(tenant)}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')
    if auth_type:
        selectors.append(f'auth_type=~"{escape_label_value(auth_type)}|"')
    if extra:
        selectors.extend(extra)
    return "{" + ",".join(selectors) + "}"
