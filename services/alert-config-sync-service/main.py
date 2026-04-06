"""
Alert Configuration Sync Service
Generates Prometheus and Alertmanager YAML files from database and triggers hot reload
"""
import os
import asyncio
import asyncpg
import yaml
from yaml.representer import SafeRepresenter
import httpx
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager
import logging

# Custom YAML representer for HTML literal blocks
class HTMLLiteral(str):
    """Marker class for HTML content that should be formatted as YAML literal block"""
    pass

def html_literal_representer(dumper, data):
    """Custom YAML representer for HTML literal blocks"""
    # Ensure the string ends with a newline to get '|' instead of '|-'
    if not data.endswith('\n'):
        data = data + '\n'
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

# Register the custom representer at module level
yaml.add_representer(HTMLLiteral, html_literal_representer)

# Configuration (import first so logging config can use it)
from ai4icore_env import app_env

# Configure structured logging (JSON) so Fluent Bit forwards logs to OpenSearch
try:
    from ai4icore_logging import get_logger, configure_logging
    configure_logging(
        service_name=app_env.service_name,
        use_kafka=app_env.use_kafka_logging,
    )
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

DB_HOST = app_env.postgres_host
DB_PORT = app_env.postgres_port
DB_USER = app_env.postgres_user
DB_PASSWORD = app_env.postgres_password
DB_NAME = "alerting_db"

# Auth DB (same host/user/password, different database) - for resolving ADMIN emails for default receiver
AUTH_DB_NAME = app_env.auth_db_name

# Multi-tenant DB (same host/user/password) - for resolving tenant name -> tenant_id and tenant user email. Set via MULTI_TENANT_DB_NAME env.
MULTI_TENANT_DB_NAME = (app_env.multi_tenant_db_name or os.getenv("MULTI_TENANT_DB_NAME") or "").strip() or None

PROMETHEUS_URL = app_env.prometheus_url
ALERTMANAGER_URL = app_env.alertmanager_url

# Paths for YAML files (mounted volumes)
PROMETHEUS_APPLICATION_ALERTS_PATH = app_env.prometheus_application_alerts_path
PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH = app_env.prometheus_infrastructure_alerts_path
ALERTMANAGER_CONFIG_PATH = app_env.alertmanager_config_path

# Alert Management Service URL (for webhook receivers)
ALERT_MANAGEMENT_SERVICE_URL = app_env.alert_management_service_url or os.getenv(
    "ALERT_MANAGEMENT_SERVICE_URL", "http://alert-management-service:8098"
)

# Sync interval (seconds)
SYNC_INTERVAL = app_env.sync_interval

# Default receiver (ADMIN role) - fallback emails if auth DB unavailable (comma-separated)
DEFAULT_RECEIVER_EMAILS = app_env.default_receiver_emails

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None
db_pool_lock = asyncio.Lock()
auth_db_pool: Optional[asyncpg.Pool] = None
auth_db_pool_lock = asyncio.Lock()
multi_tenant_db_pool: Optional[asyncpg.Pool] = None
multi_tenant_db_pool_lock = asyncio.Lock()

# Lock to prevent concurrent sync operations
sync_lock = asyncio.Lock()
sync_in_progress = False

async def init_db_pool():
    """Initialize database connection pool (thread-safe)"""
    global db_pool
    async with db_pool_lock:
        if db_pool is None:
            try:
                db_pool = await asyncpg.create_pool(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    min_size=2,
                    max_size=10
                )
                logger.info("Database connection pool initialized")
            except Exception as e:
                logger.error(f"Failed to initialize database pool: {e}")
                raise

async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        logger.info("Database connection pool closed")

async def init_auth_db_pool():
    """Initialize auth database connection pool for resolving ADMIN emails (default receiver)"""
    global auth_db_pool
    async with auth_db_pool_lock:
        if auth_db_pool is None:
            try:
                auth_db_pool = await asyncpg.create_pool(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=AUTH_DB_NAME,
                    min_size=1,
                    max_size=3
                )
                logger.info("Auth database connection pool initialized")
            except Exception as e:
                logger.warning(f"Auth database pool not available: {e}, default receiver will use DEFAULT_RECEIVER_EMAILS env")

async def close_auth_db_pool():
    """Close auth database connection pool"""
    global auth_db_pool
    if auth_db_pool:
        await auth_db_pool.close()
        auth_db_pool = None
        logger.info("Auth database connection pool closed")

async def init_multi_tenant_db_pool():
    """Initialize multi-tenant database connection pool for resolving tenant name to tenant_id and tenant user email. Requires MULTI_TENANT_DB_NAME env."""
    global multi_tenant_db_pool
    async with multi_tenant_db_pool_lock:
        if multi_tenant_db_pool is None and MULTI_TENANT_DB_NAME:
            try:
                multi_tenant_db_pool = await asyncpg.create_pool(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=MULTI_TENANT_DB_NAME,
                    min_size=1,
                    max_size=3
                )
                logger.info("Multi-tenant database connection pool initialized")
            except Exception as e:
                logger.warning(f"Could not initialize multi_tenant_db pool (tenant resolution will be skipped): {e}")
                multi_tenant_db_pool = None
        elif not MULTI_TENANT_DB_NAME:
            logger.debug("MULTI_TENANT_DB_NAME not set; tenant resolution will be skipped")

async def close_multi_tenant_db_pool():
    """Close multi-tenant database connection pool"""
    global multi_tenant_db_pool
    if multi_tenant_db_pool:
        await multi_tenant_db_pool.close()
        multi_tenant_db_pool = None
        logger.info("Multi-tenant database connection pool closed")

