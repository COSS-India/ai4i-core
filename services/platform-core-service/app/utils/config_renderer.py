"""Prometheus/Alertmanager config rendering + hot-reload HTTP clients.

Stateless utilities — every function takes inputs and either returns a data
structure (YAML-renderers) or performs I/O against caller-provided paths/URLs
(``write_yaml_file``, ``trigger_*_reload``). No global state, no DB.

Lifted from alert-config-sync-service/main.py:18-1180 with these changes:
  - ``organization`` tracking removed from labels, annotations, and routing
    match conditions (org-extraction logic dropped per migration plan).
  - URLs and file paths are explicit function arguments, not module-level env
    reads. The caller (sync_service) supplies them from ``settings``.
  - Email templates are pulled from ``app.utils.email_templates`` so there's
    one source of truth (was duplicated across both source services).
  - The ``alert-history-webhook`` receiver URL is now a parameter, since the
    merged service self-routes alerts to its own ``/alerts/history/webhook``.

The HTML email body is emitted as a YAML literal block (``|``) — Alertmanager
expects HTML in the literal style; the ``HTMLLiteral`` representer below makes
PyYAML do that.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import httpx
import yaml

from app.utils.email_templates import EmailTemplates, format_email_templates

logger = logging.getLogger(__name__)


# ── HTML literal-block YAML representer ──────────────────────────────────────


class HTMLLiteral(str):
    """Marker class — strings of this type emit as YAML literal blocks (``|``)."""


def _html_literal_representer(dumper, data):
    if not data.endswith("\n"):
        data = data + "\n"
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(HTMLLiteral, _html_literal_representer)


# ── PromQL post-processors (applied right before YAML write) ─────────────────


def inject_tenant_into_promql(expr: str) -> str:
    """Ensure application alert PromQL groups by ``tenant`` so Alertmanager can
    route by it. Idempotent — leaves expressions already grouping by tenant alone.
    """
    if not expr:
        return expr
    if ", tenant)" in expr:
        return expr
    expr = re.sub(
        r"sum by\s*\(\s*le\s*,\s*endpoint\s*\)",
        "sum by (le, endpoint, tenant)",
        expr,
    )
    expr = re.sub(
        r"sum by\s*\(\s*endpoint\s*\)",
        "sum by (endpoint, tenant)",
        expr,
    )
    return expr


def sanitize_promql_service_regex(expr: str) -> str:
    """Unescape backslash-escaped hyphens inside ``service=~"..."`` matchers."""
    if not expr:
        return expr

    def _fix(match: re.Match) -> str:
        inner = match.group(1).replace(r"\-", "-")
        return f'service=~"{inner}"'

    return re.sub(r'service=~"([^"]*)"', _fix, expr)


# ── Display helpers (annotation strings on alert rules) ──────────────────────


SERVICE_TYPE_MAP = {
    "asr": {"abbr": "ASR", "full": "ASR (Automatic Speech Recognition)"},
    "nmt": {"abbr": "NMT", "full": "NMT (Neural Machine Translation)"},
    "tts": {"abbr": "TTS", "full": "TTS (Text To Speech)"},
    "ocr": {"abbr": "OCR", "full": "OCR (Optical Character Recognition)"},
    "ner": {"abbr": "NER", "full": "NER (Named Entity Recognition)"},
    "transliteration": {"abbr": "Transliteration", "full": "Transliteration"},
    "language-detection": {"abbr": "LangDetect", "full": "Language Detection"},
    "audio-lang-detection": {"abbr": "AudioLangDetect", "full": "Audio Language Detection"},
    "language-diarization": {"abbr": "LangDiarization", "full": "Language Diarization"},
    "speaker-diarization": {"abbr": "SpeakerDiarization", "full": "Speaker Diarization"},
    "llm": {"abbr": "LLM", "full": "LLM"},
    "pipeline": {"abbr": "Pipeline", "full": "Pipeline"},
}


def _normalize_service_for_display(svc: Any) -> str:
    s = (str(svc) or "").strip().lower()
    if s.endswith("-service"):
        s = s[: -len("-service")]
    return s


def _signal_display_from_alert(a: Dict[str, Any]) -> str:
    """Human-readable label for the signal/metric shown in the email body."""
    sm = str(a.get("signal_metric") or "").strip().lower()
    sig = str(a.get("signal") or "").strip().lower()

    if sm.startswith("latency_p"):
        return f"Latency - P{sm.replace('latency_p', '').upper()}"
    if sm.startswith("latency_"):
        return f"Latency - {sm.replace('latency_', '').replace('_', ' ').title()}"
    if sm.startswith("error_rate_"):
        return f"Error Rate - {sm.replace('error_rate_', '').replace('_', ' ').upper()}"
    if a.get("category") == "infrastructure" and sm:
        return sm.replace("_", " ").title()
    if sig and sm:
        return f"{sig.title()} - {sm.replace('_', ' ').title()}"
    if sm:
        return sm.replace("_", " ").title()
    return str(a.get("alert_type") or sig or "").strip() or "Unknown Signal"


def _threshold_display_from_alert(a: Dict[str, Any]) -> Tuple[str, str]:
    """Returns (threshold_display, condition_display) strings."""
    cat = str(a.get("category") or "").strip().lower()
    threshold_value = a.get("threshold_value")
    threshold_unit = str(a.get("threshold_unit") or "").strip().lower()
    cond_op = (str(a.get("condition_operator") or ">") or ">").strip()
    for_duration = a.get("for_duration") or ""

    is_latency = (
        str(a.get("signal") or "").strip().lower() == "latency"
        or str(a.get("alert_type") or "").strip().lower() == "latency"
    )
    if cat == "application" and is_latency:
        if threshold_value is None:
            return "N/A", f"{_signal_display_from_alert(a)} {cond_op} N/A sustained for {for_duration}"
        eval_val = float(threshold_value) / 1000.0 if threshold_unit == "ms" else float(threshold_value)
        val_str = f"{eval_val:.3f}".rstrip("0").rstrip(".")
        return f"{val_str}s", f"{_signal_display_from_alert(a)} {cond_op} {val_str}s sustained for {for_duration}"

    is_error_rate = (
        str(a.get("signal") or "").strip().lower() == "error_rate"
        or str(a.get("alert_type") or "").strip().lower() == "error_rate"
    )
    if cat == "application" and is_error_rate:
        if threshold_value is None:
            return "N/A", f"{_signal_display_from_alert(a)} {cond_op} N/A sustained for {for_duration}"
        eval_val = (
            float(threshold_value) / 100.0
            if threshold_unit in {"%", "percent", "percentage"}
            else float(threshold_value)
        )
        val_str = f"{eval_val:.3f}".rstrip("0").rstrip(".")
        return (
            f"{val_str}ratio",
            f"{_signal_display_from_alert(a)} {cond_op} {val_str}ratio sustained for {for_duration}",
        )

    val_str = (
        f"{float(threshold_value):.3f}".rstrip("0").rstrip(".") if threshold_value is not None else ""
    )
    threshold_display = (
        f"{val_str}%" if threshold_unit in {"%", "percent", "percentage", ""} else f"{val_str}{threshold_unit}"
    )
    return (
        threshold_display,
        f"{_signal_display_from_alert(a)} {cond_op} {threshold_display} sustained for {for_duration}",
    )


# ── Prometheus alerts.yml generator ──────────────────────────────────────────

_SERVICE_TYPE_FALLBACK_TEMPLATE = (
    '{{ with reReplaceAll "^/api/v[0-9]+/([^/]+)/.*$" "$1" $labels.endpoint }}'
    '{{ if eq . "nmt" }}NMT (Neural Machine Translation)'
    '{{ else if eq . "asr" }}ASR (Automatic Speech Recognition)'
    '{{ else if eq . "tts" }}TTS (Text To Speech)'
    '{{ else if eq . "ocr" }}OCR (Optical Character Recognition)'
    '{{ else if eq . "ner" }}NER (Named Entity Recognition)'
    '{{ else if eq . "transliteration" }}Transliteration'
    '{{ else if eq . "language-detection" }}Language Detection'
    '{{ else if eq . "audio-lang-detection" }}Audio Language Detection'
    '{{ else if eq . "language-diarization" }}Language Diarization'
    '{{ else if eq . "speaker-diarization" }}Speaker Diarization'
    '{{ else if eq . "llm" }}LLM'
    '{{ else if eq . "pipeline" }}Pipeline'
    '{{ else }}{{ . }}'
    "{{ end }}{{ end }}"
)


def generate_prometheus_alerts_yaml(
    alert_definitions: List[Dict[str, Any]],
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Render the ``groups:`` document for ``application-alerts.yml`` or
    ``infrastructure-alerts.yml`` from a list of alert-definition row dicts.

    Each row is expected to have the same fields as ``AlertDefinition`` plus
    an ``annotations`` list of ``{"key": ..., "value": ...}`` dicts.
    """
    if category:
        alert_definitions = [a for a in alert_definitions if a.get("category") == category]

    groups_by_category: Dict[str, Dict[str, Any]] = {}

    for alert in alert_definitions:
        alert_category = alert["category"]
        alert_name = alert["name"]

        # Tenant-aware PromQL + un-escape hyphens in service= matchers.
        promql_expr = sanitize_promql_service_regex(inject_tenant_into_promql(alert["promql_expr"]))

        rule: Dict[str, Any] = {
            "alert": alert_name,
            "expr": promql_expr,
            "for": alert["for_duration"],
            "labels": {
                "severity": alert["severity"],
                "urgency": alert.get("urgency", "medium"),
                "category": alert_category,
            },
        }
        if alert.get("alert_type"):
            rule["labels"]["alert_type"] = alert["alert_type"]
        if alert.get("scope"):
            rule["labels"]["scope"] = alert["scope"]

        # Build annotation dict from DB rows, then fill in defaults.
        annotations: Dict[str, str] = {}
        for ann in alert.get("annotations") or []:
            if isinstance(ann, dict):
                annotations[ann.get("key", "")] = ann.get("value", "")

        annotations.setdefault("summary", alert_name)
        annotations.setdefault(
            "description",
            alert.get("description") or f"Alert {alert_name} is firing",
        )
        annotations.setdefault("signal_display", _signal_display_from_alert(alert))

        # service_type_abbr / service_type_full
        svc_list = alert.get("service") or []
        if isinstance(svc_list, str):
            svc_list = [svc_list]
        svc_list = [x for x in svc_list if x and str(x).strip()]
        if len(svc_list) == 1:
            svc_meta = SERVICE_TYPE_MAP.get(_normalize_service_for_display(svc_list[0]))
            if svc_meta:
                annotations.setdefault("service_type_abbr", svc_meta["abbr"])
                annotations.setdefault("service_type_full", svc_meta["full"])
        annotations.setdefault("service_type_full", _SERVICE_TYPE_FALLBACK_TEMPLATE)

        # category_display
        sub = str(alert.get("sub_category") or "").strip().lower()
        category_display = {
            "performance": "Service Performance",
            "availability": "Service Availability",
            "compute": "Service Compute",
            "storage": "Service Storage",
        }.get(sub, sub.title() if sub else str(alert_category).title())
        annotations.setdefault("category_display", category_display)

        annotations.setdefault("current_value", "{{ $value }}")

        threshold_display, condition_display = _threshold_display_from_alert(alert)
        annotations.setdefault("threshold_display", threshold_display)
        annotations.setdefault("condition_display", condition_display)

        annotations.setdefault("sustained_for", str(alert.get("for_duration") or ""))

        rule["annotations"] = annotations

        group_name = f"{alert_category}-alerts"
        group = groups_by_category.setdefault(
            group_name,
            {"name": group_name, "interval": alert.get("evaluation_interval", "30s"), "rules": []},
        )
        group["rules"].append(rule)

    return {"groups": list(groups_by_category.values())}


