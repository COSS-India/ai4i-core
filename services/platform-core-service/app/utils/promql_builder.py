"""PromQL builders for alert definitions — pure functions, no DB, no I/O.

Two entry points:
  - ``build_promql_from_threshold``: legacy path; takes (category, alert_type,
    threshold_value, threshold_unit).
  - ``build_promql_from_signal_config``: new path; takes (category, sub_category,
    signal, signal_metric, condition_operator, threshold_value, threshold_unit).

After building, ``inject_endpoint_into_promql`` can be applied to scope a rule
to one or more inference tasks (e.g. only ``nmt``). All inference tasks now run
inside a single ``inference-service``, so Prometheus has no per-task ``service``
label — the task is encoded in the ``endpoint`` label as
``/api/v1/inference/<task>`` by the observability middleware. Scoping therefore
narrows the endpoint selector rather than adding a ``service=`` matcher.

Lifted from alert-management-service/alert_management.py:638-1012 with:
  - ``organization`` parameter / org-filter logic removed per migration plan.
  - ``HTTPException(400, ...)`` raises replaced with
    ``app.core.exceptions.ValidationError``.
  - ``inject_organization_into_promql`` deleted entirely.
  - service-label injection replaced with endpoint(task) scoping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.exceptions import ValidationError


# ── Public taxonomy (used by the portal + validators) ────────────────────────

APPLICATION_ALERT_TYPES_DISPLAY = ("Latency", "Error Rate")
INFRASTRUCTURE_ALERT_TYPES_DISPLAY = ("CPU", "Memory", "Disk")

SUB_CATEGORIES_CONFIG: Dict[str, Dict[str, Any]] = {
    # Application
    "performance": {"label": "Performance", "signals": ["latency"], "category": "application"},
    "availability": {"label": "Availability", "signals": ["error_rate"], "category": "application"},
    # Infrastructure
    "compute": {
        "label": "Compute",
        "signals": ["cpu_utilization", "memory_utilization"],
        "category": "infrastructure",
    },
    "storage": {"label": "Storage", "signals": ["disk_utilization"], "category": "infrastructure"},
}

SIGNALS_CONFIG: Dict[str, Dict[str, Any]] = {
    # Application
    "latency": {"label": "Latency", "signal_metrics": ["latency_p50", "latency_p99"]},
    "error_rate": {
        "label": "Error rate",
        "signal_metrics": ["error_rate_4xx", "error_rate_5xx", "error_rate_timeout"],
    },
    # Infrastructure
    "cpu_utilization": {"label": "CPU Utilization", "signal_metrics": ["total_cpu_usage"]},
    "memory_utilization": {"label": "Memory Utilization", "signal_metrics": ["total_memory_usage"]},
    "disk_utilization": {"label": "Disk Utilization", "signal_metrics": ["total_disk_usage"]},
}

SIGNAL_METRICS_CONFIG: Dict[str, Dict[str, Any]] = {
    # Application
    "latency_p50": {"label": "Latency P50", "signal": "latency", "quantile": 0.5},
    "latency_p99": {"label": "Latency P99", "signal": "latency", "quantile": 0.99},
    "error_rate_4xx": {"label": "4xx error rate", "signal": "error_rate", "status_regex": "[4].."},
    "error_rate_5xx": {"label": "5xx error rate", "signal": "error_rate", "status_regex": "5.."},
    "error_rate_timeout": {
        "label": "Timeout error rate",
        "signal": "error_rate",
        "status_regex": "408|504",
    },
    # Infrastructure
    "total_cpu_usage": {"label": "Total CPU Usage", "signal": "cpu_utilization", "infra_type": "cpu"},
    "total_memory_usage": {
        "label": "Total Memory Usage",
        "signal": "memory_utilization",
        "infra_type": "memory",
    },
    "total_disk_usage": {"label": "Total Disk Usage", "signal": "disk_utilization", "infra_type": "disk"},
}

CONDITION_OPERATORS_LIST: List[str] = [">", ">=", "<", "<="]

THRESHOLD_UNIT_LATENCY = ("ms", "s", "seconds")
THRESHOLD_UNIT_PERCENT = ("%", "percent")

# Maps label-derived keys to canonical signal_metric keys
SIGNAL_METRIC_LABEL_TO_KEY: Dict[str, str] = {
    "4xx_error_rate": "error_rate_4xx",
    "5xx_error_rate": "error_rate_5xx",
    "timeout_error_rate": "error_rate_timeout",
    "total_cpu_usage": "total_cpu_usage",
    "total_memory_usage": "total_memory_usage",
    "total_disk_usage": "total_disk_usage",
}

# Legacy service-name suffix — stripped if callers still pass e.g. "nmt-service".
SERVICE_SUFFIX = "-service"

# ── Inference task → endpoint scoping ────────────────────────────────────────
# The observability middleware encodes the inference task in the `endpoint`
# label as `/api/v1/inference/<task>`, where <task> is the lowercased
# inference-service TaskType. Alerts scope to a task by narrowing this selector.
INFERENCE_ENDPOINT_PREFIX = "/api/v1/inference"

# Lowercased inference-service TaskType values (services/inference-service/
# models/task_types.py). These are the literal endpoint suffixes in Prometheus.
INFERENCE_TASKS: tuple = (
    "nmt",
    "asr",
    "ocr",
    "ner",
    "llm",
    "language_detection",
    "tts",
    "transliteration",
    "language_diarization",
    "speaker_diarization",
    "audio_language_detection",
    "pii",
)

# The broad inference-endpoint matcher every builder emits when no task is given.
# `inject_endpoint_into_promql` rewrites this exact substring to a task-specific
# selector, so it must stay byte-identical to what the builders below produce.
_DEFAULT_ENDPOINT_SELECTOR = 'endpoint=~"/.*inference.*"'


# ── Alert-type helpers ───────────────────────────────────────────────────────


def _normalize_alert_type(category: str, alert_type: str) -> str:
    """Normalize alert_type to internal form: latency, error_rate, cpu, memory, disk."""
    if not alert_type:
        return alert_type
    t = alert_type.strip().lower().replace(" ", "_")
    if t in ("latency", "error_rate", "errorrate"):
        return "error_rate" if t == "errorrate" else t
    if t in ("cpu", "memory", "disk"):
        return t
    return alert_type.strip()


def alert_type_to_display(alert_type: str, category: str) -> str:
    """Return display/storage form: 'Latency', 'Error Rate', 'CPU', 'Memory', 'Disk'."""
    if not alert_type:
        return alert_type
    at = _normalize_alert_type(category, alert_type)
    mapping = {"latency": "Latency", "error_rate": "Error Rate", "cpu": "CPU", "memory": "Memory", "disk": "Disk"}
    return mapping.get(at, alert_type.strip())


# ── PromQL builders ──────────────────────────────────────────────────────────


def build_promql_from_threshold(
    category: str,
    alert_type: str,
    threshold_value: float,
    threshold_unit: str,
) -> str:
    """
    Build PromQL from alert type + threshold (legacy path).

    Latency: ``threshold_value`` is in seconds; the result groups by ``(le, endpoint, tenant)``
    so Alertmanager can route by tenant.
    Error rate: ratio of 4xx/5xx vs total; ``threshold_unit`` "percent" is converted to ratio.
    Infrastructure: percent thresholds against ``node_*`` metrics.
    """
    category = (category or "application").lower()
    at = _normalize_alert_type(category, alert_type or "")

    if category == "application":
        if at == "latency":
            return (
                f'histogram_quantile(0.5, sum by (le, endpoint, tenant) '
                f'(rate(telemetry_obsv_request_duration_seconds_bucket{{endpoint=~"/.*inference.*"}}[5m]))) '
                f'> {threshold_value}'
            )
        if at == "error_rate":
            thresh = (
                threshold_value / 100.0
                if (threshold_unit or "").lower() == "percent"
                else threshold_value
            )
            return (
                f'sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total'
                f'{{status_code=~"[45]..", endpoint=~"/.*inference.*"}}[5m])) '
                f'/ sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total'
                f'{{endpoint=~"/.*inference.*"}}[5m])) > {thresh}'
            )
        raise ValidationError(
            "Invalid application alert_type. Must be one of: Latency, Error Rate"
        )

    if category == "infrastructure":
        if at == "cpu":
            return (
                '100 * (1 - (sum(rate(node_cpu_seconds_total{mode="idle"}[5m])) '
                f'/ sum(rate(node_cpu_seconds_total[5m])))) > {threshold_value}'
            )
        if at == "memory":
            return (
                'max(100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))) '
                f'> {threshold_value}'
            )
        if at == "disk":
            return (
                'max(100 * (1 - (node_filesystem_avail_bytes'
                '{fstype!~"tmpfs|ramfs|overlay", mountpoint="/"} '
                '/ node_filesystem_size_bytes{fstype!~"tmpfs|ramfs|overlay", mountpoint="/"}))) '
                f'> {threshold_value}'
            )
        raise ValidationError(
            "Invalid infrastructure alert_type. Must be one of: CPU, Memory, Disk"
        )

    raise ValidationError("category must be 'application' or 'infrastructure'")


def build_promql_from_signal_config(
    category: str,
    sub_category: str,
    signal: str,
    signal_metric: str,
    condition_operator: str,
    threshold_value: float,
    threshold_unit: str,
) -> str:
    """Build PromQL from structured (sub_category, signal, signal_metric, condition_operator)."""
    category = (category or "application").lower()
    if category not in ("application", "infrastructure"):
        raise ValidationError("category must be 'application' or 'infrastructure'")

    sub = (sub_category or "").strip().lower().replace(" ", "_")
    sig = (signal or "").strip().lower().replace(" ", "_")
    metric_key = (signal_metric or "").strip().lower().replace(" ", "_")
    metric_key = SIGNAL_METRIC_LABEL_TO_KEY.get(metric_key, metric_key)
    op = (condition_operator or ">").strip()

    if sub not in SUB_CATEGORIES_CONFIG:
        raise ValidationError(
            f"Invalid sub_category '{sub_category}'. "
            f"Must be one of: {list(SUB_CATEGORIES_CONFIG.keys())}"
        )
    if SUB_CATEGORIES_CONFIG[sub].get("category") != category:
        raise ValidationError(
            f"Sub_category '{sub_category}' is not valid for category '{category}'."
        )
    if sig not in SIGNALS_CONFIG or sig not in SUB_CATEGORIES_CONFIG[sub]["signals"]:
        raise ValidationError(
            f"Invalid signal '{signal}' for sub_category '{sub_category}'."
        )
    if (
        metric_key not in SIGNAL_METRICS_CONFIG
        or SIGNAL_METRICS_CONFIG[metric_key]["signal"] != sig
    ):
        raise ValidationError(
            f"Invalid signal_metric '{signal_metric}' for signal '{signal}'."
        )
    if op not in CONDITION_OPERATORS_LIST:
        raise ValidationError(
            f"Invalid condition_operator '{condition_operator}'. "
            f"Must be one of: {CONDITION_OPERATORS_LIST}"
        )

    config = SIGNAL_METRICS_CONFIG[metric_key]

    # Latency: ms or s; convert ms → seconds for PromQL.
    if config["signal"] == "latency":
        unit = (threshold_unit or "s").strip().lower()
        if unit not in THRESHOLD_UNIT_LATENCY:
            raise ValidationError(
                f"Invalid threshold_unit for latency: '{threshold_unit}'. Use 'ms' or 's'."
            )
        threshold_seconds = threshold_value / 1000.0 if unit == "ms" else threshold_value
        quantile = config["quantile"]
        expr = (
            f'histogram_quantile({quantile}, sum by (le, endpoint, tenant) '
            f'(rate(telemetry_obsv_request_duration_seconds_bucket'
            f'{{endpoint=~"/.*inference.*"}}[5m])))'
        )
        return f"{expr} {op} {threshold_seconds}"

    # Error rate: percent.
    if config["signal"] == "error_rate":
        unit = (threshold_unit or "%").strip().lower()
        if unit not in THRESHOLD_UNIT_PERCENT and unit != "ratio":
            raise ValidationError(
                "Invalid threshold_unit for error rate. Use '%' (percent)."
            )
        thresh = (
            threshold_value / 100.0 if unit in THRESHOLD_UNIT_PERCENT else threshold_value
        )
        status_regex = config["status_regex"]
        num = (
            f'sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total'
            f'{{status_code=~"{status_regex}", endpoint=~"/.*inference.*"}}[5m]))'
        )
        den = (
            f'sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total'
            f'{{endpoint=~"/.*inference.*"}}[5m]))'
        )
        return f"({num} / {den}) {op} {thresh}"

    # Infrastructure: CPU / Memory / Disk — percent threshold.
    if "infra_type" in config:
        unit = (threshold_unit or "%").strip().lower()
        if unit not in THRESHOLD_UNIT_PERCENT:
            raise ValidationError(
                "Invalid threshold_unit for infrastructure. Use '%' (percent)."
            )
        infra = config["infra_type"]
        if infra == "cpu":
            expr = (
                '100 * (1 - (sum(rate(node_cpu_seconds_total{mode="idle"}[5m])) '
                '/ sum(rate(node_cpu_seconds_total[5m]))))'
            )
        elif infra == "memory":
            expr = 'max(100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)))'
        elif infra == "disk":
            expr = (
                'max(100 * (1 - (node_filesystem_avail_bytes'
                '{fstype!~"tmpfs|ramfs|overlay", mountpoint="/"} '
                '/ node_filesystem_size_bytes{fstype!~"tmpfs|ramfs|overlay", mountpoint="/"})))'
            )
        else:
            raise ValidationError(f"Unsupported infra_type '{infra}'.")
        return f"{expr} {op} {threshold_value}"

    raise ValidationError(
        f"Unsupported signal '{config.get('signal', '')}' in config."
    )


# ── Inference task (endpoint) scoping ────────────────────────────────────────


def _normalize_tasks(tasks: Optional[List[str]]) -> List[str]:
    """Normalize inference task name(s) to canonical lowercased keys.

    Accepts a single string or a list. Strips a legacy ``-service`` suffix
    (e.g. ``nmt-service`` → ``nmt``) and de-duplicates while preserving order.
    Raises ``ValidationError`` for any task not in ``INFERENCE_TASKS``.
    """
    if not tasks:
        return []
    if isinstance(tasks, str):
        s = tasks.strip()
        raw_list = [s] if s else []
    else:
        raw_list = [str(s).strip() for s in tasks if s and str(s).strip()]
    result: List[str] = []
    for name in raw_list:
        if not name:
            continue
        key = name.lower()
        if key.endswith(SERVICE_SUFFIX):
            key = key[: -len(SERVICE_SUFFIX)]
        if key not in INFERENCE_TASKS:
            raise ValidationError(
                f"Unknown inference task '{name}'. Must be one of: {list(INFERENCE_TASKS)}"
            )
        if key not in result:
            result.append(key)
    return result


def inject_endpoint_into_promql(promql_expr: str, tasks: Optional[List[str]]) -> str:
    """Narrow the inference ``endpoint`` selector to specific task(s).

    Replaces the broad ``endpoint=~"/.*inference.*"`` matcher emitted by the
    builders with a task-scoped selector:
      - 1 task:  ``endpoint="/api/v1/inference/nmt"`` (exact match)
      - 2+ tasks: ``endpoint=~"/api/v1/inference/(nmt|asr)"`` (RE2 alternation)

    No-op when ``tasks`` is empty (the rule stays scoped to all inference
    endpoints) or when the expression has no inference endpoint selector
    (e.g. infrastructure rules built on ``node_*`` metrics).
    """
    task_list = _normalize_tasks(tasks)
    if not task_list:
        return promql_expr

    if len(task_list) == 1:
        new_selector = f'endpoint="{INFERENCE_ENDPOINT_PREFIX}/{task_list[0]}"'
    else:
        pattern = "|".join(task_list)
        new_selector = f'endpoint=~"{INFERENCE_ENDPOINT_PREFIX}/({pattern})"'

    return promql_expr.replace(_DEFAULT_ENDPOINT_SELECTOR, new_selector)