async def resolve_tenant_name_to_tenant_id_and_emails(tenant_name: str) -> Optional[Tuple[str, List[str]]]:
    """
    Resolve tenant name to (tenant_id, list of emails) using multi_tenant_db and auth_db.
    Matches tenant by organization_name only (case-insensitive, trimmed); then auth_db users where is_tenant=true.
    Returns (tenant_id, [emails]) or None if not found or no tenant user.
    """
    if not tenant_name or not str(tenant_name).strip():
        return None
    tenant_name = str(tenant_name).strip()
    try:
        if multi_tenant_db_pool is None:
            await init_multi_tenant_db_pool()
        if multi_tenant_db_pool is None:
            logger.warning("multi_tenant_db pool not available; cannot resolve tenant to tenant_id/emails")
            return None
        async with multi_tenant_db_pool.acquire() as conn:
            # Match by organization_name only (case-insensitive, trimmed)
            row = await conn.fetchrow(
                """
                SELECT tenant_id, user_id
                FROM tenants
                WHERE LOWER(TRIM(organization_name)) = LOWER(TRIM($1))
                LIMIT 1
                """,
                tenant_name
            )
            if not row:
                logger.info(f"Tenant not found in multi_tenant_db for organization_name '{tenant_name}'")
                return None
            tenant_id = str(row['tenant_id'])
            user_id = row.get('user_id')
            if user_id is None:
                logger.info(f"Tenant '{tenant_name}' (tenant_id={tenant_id}) has no user_id in multi_tenant_db; no tenant user email available")
                return (tenant_id, [])
        # Resolve tenant user email from auth_db (user where is_tenant = true)
        if auth_db_pool is None:
            await init_auth_db_pool()
        if auth_db_pool is None:
            logger.warning("auth_db pool not available; cannot resolve tenant user email")
            return (tenant_id, [])
        async with auth_db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT email FROM users
                WHERE id = $1 AND is_tenant = true AND is_active = true AND email IS NOT NULL AND email != ''
                """,
                user_id
            )
            emails = [r['email'] for r in rows if r.get('email')]
        if not emails:
            logger.info(f"Tenant '{tenant_name}' (tenant_id={tenant_id}, user_id={user_id}): no auth_db user with is_tenant=true and valid email")
        else:
            logger.info(f"Resolved tenant '{tenant_name}' -> tenant_id={tenant_id}, {len(emails)} tenant user email(s)")
        return (tenant_id, emails)
    except Exception as e:
        logger.warning(f"Failed to resolve tenant '{tenant_name}' to tenant_id/emails: {e}")
        return None



async def fetch_admin_emails() -> List[str]:
    """Fetch email addresses of active users with ADMIN role from auth DB for default receiver."""
    return await fetch_emails_by_role("ADMIN")

async def fetch_emails_by_role(role_name: str) -> List[str]:
    """Fetch email addresses of active users with the given RBAC role from auth DB."""
    if auth_db_pool is None:
        await init_auth_db_pool()
    if auth_db_pool is None:
        return list(DEFAULT_RECEIVER_EMAILS) if role_name == "ADMIN" else []
    valid_roles = ("ADMIN", "MODERATOR", "USER", "GUEST")
    if role_name not in valid_roles:
        logger.warning(f"Invalid role '{role_name}' for email resolution")
        return []
    try:
        async with auth_db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT u.email
                FROM users u
                INNER JOIN user_roles ur ON u.id = ur.user_id
                INNER JOIN roles r ON ur.role_id = r.id
                WHERE r.name = $1 AND u.is_active = true AND u.email IS NOT NULL AND u.email != ''
                ORDER BY u.email
                """,
                role_name,
            )
            emails = [row["email"] for row in rows if row.get("email")]
            if emails:
                logger.info(f"Resolved {len(emails)} {role_name} user(s) for receivers")
            if role_name == "ADMIN" and not emails:
                return list(DEFAULT_RECEIVER_EMAILS)
            return emails
    except Exception as e:
        logger.warning(f"Could not fetch {role_name} emails from auth DB: {e}")
        return list(DEFAULT_RECEIVER_EMAILS) if role_name == "ADMIN" else []

async def fetch_alert_definitions() -> List[Dict[str, Any]]:
    """Fetch all enabled alert definitions from database"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                ad.*,
                COALESCE(
                    json_agg(
                        json_build_object('key', aa.annotation_key, 'value', aa.annotation_value)
                    ) FILTER (WHERE aa.annotation_key IS NOT NULL),
                    '[]'::json
                ) as annotations
            FROM alert_definitions ad
            LEFT JOIN alert_annotations aa ON ad.id = aa.alert_definition_id
            WHERE ad.enabled = true
            GROUP BY ad.id
            ORDER BY ad.organization, ad.category, ad.severity
            """
        )
        return [dict(row) for row in rows]

async def fetch_notification_receivers() -> List[Dict[str, Any]]:
    """Fetch all enabled notification receivers from database"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM notification_receivers
            WHERE enabled = true
            ORDER BY organization, receiver_name
            """
        )
        return [dict(row) for row in rows]

async def fetch_routing_rules() -> List[Dict[str, Any]]:
    """Fetch all enabled routing rules from database"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM routing_rules
            WHERE enabled = true
            ORDER BY organization, priority ASC
            """
        )
        return [dict(row) for row in rows]

def inject_tenant_into_promql(expr: str) -> str:
    """
    Ensure application alert PromQL preserves the metric's tenant label so firing alerts
    can be routed by tenant in Alertmanager. Idempotent: does not double-inject.
    """
    if not expr:
        return expr
    import re
    # If already has tenant in group-by, leave as-is
    if ", tenant)" in expr:
        return expr
    # Latency-style: sum by (le, endpoint) -> sum by (le, endpoint, tenant)
    expr = re.sub(
        r'sum by\s*\(\s*le\s*,\s*endpoint\s*\)',
        'sum by (le, endpoint, tenant)',
        expr,
    )
    # Error-rate-style: sum by (endpoint) -> sum by (endpoint, tenant)
    expr = re.sub(
        r'sum by\s*\(\s*endpoint\s*\)',
        'sum by (endpoint, tenant)',
        expr,
    )
    return expr


def sanitize_promql_service_regex(expr: str) -> str:
    """
    Normalize PromQL regex label matchers for `service=~"..."`
    by removing unnecessary escaped hyphens (`\\-` -> `-`).
    This keeps generated rules valid even if older DB records contain
    backslash-escaped hyphens from previous generator behavior.
    """
    if not expr:
        return expr

    import re

    def _fix_service_matcher(match):
        inner = match.group(1).replace(r"\-", "-")
        return f'service=~"{inner}"'

    return re.sub(r'service=~"([^"]*)"', _fix_service_matcher, expr)