# ── Alertmanager SMTP global config ──────────────────────────────────────────


def build_smtp_global_config(
    *,
    smtp_smarthost: Optional[str] = None,
    smtp_from: Optional[str] = None,
    smtp_auth_username: Optional[str] = None,
    smtp_auth_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the ``global`` block (SMTP creds) for alertmanager.yml.

    Keys with no value are omitted so the YAML never contains ``key: null``.
    Values come from the caller (sync_service reads them off settings); falls
    back to ``SMTP_*`` env vars only when an argument is not supplied — handy
    if you export them into the process environment instead.
    """
    out: Dict[str, Any] = {"resolve_timeout": "5m"}
    smarthost = (smtp_smarthost or os.getenv("SMTP_SMARTHOST") or "").strip()
    sender = (smtp_from or os.getenv("SMTP_FROM") or "").strip()
    username = (smtp_auth_username or os.getenv("SMTP_AUTH_USERNAME") or "").strip()
    password = (smtp_auth_password or os.getenv("SMTP_AUTH_PASSWORD") or "").strip()

    if smarthost:
        out["smtp_smarthost"] = smarthost
    if sender:
        out["smtp_from"] = sender
    if username:
        out["smtp_auth_username"] = username
    if password:
        out["smtp_auth_password"] = password
    if "smtp_smarthost" in out:
        out["smtp_require_tls"] = True

    if not out.get("smtp_smarthost"):
        logger.warning(
            "SMTP not configured (smtp_smarthost empty). Alertmanager email delivery "
            "will not work until SMTP_* settings are set."
        )
    return out


# ── Alertmanager.yml generator ───────────────────────────────────────────────


def generate_alertmanager_yaml(
    receivers: List[Dict[str, Any]],
    routing_rules: List[Dict[str, Any]],
    *,
    default_admin_emails: Optional[List[str]] = None,
    tenant_resolution_map: Optional[Dict[str, Tuple[str, List[str]]]] = None,
    role_emails_map: Optional[Dict[str, List[str]]] = None,
    history_webhook_url: Optional[str] = None,
    environment: Optional[str] = None,
    smtp_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Render the full ``alertmanager.yml`` document.

    Args:
      receivers, routing_rules: rows from notification_receivers / routing_rules.
      default_admin_emails: emails to fall back to when no receiver matches.
      tenant_resolution_map: ``{tenant_name: (tenant_id, [emails])}`` from auth_db.
      role_emails_map: ``{rbac_role: [emails]}`` from auth_db.
      history_webhook_url: where to forward all alerts for audit logging — typically
        ``http://platform-core-service:8095/api/v1/alerts/history/webhook``. If
        falsy, the history webhook receiver/route are omitted.
      environment: feeds into the email subject/body via ``email_templates``.
      smtp_config: the ``global`` SMTP block (from ``build_smtp_global_config``); if
        None, falls back to env vars.
    """
    tenant_resolution_map = tenant_resolution_map or {}
    role_emails_map = role_emails_map or {}
    default_admin_emails = default_admin_emails or []
    default_receiver_name = "default-admin"

    global_config = smtp_config if smtp_config is not None else build_smtp_global_config()
    receivers_config: List[Dict[str, Any]] = []

    # Webhook receiver (audit log) — only if URL supplied.
    if history_webhook_url:
        receivers_config.append(
            {
                "name": "alert-history-webhook",
                "webhook_configs": [{"url": history_webhook_url, "send_resolved": False}],
            }
        )

    # Default admin receiver (catch-all).
    default_tmpl = format_email_templates(environment, tenant=None)
    default_email_configs = []
    for email in default_admin_emails:
        if email and str(email).strip():
            default_email_configs.append(
                {
                    "to": str(email).strip(),
                    "send_resolved": False,
                    "html": default_tmpl.body,
                    "headers": {"Subject": default_tmpl.subject},
                }
            )
    receivers_config.append(
        {"name": default_receiver_name, "email_configs": default_email_configs}
    )
    if not default_email_configs:
        logger.warning(
            "Default receiver '%s' has no email addresses; set DEFAULT_RECEIVER_EMAILS "
            "or ensure auth_db has ADMIN users",
            default_receiver_name,
        )

    # DB-driven receivers: merge by (severity, category) for legacy names; one Alertmanager
    # receiver per unique name (contains "--") for tenant/alert-names variants.
    receivers_by_sev_cat: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    receivers_by_unique_name: Dict[str, List[Dict[str, Any]]] = {}

    for receiver in receivers:
        receiver_name = receiver["receiver_name"]
        tenant_name = (receiver.get("tenant") or "").strip() or None

        if tenant_name:
            if tenant_name not in tenant_resolution_map:
                logger.warning(
                    "Receiver '%s' (tenant=%s): tenant not in resolution map, skipping",
                    receiver_name,
                    tenant_name,
                )
                continue
            _tid, tenant_emails = tenant_resolution_map[tenant_name]
            email_list = [e for e in tenant_emails if e and str(e).strip()]
            if not email_list:
                logger.warning(
                    "Receiver '%s' (tenant=%s): no tenant user email, skipping",
                    receiver_name,
                    tenant_name,
                )
                continue
        else:
            effective_role = (receiver.get("rbac_role") or "").strip() or "ADMIN"
            email_list = role_emails_map.get(effective_role, [])
            email_list = [e for e in email_list if e and str(e).strip()]
            if not email_list:
                logger.warning(
                    "Receiver '%s' (role=%s): no emails for role, skipping",
                    receiver_name,
                    effective_role,
                )
                continue

        # Email templates: per-receiver override > tenant default > global default.
        receiver_tmpl = format_email_templates(environment, tenant=tenant_name)
        stored_subject = (receiver.get("email_subject_template") or "").strip()
        stored_body = (receiver.get("email_body_template") or "").strip()
        subject = stored_subject or receiver_tmpl.subject
        body = stored_body or receiver_tmpl.body

        email_configs = []
        for email in email_list:
            if email and str(email).strip():
                email_configs.append(
                    {
                        "to": str(email).strip(),
                        "send_resolved": False,
                        "html": body,
                        "headers": {"Subject": subject},
                    }
                )
        if not email_configs:
            continue

        if "--" in receiver_name:
            receivers_by_unique_name.setdefault(receiver_name, []).extend(email_configs)
            continue

        parts = receiver_name.split("-", 1)
        if len(parts) != 2:
            logger.warning(
                "Receiver name '%s' doesn't follow 'severity-category' pattern; skipping",
                receiver_name,
            )
            continue
        severity, category = parts
        receivers_by_sev_cat.setdefault((severity, category), []).extend(email_configs)

    for (severity, category), email_configs in receivers_by_sev_cat.items():
        receivers_config.append(
            {"name": f"{severity}-{category}", "email_configs": email_configs}
        )
    for name, email_configs in receivers_by_unique_name.items():
        receivers_config.append({"name": name, "email_configs": email_configs})

    # Routing tree.
    valid_receiver_names = {r["name"] for r in receivers_config}
    receivers_by_id = {r["id"]: r for r in receivers}

    def _route_sort_key(rule: Dict[str, Any]) -> Tuple[int, int]:
        r = receivers_by_id.get(rule.get("receiver_id"), {})
        has_tenant = bool((r.get("tenant") or "").strip())
        has_alert_names = bool(rule.get("match_alert_names"))
        return (rule.get("priority", 100), 0 if (has_tenant or has_alert_names) else 1)

    root_routes: List[Dict[str, Any]] = []
    for rule in sorted(routing_rules, key=_route_sort_key):
        receiver = receivers_by_id.get(rule.get("receiver_id"))
        if not receiver:
            continue
        receiver_name_db = receiver["receiver_name"]
        if "--" in receiver_name_db:
            receiver_name_am = receiver_name_db
        else:
            sev = rule.get("match_severity")
            cat = rule.get("match_category")
            if not sev or not cat:
                continue
            receiver_name_am = f"{sev}-{cat}"
        if receiver_name_am not in valid_receiver_names:
            continue

        match_conditions: Dict[str, Any] = {
            "severity": rule.get("match_severity"),
            "category": rule.get("match_category"),
        }
        if rule.get("match_alert_type"):
            match_conditions["alert_type"] = rule["match_alert_type"]

        match_re_alertname: Optional[str] = None
        match_alert_names = rule.get("match_alert_names")
        if match_alert_names and isinstance(match_alert_names, (list, tuple)):
            names = [n for n in match_alert_names if n and str(n).strip()]
            if len(names) == 1:
                match_conditions["alertname"] = names[0]
            elif len(names) > 1:
                match_re_alertname = "|".join(re.escape(n) for n in names)

        tenant_name = (receiver.get("tenant") or "").strip() or None
        if tenant_name and tenant_name in tenant_resolution_map:
            tenant_id, _ = tenant_resolution_map[tenant_name]
            match_conditions["tenant"] = tenant_id

        route: Dict[str, Any] = {
            "match": match_conditions,
            "receiver": receiver_name_am,
            "group_wait": rule.get("group_wait") or "10s",
            "group_interval": rule.get("group_interval") or "10s",
            "repeat_interval": rule.get("repeat_interval") or "12h",
            "continue": True,
        }
        if match_re_alertname:
            route["match_re"] = {"alertname": match_re_alertname}
        if rule.get("group_by"):
            route["group_by"] = rule["group_by"]
        root_routes.append(route)

    # Prepend a catch-all route to the history webhook (continues so other routes still fire).
    if history_webhook_url:
        root_routes.insert(0, {"receiver": "alert-history-webhook", "continue": True})

    root_routes = [r for r in root_routes if r.get("receiver") in valid_receiver_names]

    route_config: Dict[str, Any] = {
        "group_by": ["alertname", "category", "severity", "tenant"],
        "group_wait": "10s",
        "group_interval": "10s",
        "repeat_interval": "12h",
        "receiver": default_receiver_name,
        "routes": root_routes,
    }

    if not root_routes:
        logger.info("No severity/category routes; all alerts will go to default-admin receiver.")

    global_sanitized = {
        k: v for k, v in global_config.items() if v is not None and (v != "" if isinstance(v, str) else True)
    }

    return {
        "global": global_sanitized,
        "route": route_config,
        "receivers": receivers_config,
        "inhibit_rules": [
            {
                "source_match": {"severity": "critical"},
                "target_match": {"severity": "warning"},
                "equal": ["alertname", "category"],
            }
        ],
    }


# ── YAML write + Prometheus validation ───────────────────────────────────────


async def validate_prometheus_config(config: Dict[str, Any]) -> bool:
    """Run ``promtool check rules`` on the rendered config.

    Returns True if validation passes OR ``promtool`` isn't installed
    (we don't want to block writes on the binary being missing).
    """
    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".yml")
        os.close(fd)
        async with aiofiles.open(tmp_path, mode="w") as tmp:
            await tmp.write(yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True))
        try:
            proc = await asyncio.create_subprocess_exec(
                "promtool", "check", "rules", tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.debug("promtool timed out, skipping validation")
            return True
        except FileNotFoundError:
            logger.debug("promtool not available, skipping validation")
            return True
        if proc.returncode == 0:
            logger.info("Prometheus configuration validated successfully")
            return True
        logger.error("Prometheus configuration validation failed: %s", stderr_bytes.decode())
        return False
    except Exception as exc:
        logger.warning("Validation check failed: %s, proceeding anyway", exc)
        return True
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


async def write_yaml_file(
    file_path: str,
    data: Dict[str, Any],
    *,
    validate: bool = True,
) -> None:
    """Write ``data`` to ``file_path`` as YAML.

    - For Alertmanager configs (heuristic: path contains ``alertmanager``), the
      ``html`` field on every email config is converted to ``HTMLLiteral`` so it
      emits as a literal block. Writes directly with retries (volume mounts can
      briefly lock the file).
    - For Prometheus rule files, writes to ``<path>.tmp`` then atomically renames.
      Optionally validates via ``promtool`` first.
    """
    is_alertmanager = file_path == "" or "alertmanager" in os.path.basename(file_path).lower()

    if is_alertmanager:
        data_to_dump = _convert_html_to_literal(data)
        for attempt in range(3):
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                    await f.write(yaml.dump(
                        data_to_dump,
                        default_flow_style=False,
                        sort_keys=False,
                        allow_unicode=True,
                        width=1000,
                        indent=2,
                    ))
                logger.info(
                    "Wrote %s (%d bytes)", file_path, os.path.getsize(file_path)
                )
                return
            except (OSError, IOError) as exc:
                if attempt < 2:
                    logger.warning(
                        "Failed to write %s (attempt %d/3): %s, retrying...",
                        file_path,
                        attempt + 1,
                        exc,
                    )
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    logger.error("Failed to write %s after 3 attempts: %s", file_path, exc)
                    raise
        return

    # Prometheus rules: atomic rename + optional validation.
    temp_path = f"{file_path}.tmp"
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
            await f.write(yaml.dump(
                data,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=1000,
                indent=2,
            ))
        if validate and not await validate_prometheus_config(data):
            raise ValueError("Prometheus configuration validation failed")
        os.replace(temp_path, file_path)
        logger.info("Wrote %s (%d bytes)", file_path, os.path.getsize(file_path))
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def _convert_html_to_literal(obj: Any) -> Any:
    """Recursively convert ``'html': <str>`` fields to ``HTMLLiteral`` so PyYAML emits ``|``."""
    if isinstance(obj, dict):
        return {
            k: (HTMLLiteral(v) if k == "html" and isinstance(v, str) else _convert_html_to_literal(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_convert_html_to_literal(item) for item in obj]
    return obj


# ── Hot-reload HTTP clients ──────────────────────────────────────────────────


async def trigger_prometheus_reload(prometheus_url: str, *, timeout: float = 10.0) -> bool:
    """POST ``<prometheus_url>/-/reload``. Returns True on 200."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{prometheus_url}/-/reload")
        if response.status_code == 200:
            logger.info("Prometheus configuration reloaded successfully")
            return True
        logger.warning(
            "Prometheus reload returned status %d: %s",
            response.status_code,
            response.text,
        )
        return False
    except Exception as exc:
        logger.error("Failed to trigger Prometheus reload: %s", exc)
        return False


async def trigger_alertmanager_reload(alertmanager_url: str, *, timeout: float = 10.0) -> bool:
    """POST ``<alertmanager_url>/-/reload``. Returns True on 200; False otherwise.

    A False result usually means a container restart is needed to pick up the
    config — log message explains.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{alertmanager_url}/-/reload")
        if response.status_code == 200:
            logger.info("Alertmanager configuration reloaded successfully")
            return True
        logger.warning(
            "Alertmanager reload returned status %d: %s. "
            "Config was written but not loaded; restart the alertmanager container.",
            response.status_code,
            response.text,
        )
        return False
    except Exception as exc:
        logger.error("Failed to trigger Alertmanager reload: %s", exc)
        return False