def generate_prometheus_alerts_yaml(alert_definitions: List[Dict[str, Any]], category: str = None) -> Dict[str, Any]:
    """
    Generate Prometheus alerts.yml structure from alert definitions.
    
    If category is specified, only generates alerts for that category.
    Otherwise generates all alerts grouped by category.
    
    Alerts are global: no organization in labels or annotations; alertname is the definition name only.
    """
    # Filter by category if specified
    if category:
        alert_definitions = [a for a in alert_definitions if a['category'] == category]
    
    # Group alerts by category (or use single category if filtered)
    groups_by_category = {}
    
    for alert in alert_definitions:
        alert_category = alert['category']
        alert_name = alert['name']
        
        # Use alert name as-is so alertname label does not expose organization
        unique_alert_name = alert_name
        
        # Build alert rule (no organization in labels; alerts are global)
        # Preserve metric tenant label in expr so Alertmanager can route by tenant
        promql_expr = inject_tenant_into_promql(alert['promql_expr'])
        promql_expr = sanitize_promql_service_regex(promql_expr)
        alert_rule = {
            'alert': unique_alert_name,
            'expr': promql_expr,
            'for': alert['for_duration'],
            'labels': {
                'severity': alert['severity'],
                'urgency': alert.get('urgency', 'medium'),
                'category': alert_category,
            }
        }
        
        # Add optional labels
        if alert.get('alert_type'):
            alert_rule['labels']['alert_type'] = alert['alert_type']
        if alert.get('scope'):
            alert_rule['labels']['scope'] = alert['scope']
        
        # Add annotations from database
        annotations = {}
        if alert.get('annotations'):
            for ann in alert['annotations']:
                if isinstance(ann, dict):
                    annotations[ann.get('key', '')] = ann.get('value', '')
        
        # Add default annotations if not present.
        # These are used by Alertmanager email templates (current value, threshold, signal display, etc.).
        if 'summary' not in annotations:
            annotations['summary'] = alert_name
        if 'description' not in annotations:
            annotations['description'] = alert.get('description', f"Alert {alert_name} is firing")

        # Helper: parse service -> friendly names (only if the alert targets a single service).
        def _normalize_service_for_display(svc: Any) -> str:
            s = (str(svc) or "").strip().lower()
            if s.endswith("-service"):
                s = s[: -len("-service")]
            return s

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

        # Helper: format signal display for the email templates.
        def _signal_display_from_alert(a: Dict[str, Any]) -> str:
            sm = (str(a.get("signal_metric") or "")).strip().lower()
            sig = (str(a.get("signal") or "")).strip().lower()

            if sm.startswith("latency_p"):
                p = sm.replace("latency_p", "").upper()
                return f"Latency - P{p}"
            if sm.startswith("latency_"):
                # Fallback: e.g. latency_p95 -> Latency p95
                rest = sm.replace("latency_", "").replace("_", " ").title()
                return f"Latency - {rest}"
            if sm.startswith("error_rate_"):
                rest = sm.replace("error_rate_", "").replace("_", " ").upper()
                return f"Error Rate - {rest}"
            if a.get("category") == "infrastructure" and sm:
                return sm.replace("_", " ").title()
            if sig and sm:
                return f"{sig.title()} - {sm.replace('_', ' ').title()}"
            if sm:
                return sm.replace("_", " ").title()
            return str(a.get("alert_type") or sig or "").strip() or "Unknown Signal"

        # Helper: format threshold/condition display so it matches what PromQL evaluates ($value).
        def _threshold_display_from_alert(a: Dict[str, Any]) -> tuple[str, str]:
            # returns (threshold_display, unit_for_display)
            cat = (str(a.get("category") or "")).strip().lower()
            threshold_value = a.get("threshold_value")
            threshold_unit = (str(a.get("threshold_unit") or "")).strip().lower()
            cond_op = (str(a.get("condition_operator") or ">") or ">").strip()
            for_duration = a.get("for_duration") or ""

            # Latency PromQL outputs seconds, even if threshold_unit was "ms" (builder converts internally).
            is_latency = (str(a.get("signal") or "")).strip().lower() == "latency" or (str(a.get("alert_type") or "")).strip().lower() == "latency"
            if cat == "application" and is_latency:
                if threshold_unit == "ms":
                    threshold_eval_value = float(threshold_value) / 1000.0
                    unit_eval = "s"
                else:
                    threshold_eval_value = float(threshold_value)
                    unit_eval = "s"
                # Avoid trailing .0
                val_str = f"{threshold_eval_value:.3f}".rstrip("0").rstrip(".")
                threshold_display = f"{val_str}{unit_eval}"
                condition_display = f"{_signal_display_from_alert(a)} {cond_op} {val_str}{unit_eval} sustained for {for_duration}"
                return threshold_display, condition_display

            # Error rate PromQL returns ratio (0..1) when threshold_unit is '%'.
            is_error_rate = (str(a.get("signal") or "")).strip().lower() == "error_rate" or (str(a.get("alert_type") or "")).strip().lower() == "error_rate"
            if cat == "application" and is_error_rate:
                threshold_eval_value = float(threshold_value) / 100.0 if threshold_unit in {"%", "percent", "percentage"} else float(threshold_value)
                val_str = f"{threshold_eval_value:.3f}".rstrip("0").rstrip(".")
                threshold_display = f"{val_str}ratio"
                condition_display = f"{_signal_display_from_alert(a)} {cond_op} {val_str}ratio sustained for {for_duration}"
                return threshold_display, condition_display

            # Infrastructure: CPU/Memory/Disk expressions output percentages and compare to threshold_value directly.
            val_str = f"{float(threshold_value):.3f}".rstrip("0").rstrip(".") if threshold_value is not None else ""
            threshold_display = f"{val_str}%" if threshold_unit in {"%", "percent", "percentage", ""} else f"{val_str}{threshold_unit}"
            condition_display = f"{_signal_display_from_alert(a)} {cond_op} {threshold_display} sustained for {for_duration}"
            return threshold_display, condition_display

        if "signal_display" not in annotations:
            annotations["signal_display"] = _signal_display_from_alert(alert)

        if "service_type_abbr" not in annotations or "service_type_full" not in annotations:
            svc_list = alert.get("service") or []
            if isinstance(svc_list, str):
                svc_list = [svc_list]
            svc_list = [x for x in (svc_list or []) if x and str(x).strip()]
            if len(svc_list) == 1:
                svc_key = _normalize_service_for_display(svc_list[0])
                svc_meta = SERVICE_TYPE_MAP.get(svc_key)
                if svc_meta:
                    annotations["service_type_abbr"] = annotations.get("service_type_abbr", svc_meta["abbr"])
                    annotations["service_type_full"] = annotations.get("service_type_full", svc_meta["full"])

        # Category display based on sub_category (when present)
        if "category_display" not in annotations:
            sub = (str(alert.get("sub_category") or "")).strip().lower()
            annotations["category_display"] = {
                "performance": "Service Performance",
                "availability": "Service Availability",
                "compute": "Service Compute",
                "storage": "Service Storage",
            }.get(sub, (sub.title() if sub else str(alert_category).title()))

        if "current_value" not in annotations:
            # Prometheus will replace {{ $value }} with the current firing value.
            annotations["current_value"] = "{{ $value }}"

        if "threshold_display" not in annotations or "condition_display" not in annotations:
            threshold_display, condition_display = _threshold_display_from_alert(alert)
            annotations.setdefault("threshold_display", threshold_display)
            annotations.setdefault("condition_display", condition_display)

        if "sustained_for" not in annotations:
            annotations["sustained_for"] = str(alert.get("for_duration") or "")
        
        alert_rule['annotations'] = annotations
        
        # Group by category
        group_name = f"{alert_category}-alerts"
        if group_name not in groups_by_category:
            groups_by_category[group_name] = {
                'name': group_name,
                'interval': alert.get('evaluation_interval', '30s'),
                'rules': []
            }
        
        groups_by_category[group_name]['rules'].append(alert_rule)
    
    # Convert to list format expected by Prometheus
    groups = list(groups_by_category.values())
    
    return {'groups': groups}

# Note: we intentionally do not keep any "legacy" email template defaults.
# If a receiver doesn't specify custom templates, we always use the new ones below.


def _format_environment_title(env: str) -> str:
    env_norm = (env or "").strip().lower()
    if env_norm in {"production", "prod", "live"}:
        return "Production"
    if env_norm in {"staging"}:
        return "Staging"
    if env_norm in {"dev", "development", "local", "test"}:
        return "Dev"
    return env_norm.title() if env_norm else "Dev"


ENVIRONMENT_TITLE = _format_environment_title(os.getenv("ENVIRONMENT") or app_env.environment or "dev")


# New templates:
# - "Global" receiver: tenant shown as "Global (All Tenants)"
# - "Tenant Admin" receiver: tenant shown from alert label `.Labels.tenant`
GLOBAL_EMAIL_SUBJECT_TEMPLATE = (
    "[{{ if eq .GroupLabels.severity \"critical\" }}CRITICAL{{ else if eq .GroupLabels.severity \"warning\" }}WARNING{{ else }}INFO{{ end }}] "
    "{{ .GroupLabels.alertname }} — "
    + ENVIRONMENT_TITLE
    + "- "
    "{{ if eq .GroupLabels.severity \"critical\" }}Service Impacted{{ else if eq .GroupLabels.severity \"warning\" }}Service Degrading{{ else }}For Your Awareness{{ end }}"
)

TENANT_EMAIL_SUBJECT_TEMPLATE = (
    "[{{ if eq .GroupLabels.severity \"critical\" }}CRITICAL{{ else if eq .GroupLabels.severity \"warning\" }}WARNING{{ else }}INFO{{ end }}] "
    "{{ .GroupLabels.alertname }} — "
    + ENVIRONMENT_TITLE
    + "- "
    "{{ if eq .GroupLabels.severity \"critical\" }}Service Impacted{{ else if eq .GroupLabels.severity \"warning\" }}Service Degrading{{ else }}For Your Awareness{{ end }}"
)


GLOBAL_EMAIL_BODY_TEMPLATE = """<h2 style="color: {{if eq .GroupLabels.severity \"critical\"}}#d32f2f{{else if eq .GroupLabels.severity \"warning\"}}#f57c00{{else}}#1976d2{{end}};">
  {{if eq .GroupLabels.severity "critical"}}CRITICAL{{else if eq .GroupLabels.severity "warning"}}WARNING{{else}}INFO{{end}}: {{(index .Alerts 0).Annotations.signal_display}}
</h2>
<p><strong>Alert Name</strong></p>
<p>{{ .GroupLabels.alertname }}</p>

<p><strong>Category</strong></p>
<p>{{ index (index .Alerts 0).Annotations "category_display" }}</p>

<p><strong>Signal</strong></p>
<p>{{ index (index .Alerts 0).Annotations "signal_display" }}</p>

<p><strong>Service Type</strong></p>
<p>{{ index (index .Alerts 0).Annotations "service_type_full" }}</p>

<p><strong>Tenant</strong></p>
<p>Global (All Tenants)</p>

<p><strong>Environment</strong></p>
<p>__ENVIRONMENT_TITLE__</p>

<p><strong>Condition</strong></p>
<p>{{ index (index .Alerts 0).Annotations "condition_display" }}</p>

<p><strong>Current Value</strong></p>
<p>{{ index (index .Alerts 0).Annotations "current_value" }}</p>

<p><strong>Threshold</strong></p>
<p>{{ index (index .Alerts 0).Annotations "threshold_display" }}</p>

<p><strong>Triggered At</strong></p>
<p>{{ (index .Alerts 0).StartsAt }}</p>

<p><strong>Sustained For</strong></p>
<p>{{ index (index .Alerts 0).Annotations "sustained_for" }}</p>
"""

TENANT_EMAIL_BODY_TEMPLATE = """<h2 style="color: {{if eq .GroupLabels.severity \"critical\"}}#d32f2f{{else if eq .GroupLabels.severity \"warning\"}}#f57c00{{else}}#1976d2{{end}};">
  {{if eq .GroupLabels.severity "critical"}}CRITICAL{{else if eq .GroupLabels.severity "warning"}}WARNING{{else}}INFO{{end}}: {{(index .Alerts 0).Annotations.signal_display}}
</h2>
<p><strong>Alert Name</strong></p>
<p>{{ .GroupLabels.alertname }}</p>

<p><strong>Category</strong></p>
<p>{{ index (index .Alerts 0).Annotations "category_display" }}</p>

<p><strong>Signal</strong></p>
<p>{{ index (index .Alerts 0).Annotations "signal_display" }}</p>

<p><strong>Service Type</strong></p>
<p>{{ index (index .Alerts 0).Annotations "service_type_full" }}</p>

<p><strong>Tenant</strong></p>
<p>{{ (index .Alerts 0).Labels.tenant }}</p>

<p><strong>Environment</strong></p>
<p>__ENVIRONMENT_TITLE__</p>

<p><strong>Condition</strong></p>
<p>{{ index (index .Alerts 0).Annotations "condition_display" }}</p>

<p><strong>Current Value</strong></p>
<p>{{ index (index .Alerts 0).Annotations "current_value" }}</p>

<p><strong>Threshold</strong></p>
<p>{{ index (index .Alerts 0).Annotations "threshold_display" }}</p>

<p><strong>Triggered At</strong></p>
<p>{{ (index .Alerts 0).StartsAt }}</p>

<p><strong>Sustained For</strong></p>
<p>{{ index (index .Alerts 0).Annotations "sustained_for" }}</p>
"""

# Inject environment title without interfering with Alertmanager Go-template braces.
GLOBAL_EMAIL_BODY_TEMPLATE = GLOBAL_EMAIL_BODY_TEMPLATE.replace("__ENVIRONMENT_TITLE__", ENVIRONMENT_TITLE)
TENANT_EMAIL_BODY_TEMPLATE = TENANT_EMAIL_BODY_TEMPLATE.replace("__ENVIRONMENT_TITLE__", ENVIRONMENT_TITLE)


# Backwards compatible aliases (kept for existing code paths)
DEFAULT_EMAIL_SUBJECT_TEMPLATE = GLOBAL_EMAIL_SUBJECT_TEMPLATE
DEFAULT_EMAIL_BODY_TEMPLATE = GLOBAL_EMAIL_BODY_TEMPLATE

def get_global_config_from_env() -> Dict[str, Any]:
    """
    Build global SMTP config from environment variables.
    In Docker, env comes from docker-compose env_file: ./.env and environment: SMTP_*=${SMTP_*} (same pattern as alert-management-service).
    Keys with no value are omitted so the YAML does not contain 'key: null'.
    """
    out: Dict[str, Any] = {
        'resolve_timeout': '5m',
    }
    smtp_smarthost = (os.getenv('SMTP_SMARTHOST') or '').strip()
    smtp_from = (os.getenv('SMTP_FROM') or '').strip()
    smtp_auth_username = (os.getenv('SMTP_AUTH_USERNAME') or '').strip()
    smtp_auth_password = (os.getenv('SMTP_AUTH_PASSWORD') or '').strip()

    if smtp_smarthost:
        out['smtp_smarthost'] = smtp_smarthost
    if smtp_from:
        out['smtp_from'] = smtp_from
    if smtp_auth_username:
        out['smtp_auth_username'] = smtp_auth_username
    if smtp_auth_password:
        out['smtp_auth_password'] = smtp_auth_password
    if 'smtp_smarthost' in out:
        out['smtp_require_tls'] = True

    if out.get('smtp_smarthost'):
        logger.info(
            "SMTP global config from env: smtp_smarthost=%s smtp_from=%s smtp_auth_username=%s auth_password_set=%s",
            out.get('smtp_smarthost'), out.get('smtp_from'), out.get('smtp_auth_username'), bool(out.get('smtp_auth_password')),
        )
    else:
        logger.warning(
            "SMTP env vars not set (SMTP_SMARTHOST empty). Set SMTP_* in .env next to docker-compose and use env_file: ./.env (same as alert-management-service)."
        )

    return out


def load_global_config_from_file() -> Dict[str, Any]:
    """
    Load global SMTP configuration from existing alertmanager.yml file.
    Preserves only the global section. Falls back to env if file missing/fails.
    """
    try:
        if os.path.exists(ALERTMANAGER_CONFIG_PATH):
            with open(ALERTMANAGER_CONFIG_PATH, 'r') as f:
                existing_config = yaml.safe_load(f)
                if existing_config and 'global' in existing_config:
                    logger.info("Loaded global SMTP config from existing alertmanager.yml")
                    return existing_config['global']
    except Exception as e:
        logger.warning(f"Failed to load global config from file: {e}, using defaults")
    
    return {
        'resolve_timeout': '5m',
        'smtp_smarthost': app_env.smtp_smarthost,
        'smtp_from': app_env.smtp_from,
        'smtp_auth_username': app_env.smtp_auth_username,
        'smtp_auth_password': app_env.smtp_auth_password,
        'smtp_require_tls': True
    }

def generate_alertmanager_yaml(
    receivers: List[Dict[str, Any]],
    routing_rules: List[Dict[str, Any]],
    default_admin_emails: Optional[List[str]] = None,
    tenant_resolution_map: Optional[Dict[str, Tuple[str, List[str]]]] = None,
    role_emails_map: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Generate Alertmanager configuration from receivers and routing rules.
    tenant_resolution_map: tenant_name -> (tenant_id, [emails]) = auth user with is_tenant=true for that tenant.
    role_emails_map: rbac_role -> [emails] for non-tenant receivers (default ADMIN when role not set).
    """
    tenant_resolution_map = tenant_resolution_map or {}
    role_emails_map = role_emails_map or {}
    # Always use env for global config when generating (so SMTP is never hardcoded)
    global_config = get_global_config_from_env()
    
    default_admin_emails = default_admin_emails or []
    default_receiver_name = "default-admin"

    # Alert history webhook receiver: include so all alerts are also sent here for audit log
    alert_history_webhook_url = f"{ALERT_MANAGEMENT_SERVICE_URL}/alerts/history/webhook"
    receivers_config = [
        {
            "name": "alert-history-webhook",
            "webhook_configs": [{"url": alert_history_webhook_url, "send_resolved": False}],
        }
    ]

    # Build receivers: add the default receiver (not tied to any organization, ADMIN role)
    default_email_configs = []
    for email in default_admin_emails:
        if email and str(email).strip():
            cfg = {
                'to': str(email).strip(),
                'send_resolved': False,
                'html': DEFAULT_EMAIL_BODY_TEMPLATE,
            }
            # Alertmanager email subject (kept in headers to allow templating).
            cfg['headers'] = {'Subject': DEFAULT_EMAIL_SUBJECT_TEMPLATE}
            default_email_configs.append(cfg)
    receivers_config.append({
        'name': default_receiver_name,
        'email_configs': default_email_configs,
    })
    if not default_email_configs:
        logger.warning("Default receiver 'default-admin' has no email addresses; set DEFAULT_RECEIVER_EMAILS or ensure auth DB has ADMIN users")

    # Build receivers from database: merge by (severity, category) when receiver_name is "severity-category"; else one per receiver_name (alert_names/tenant)
    receivers_by_severity_category = {}  # (severity, category) -> list of email_configs to merge
    receivers_by_unique_name = {}  # receiver_name -> list of email_configs (for names containing "--")
    
    for receiver in receivers:
        receiver_name = receiver['receiver_name']
        tenant_name = (receiver.get('tenant') or '').strip() or None

        if tenant_name:
            # Tenant set: use only the auth user with is_tenant=true for this tenant (tenant_resolution_map).
            if tenant_name not in tenant_resolution_map:
                logger.warning(f"Receiver '{receiver_name}' (tenant={tenant_name}): tenant not in resolution map, skipping")
                continue
            _tid, tenant_emails = tenant_resolution_map[tenant_name]
            email_list = [e for e in tenant_emails if e and str(e).strip()]
            if not email_list:
                logger.warning(f"Receiver '{receiver_name}' (tenant={tenant_name}): no tenant user email (is_tenant=true), skipping")
                continue
        else:
            # No tenant: use all emails for rbac_role (default ADMIN) from auth DB. Ignore stored email_to.
            effective_role = (receiver.get("rbac_role") or "").strip() or "ADMIN"
            email_list = role_emails_map.get(effective_role, [])
            email_list = [e for e in email_list if e and str(e).strip()]
            if not email_list:
                logger.warning(f"Receiver '{receiver_name}' (role={effective_role}): no emails for role, skipping")
                continue
        
        email_configs = []

        is_tenant_receiver = bool((receiver.get("tenant") or "").strip())
        default_subject_template = TENANT_EMAIL_SUBJECT_TEMPLATE if is_tenant_receiver else GLOBAL_EMAIL_SUBJECT_TEMPLATE
        default_body_template = TENANT_EMAIL_BODY_TEMPLATE if is_tenant_receiver else GLOBAL_EMAIL_BODY_TEMPLATE

        stored_subject = receiver.get("email_subject_template")
        email_subject_template = (
            default_subject_template
            if not stored_subject or not str(stored_subject).strip()
            else stored_subject
        )
    
        stored_body = receiver.get("email_body_template")
        email_body_template = (
            default_body_template
            if not stored_body or not str(stored_body).strip()
            else stored_body
        )

        for email in email_list:
            if email and str(email).strip():
                cfg = {
                    'to': str(email).strip(),
                    'send_resolved': False,
                    'html': email_body_template,
                }
                # Alertmanager email subject (kept in headers to allow templating).
                cfg['headers'] = {'Subject': email_subject_template}
                email_configs.append(cfg)
        
        if not email_configs:
            logger.warning(f"No valid email addresses for receiver '{receiver_name}' (org: {receiver.get('organization')})")
            continue
        
        # Unique receiver name (contains "--") -> one Alertmanager receiver per name
        if '--' in receiver_name:
            if receiver_name not in receivers_by_unique_name:
                receivers_by_unique_name[receiver_name] = []
            receivers_by_unique_name[receiver_name].extend(email_configs)
            continue
        
        # Legacy: severity-category (no --) -> merge by (severity, category)
        parts = receiver_name.split('-', 1)
        if len(parts) != 2:
            logger.warning(f"Receiver name '{receiver_name}' doesn't follow pattern 'severity-category', skipping")
            continue
        severity, category = parts
        key = (severity, category)
        if key not in receivers_by_severity_category:
            receivers_by_severity_category[key] = []
        receivers_by_severity_category[key].extend(email_configs)
    
    # One Alertmanager receiver per (severity, category) with merged email_configs (legacy)
    for (severity, category), email_configs in receivers_by_severity_category.items():
        receiver_name_am = f"{severity}-{category}"
        receivers_config.append({
            'name': receiver_name_am,
            'email_configs': email_configs,
        })
    # One Alertmanager receiver per unique name (alert_names/tenant)
    for name, email_configs in receivers_by_unique_name.items():
        receivers_config.append({
            'name': name,
            'email_configs': email_configs,
        })
    
    # Build routing tree: one route per routing rule; match severity, category, optional alert_type, optional alertname, optional tenant
    root_routes = []
    valid_receiver_names = {r['name'] for r in receivers_config}
    receivers_by_id = {r['id']: r for r in receivers}
    
    # Sort rules by priority (lower first); then put rules with more matchers (tenant, alert_names) first for same priority
    def route_sort_key(rule):
        r = receivers_by_id.get(rule.get('receiver_id'), {})
        has_tenant = bool((r.get('tenant') or '').strip())
        has_alert_names = bool(rule.get('match_alert_names'))
        return (rule.get('priority', 100), 0 if (has_tenant or has_alert_names) else 1)
    
    for rule in sorted(routing_rules, key=route_sort_key):
        receiver = receivers_by_id.get(rule.get('receiver_id'))
        if not receiver:
            continue
        receiver_name_db = receiver['receiver_name']
        # Alertmanager receiver name: unique name if contains "--", else severity-category
        if '--' in receiver_name_db:
            receiver_name_am = receiver_name_db
        else:
            sev, cat = rule.get('match_severity'), rule.get('match_category')
            if not sev or not cat:
                continue
            receiver_name_am = f"{sev}-{cat}"
        
        if receiver_name_am not in valid_receiver_names:
            continue
        
        match_conditions = {
            'severity': rule.get('match_severity'),
            'category': rule.get('match_category'),
        }
        if rule.get('match_alert_type'):
            match_conditions['alert_type'] = rule['match_alert_type']
        
        # Optional: match specific alert names (alertname label in Prometheus)
        match_alert_names = rule.get('match_alert_names')
        match_re_alertname = None
        if match_alert_names and isinstance(match_alert_names, (list, tuple)):
            names = [n for n in match_alert_names if n and str(n).strip()]
            if len(names) == 1:
                match_conditions['alertname'] = names[0]
            elif len(names) > 1:
                import re
                match_re_alertname = '|'.join(re.escape(n) for n in names)
        
        # Optional: match tenant (tenant label in metrics)
        tenant_name = (receiver.get('tenant') or '').strip() or None
        if tenant_name and tenant_name in tenant_resolution_map:
            tenant_id, _ = tenant_resolution_map[tenant_name]
            match_conditions['tenant'] = tenant_id
        
        route = {
            'match': match_conditions,
            'receiver': receiver_name_am,
            'group_wait': rule.get('group_wait') or '10s',
            'group_interval': rule.get('group_interval') or '10s',
            'repeat_interval': rule.get('repeat_interval') or '12h',
            'continue': True
        }
        if match_re_alertname:
            route['match_re'] = {'alertname': match_re_alertname}
        if rule.get('group_by'):
            route['group_by'] = rule['group_by']
        root_routes.append(route)
    
    # Prepend catch-all route so every alert is also sent to alert-history-webhook (continue so other routes still run)
    root_routes.insert(0, {
        "receiver": "alert-history-webhook",
        "continue": True,
    })
    
    # Deduplicate and ensure we don't have duplicate match sets (Alertmanager uses first match)
    # Only include routes whose receiver exists
    root_routes = [r for r in root_routes if r.get('receiver') in valid_receiver_names]

    # Build complete Alertmanager configuration
    route_config = {
        'group_by': ['alertname', 'category', 'severity', 'tenant'],
        'group_wait': '10s',
        'group_interval': '10s',
        'repeat_interval': '12h'
    }
    route_config['receiver'] = default_receiver_name
    route_config['routes'] = root_routes
    
    if not root_routes:
        logger.info("No severity/category routes; all alerts will go to default-admin receiver.")

    # Sanitize global: drop any key that is None or empty string so YAML never gets "key: null"
    global_sanitized = {
        k: v for k, v in global_config.items()
        if v is not None and (v != '' if isinstance(v, str) else True)
    }

    config = {
        'global': global_sanitized,
        'route': route_config,
        'receivers': receivers_config
    }
    config['inhibit_rules'] = [
        {
            'source_match': {'severity': 'critical'},
            'target_match': {'severity': 'warning'},
            'equal': ['alertname', 'category']
        }
    ]
    return config

async def validate_prometheus_config(config: Dict[str, Any]) -> bool:
    """
    Validate Prometheus configuration using promtool (if available).
    Returns True if validation passes or promtool is not available.
    """
    try:
        import subprocess
        import tempfile
        
        # Write config to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as tmp_file:
            yaml.dump(config, tmp_file, default_flow_style=False, sort_keys=False, allow_unicode=True)
            tmp_path = tmp_file.name
        
        try:
            # Run promtool check rules
            result = subprocess.run(
                ['promtool', 'check', 'rules', tmp_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info("Prometheus configuration validated successfully")
                return True
            else:
                logger.error(f"Prometheus configuration validation failed: {result.stderr}")
                return False
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except FileNotFoundError:
        # promtool not available, skip validation
        logger.debug("promtool not available, skipping validation")
        return True
    except Exception as e:
        logger.warning(f"Validation check failed: {e}, proceeding anyway")
        return True  # Don't block on validation errors

async def write_yaml_file(file_path: str, data: Dict[str, Any], validate: bool = True) -> None:
    """
    Write YAML data to file atomically.
    
    For Prometheus alerts.yml, optionally validates using promtool before writing.
    For Alertmanager config, writes directly to avoid "Device or resource busy" errors with volume mounts.
    """
    # For Alertmanager config, write directly (it's a volume mount that Alertmanager watches)
    # For Prometheus rules, use atomic rename
    is_alertmanager_config = file_path == ALERTMANAGER_CONFIG_PATH or 'alertmanager' in file_path.lower()
    
    if is_alertmanager_config:
        # Write directly to file (Alertmanager watches for file changes)
        # Retry logic to handle file locks
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Write directly to the file
                # 'to' field is now a single string, so no special formatting needed
                # HTML templates need to be formatted as YAML literal blocks (|) for proper parsing
                # Convert HTML strings to HTMLLiteral before dumping
                def convert_html_to_literal(obj):
                    """Recursively convert 'html' field values to HTMLLiteral"""
                    if isinstance(obj, dict):
                        return {k: HTMLLiteral(v) if k == 'html' and isinstance(v, str) else convert_html_to_literal(v) 
                                for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_html_to_literal(item) for item in obj]
                    else:
                        return obj
                
                # Convert the data structure
                data_with_literals = convert_html_to_literal(data)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    yaml.dump(
                        data_with_literals, 
                        f, 
                        default_flow_style=False,  # Use block style
                        sort_keys=False, 
                        allow_unicode=True,
                        width=1000,  # Prevent line wrapping
                        indent=2  # Ensure consistent 2-space indentation
                    )
                
                logger.info(f"Successfully wrote {file_path} ({os.path.getsize(file_path)} bytes)")
                
                # Log file contents for debugging (first 500 chars)
                with open(file_path, 'r') as f:
                    preview = f.read(500)
                    logger.debug(f"File preview (first 500 chars): {preview}")
                return  # Success, exit retry loop
            except (OSError, IOError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to write {file_path} (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to write {file_path} after {max_retries} attempts: {e}", exc_info=True)
                    raise
            except Exception as e:
                logger.error(f"Failed to write {file_path}: {e}", exc_info=True)
                raise
    else:
        # For Prometheus rules, use atomic rename
        temp_path = f"{file_path}.tmp"
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    data, 
                    f, 
                    default_flow_style=False,  # Use block style
                    sort_keys=False, 
                    allow_unicode=True,
                    width=1000,
                    indent=2
                )
            
            # Validate if requested (for Prometheus configs)
            if validate:
                if not await validate_prometheus_config(data):
                    raise ValueError("Prometheus configuration validation failed")
            
            # Atomically rename
            os.replace(temp_path, file_path)
            logger.info(f"Successfully wrote {file_path} ({os.path.getsize(file_path)} bytes)")
        except Exception as e:
            logger.error(f"Failed to write {file_path}: {e}", exc_info=True)
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

async def trigger_prometheus_reload() -> bool:
    """Trigger Prometheus configuration reload via HTTP API"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{PROMETHEUS_URL}/-/reload")
            if response.status_code == 200:
                logger.info("Prometheus configuration reloaded successfully")
                return True
            else:
                logger.warning(f"Prometheus reload returned status {response.status_code}: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to trigger Prometheus reload: {e}")
        return False

async def trigger_alertmanager_reload() -> bool:
    """Trigger Alertmanager configuration reload via POST /-/reload (enabled by default in Alertmanager)."""
    try:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{ALERTMANAGER_URL}/-/reload")
                if response.status_code == 200:
                    logger.info("Alertmanager configuration reloaded successfully via HTTP API")
                    return True
                else:
                    logger.warning(
                        "Alertmanager reload returned status %s: %s. "
                        "Config was written but not loaded; restart the alertmanager container to apply.",
                        response.status_code,
                        response.text,
                    )
                    return False
        except Exception as e:
            logger.debug("Alertmanager HTTP reload not available: %s", e)

        # Reload API unreachable - config will not reload until container restart
        logger.warning(
            "Alertmanager config was written but reload request failed. "
            "Restart the alertmanager container to apply the new config."
        )
        return False
    except Exception as e:
        logger.error("Failed to trigger Alertmanager reload: %s", e)
        return False

async def sync_configuration(blocking: bool = True) -> None:
    """
    Main sync function: fetch from DB, generate YAML, write files, trigger reload
    
    Args:
        blocking: If True, wait for lock (for manual syncs). If False, skip if lock is held (for periodic syncs).
    """
    global sync_in_progress
    
    # Check if sync is already in progress
    if sync_in_progress:
        if blocking:
            # Manual sync: wait a bit and retry
            await asyncio.sleep(0.5)
            if sync_in_progress:
                raise Exception("cannot perform operation: another operation is in progress")
        else:
            # Periodic sync: just skip
            logger.debug("Sync already in progress, skipping periodic sync")
            return
    
    # Try to acquire lock (non-blocking for periodic sync, blocking for manual sync)
    if blocking:
        # Manual sync: wait for lock (with timeout)
        try:
            await asyncio.wait_for(sync_lock.acquire(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Could not acquire sync lock within timeout, another sync may be in progress")
            raise Exception("cannot perform operation: another operation is in progress")
    else:
        # Periodic sync: try to acquire lock with very short timeout, skip if can't get it
        try:
            await asyncio.wait_for(sync_lock.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            logger.debug("Could not acquire lock for periodic sync, skipping this cycle")
            return
    
    try:
        if sync_in_progress:
            logger.warning("Sync already in progress, skipping this request")
            sync_lock.release()
            raise Exception("cannot perform operation: another operation is in progress")
        
        sync_in_progress = True
        try:
            logger.info("Starting configuration sync...")
            
            # Ensure DB pool is initialized
            if db_pool is None:
                await init_db_pool()
            
            # Fetch data from database
            alert_definitions = await fetch_alert_definitions()
            receivers = await fetch_notification_receivers()
            routing_rules = await fetch_routing_rules()
            
            logger.info(f"Fetched {len(alert_definitions)} alert definitions, {len(receivers)} receivers, {len(routing_rules)} routing rules")
            
            # Log receiver details for debugging
            if receivers:
                logger.info(f"Receivers: {[{'id': r['id'], 'organization': r['organization'], 'name': r['receiver_name'], 'enabled': r.get('enabled', True)} for r in receivers]}")
            else:
                logger.warning("No enabled receivers found in database!")
            
            # Resolve ADMIN emails for default receiver (not tied to any organization)
            default_admin_emails = await fetch_admin_emails()

            # Build role -> [emails] for non-tenant receivers (rbac_role default ADMIN)
            roles_needed = set()
            for r in receivers:
                if not (r.get("tenant") or "").strip():
                    roles_needed.add((r.get("rbac_role") or "").strip() or "ADMIN")
            role_emails_map = {"ADMIN": default_admin_emails}
            for role in roles_needed:
                if role != "ADMIN":
                    role_emails_map[role] = await fetch_emails_by_role(role)

            # Resolve tenant names to (tenant_id, emails) for receivers that have tenant set
            tenant_resolution_map = {}
            unique_tenant_names = set()
            for r in receivers:
                t = (r.get('tenant') or '').strip() or None
                if t:
                    unique_tenant_names.add(t)
            for tname in unique_tenant_names:
                resolved = await resolve_tenant_name_to_tenant_id_and_emails(tname)
                if resolved:
                    tenant_id, emails = resolved
                    tenant_resolution_map[tname] = resolved
                    if emails:
                        logger.info(f"Tenant '{tname}' resolved to tenant_id={tenant_id}, {len(emails)} email(s) for receiver routing")
                    else:
                        logger.warning(f"Tenant '{tname}' resolved to tenant_id={tenant_id} but no tenant user email; tenant receivers will be skipped")
                else:
                    logger.warning(f"Could not resolve tenant '{tname}' to tenant_id/emails; tenant receivers will be skipped")

            # Generate YAML configurations - separate files for application and infrastructure
            application_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='application')
            infrastructure_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='infrastructure')
            alertmanager_config = generate_alertmanager_yaml(
                receivers, routing_rules,
                default_admin_emails=default_admin_emails,
                tenant_resolution_map=tenant_resolution_map,
                role_emails_map=role_emails_map,
            )
            
            # Write YAML files - separate files for application and infrastructure alerts
            await write_yaml_file(PROMETHEUS_APPLICATION_ALERTS_PATH, application_alerts)
            await write_yaml_file(PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH, infrastructure_alerts)
            await write_yaml_file(ALERTMANAGER_CONFIG_PATH, alertmanager_config, validate=False)
            
            # Trigger reloads
            prometheus_ok = await trigger_prometheus_reload()
            alertmanager_ok = await trigger_alertmanager_reload()
            
            if prometheus_ok and alertmanager_ok:
                logger.info("Configuration sync completed successfully")
            else:
                logger.warning("Configuration sync completed with warnings")
            
        except Exception as e:
            logger.error(f"Configuration sync failed: {e}", exc_info=True)
            raise
        finally:
            sync_in_progress = False
    finally:
        # Always release the lock (even if an exception occurred)
        try:
            sync_lock.release()
        except RuntimeError:
            # Lock was already released, ignore
            pass

async def periodic_sync():
    """Periodically sync configuration"""
    await init_db_pool()
    
    # Initial sync
    try:
        await sync_configuration()
    except Exception as e:
        logger.error(f"Initial sync failed: {e}")
    
    # Periodic sync
    while True:
        try:
            await asyncio.sleep(SYNC_INTERVAL)
            await sync_configuration()
        except Exception as e:
            logger.error(f"Periodic sync failed: {e}")
            # Continue even if sync fails
            await asyncio.sleep(SYNC_INTERVAL)

async def run_periodic_sync():
    """Run periodic sync in background (non-blocking - skips if manual sync is running)"""
    await init_db_pool()
    
    # Initial sync (blocking - we want it to run on startup)
    try:
        await sync_configuration(blocking=True)
    except Exception as e:
        logger.error(f"Initial sync failed: {e}")
    
    # Periodic sync (non-blocking - skip if manual sync is in progress)
    while True:
        try:
            await asyncio.sleep(SYNC_INTERVAL)
            # Non-blocking: skip if manual sync is running
            await sync_configuration(blocking=False)
        except Exception as e:
            # Only log if it's a real error, not a "skip" case
            if "skipping" not in str(e).lower():
                logger.error(f"Periodic sync failed: {e}")
            # Continue even if sync fails or is skipped

# HTTP endpoint for manual sync trigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Background sync task (set by lifespan, cancelled on shutdown)
_sync_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start periodic sync in the same event loop as the app; close pools on shutdown."""
    global _sync_task
    _sync_task = asyncio.create_task(run_periodic_sync())
    logger.info("Background configuration sync task started")
    try:
        yield
    finally:
        if _sync_task and not _sync_task.done():
            _sync_task.cancel()
            try:
                await _sync_task
            except asyncio.CancelledError:
                pass
            logger.info("Background sync task stopped")
        await close_db_pool()
        await close_auth_db_pool()
        await close_multi_tenant_db_pool()
        logger.info("Database connection pools closed")


app = FastAPI(title="Alert Config Sync Service", lifespan=lifespan)

@app.post("/sync")
async def trigger_sync_endpoint():
    """Manually trigger configuration sync (called by API Gateway after create/update/delete)"""
    try:
        # Ensure DB pool is initialized (lifespan starts sync task which calls init_db_pool)
        if db_pool is None:
            await init_db_pool()
        
        # Manual sync: blocking (will wait for periodic sync to finish if needed)
        await sync_configuration(blocking=True)
        return {"status": "success", "message": "Configuration synced successfully"}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Manual sync failed: {error_msg}", exc_info=True)
        
        # Return appropriate status code based on error
        if "another operation is in progress" in error_msg.lower():
            status_code = 409
        else:
            status_code = 500
            
        return JSONResponse(
            status_code=status_code,
            content={"status": "error", "message": error_msg}
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "alert-config-sync-service"}


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Alert Configuration Sync Service...")

    # Background sync is already started by the FastAPI `lifespan()` handler
    # (runs in the same event loop as the app). No extra thread needed here.

    # Start HTTP server for manual triggers
    try:
        port = app_env.port
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Close pools if still open
        if db_pool:
            asyncio.run(close_db_pool())
        if auth_db_pool:
            asyncio.run(close_auth_db_pool())

