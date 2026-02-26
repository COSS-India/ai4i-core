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
from typing import List, Dict, Any, Optional
from datetime import datetime
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

# Configure structured logging (JSON) so Fluent Bit forwards logs to OpenSearch
try:
    from ai4icore_logging import get_logger, configure_logging
    configure_logging(
        service_name=os.getenv("SERVICE_NAME", "alert-config-sync-service"),
        use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
    )
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

# Configuration
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_USER = os.getenv("POSTGRES_USER", "dhruva_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "dhruva_secure_password_2024")
DB_NAME = "alerting_db"

# Auth DB (same host/user/password, different database) - for resolving ADMIN emails for default receiver
AUTH_DB_NAME = os.getenv("AUTH_DB_NAME", "auth_db")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")

# Paths for YAML files (mounted volumes)
PROMETHEUS_APPLICATION_ALERTS_PATH = os.getenv("PROMETHEUS_APPLICATION_ALERTS_PATH", "/etc/prometheus/rules/application-alerts.yml")
PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH = os.getenv("PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH", "/etc/prometheus/rules/infrastructure-alerts.yml")
ALERTMANAGER_CONFIG_PATH = os.getenv("ALERTMANAGER_CONFIG_PATH", "/etc/alertmanager/alertmanager.yml")

# Sync interval (seconds)
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "60"))

# Default receiver (ADMIN role) - fallback emails if auth DB unavailable (comma-separated)
DEFAULT_RECEIVER_EMAILS = [e.strip() for e in (os.getenv("DEFAULT_RECEIVER_EMAILS") or "").split(",") if e and e.strip()]

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None
db_pool_lock = asyncio.Lock()
auth_db_pool: Optional[asyncpg.Pool] = None
auth_db_pool_lock = asyncio.Lock()

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

async def fetch_admin_emails() -> List[str]:
    """Fetch email addresses of active users with ADMIN role from auth DB for default receiver."""
    if auth_db_pool is None:
        await init_auth_db_pool()
    if auth_db_pool is None:
        return list(DEFAULT_RECEIVER_EMAILS)
    try:
        async with auth_db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT u.email
                FROM users u
                INNER JOIN user_roles ur ON u.id = ur.user_id
                INNER JOIN roles r ON ur.role_id = r.id
                WHERE r.name = 'ADMIN' AND u.is_active = true
                ORDER BY u.email
                """,
            )
            emails = [row['email'] for row in rows if row.get('email')]
            if emails:
                logger.info(f"Resolved {len(emails)} ADMIN user(s) for default receiver")
            return emails if emails else list(DEFAULT_RECEIVER_EMAILS)
    except Exception as e:
        logger.warning(f"Could not fetch ADMIN emails from auth DB: {e}, using DEFAULT_RECEIVER_EMAILS")
        return list(DEFAULT_RECEIVER_EMAILS)

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
        alert_rule = {
            'alert': unique_alert_name,
            'expr': alert['promql_expr'],
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
        
        # Add default annotations if not present
        if 'summary' not in annotations:
            annotations['summary'] = alert_name
        if 'description' not in annotations:
            annotations['description'] = alert.get('description', f"Alert {alert_name} is firing")
        
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

# Default email templates (no organization; route by severity/category only)
DEFAULT_EMAIL_SUBJECT_TEMPLATE = "[{{ if eq .GroupLabels.severity \"critical\" }}CRITICAL{{ else if eq .GroupLabels.severity \"warning\" }}WARNING{{ else }}INFO{{ end }}] {{ .GroupLabels.alertname }}{{ with (index .Alerts 0).Labels.endpoint }} - {{ . }}{{ end }}"
DEFAULT_EMAIL_BODY_TEMPLATE = """<h2 style="color: {{ if eq .GroupLabels.severity \"critical\" }}#d32f2f{{ else if eq .GroupLabels.severity \"warning\" }}#f57c00{{ else }}#1976d2{{ end }};">
  {{ if eq .GroupLabels.severity "critical" }}🚨 CRITICAL{{ else if eq .GroupLabels.severity "warning" }}⚠️ WARNING{{ else }}ℹ️ INFO{{ end }}: {{ .GroupLabels.category | title }} Alert
</h2>
<p><strong>Alert:</strong> {{ .GroupLabels.alertname }}</p>
<p><strong>Severity:</strong> {{ .GroupLabels.severity }}</p>
<p><strong>Category:</strong> {{ .GroupLabels.category }}</p>
"""

def load_global_config_from_file() -> Dict[str, Any]:
    """
    Load global SMTP configuration from existing alertmanager.yml file.
    Preserves only the global section (lines 1-7).
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
    
    # Fallback to defaults if file doesn't exist or can't be read
    return {
        'resolve_timeout': '5m',
        'smtp_smarthost': os.getenv('SMTP_SMARTHOST', 'smtp.gmail.com:587'),
        'smtp_from': os.getenv('SMTP_FROM', 'bharathia0704@gmail.com'),
        'smtp_auth_username': os.getenv('SMTP_AUTH_USERNAME', 'bharathia0704@gmail.com'),
        'smtp_auth_password': os.getenv('SMTP_AUTH_PASSWORD', 'ypuaofsbatebvwye'),
        'smtp_require_tls': True
    }

def generate_alertmanager_yaml(
    receivers: List[Dict[str, Any]],
    routing_rules: List[Dict[str, Any]],
    default_admin_emails: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate Alertmanager configuration from receivers and routing rules.
    Preserves global SMTP config from existing file, everything else comes from database.
    Always includes a default receiver 'default-admin' (ADMIN role, not tied to any organization).
    Only routes whose receiver still exists in the config are included (stale routes removed).
    """
    # Load global config from existing file (preserves SMTP settings)
    global_config = load_global_config_from_file()
    
    default_admin_emails = default_admin_emails or []
    default_receiver_name = "default-admin"

    # Build receivers: first add the default receiver (not tied to any organization, ADMIN role)
    receivers_config = []
    default_email_configs = []
    for email in default_admin_emails:
        if email and str(email).strip():
            default_email_configs.append({
                'to': str(email).strip(),
                'send_resolved': True,
                'headers': {'Subject': DEFAULT_EMAIL_SUBJECT_TEMPLATE},
                'html': DEFAULT_EMAIL_BODY_TEMPLATE
            })
    receivers_config.append({
        'name': default_receiver_name,
        'email_configs': default_email_configs,
    })
    if not default_email_configs:
        logger.warning("Default receiver 'default-admin' has no email addresses; set DEFAULT_RECEIVER_EMAILS or ensure auth DB has ADMIN users")

    # Build receivers from database: one receiver per (severity, category), merge emails from all orgs
    # Receiver name = severity-category (e.g. warning-application), no organization
    receivers_by_severity_category = {}  # (severity, category) -> list of email_configs to merge
    
    for receiver in receivers:
        receiver_name = receiver['receiver_name']
        # Parse receiver name: format severity-category (e.g. "warning-application")
        parts = receiver_name.split('-', 1)
        if len(parts) != 2:
            logger.warning(f"Receiver name '{receiver_name}' doesn't follow pattern 'severity-category', skipping")
            continue
        severity, category = parts
        key = (severity, category)
        
        # Build email configs for this DB receiver
        email_configs = []
        if receiver.get('email_to'):
            email_to = receiver['email_to']
            if isinstance(email_to, str):
                email_list = [email_to]
            elif isinstance(email_to, list):
                email_list = email_to
            else:
                email_list = list(email_to) if email_to else []
            
            email_subject_template = receiver.get('email_subject_template') or DEFAULT_EMAIL_SUBJECT_TEMPLATE
            email_body_template = receiver.get('email_body_template') or DEFAULT_EMAIL_BODY_TEMPLATE
            
            for email in email_list:
                if email and str(email).strip():
                    email_config = {
                        'to': str(email).strip(),
                        'send_resolved': True,
                        'headers': {'Subject': email_subject_template},
                        'html': email_body_template
                    }
                    email_configs.append(email_config)
        
        if not email_configs:
            logger.warning(f"No valid email addresses for receiver '{receiver_name}' (org: {receiver.get('organization')})")
            continue
        
        if key not in receivers_by_severity_category:
            receivers_by_severity_category[key] = []
        receivers_by_severity_category[key].extend(email_configs)
    
    # One Alertmanager receiver per (severity, category) with merged email_configs
    for (severity, category), email_configs in receivers_by_severity_category.items():
        receiver_name_alertmanager = f"{severity}-{category}"
        receivers_config.append({
            'name': receiver_name_alertmanager,
            'email_configs': email_configs,
        })
    
    # Build routing tree: one route per (severity, category), receiver = severity-category (no organization)
    # Use explicit routing rules when available (custom group_wait, match_alert_type, etc.); else defaults
    root_routes = []
    valid_receiver_names = {r['name'] for r in receivers_config}
    
    # Build map (severity, category) -> best explicit rule (lowest priority wins; any org)
    explicit_rule_by_key = {}
    if routing_rules:
        # Sort by priority ascending (lower = higher priority)
        for rule in sorted(routing_rules, key=lambda r: r.get('priority', 100)):
            sev = rule.get('match_severity')
            cat = rule.get('match_category')
            if sev and cat:
                key = (sev, cat)
                if key not in explicit_rule_by_key:
                    explicit_rule_by_key[key] = rule
    
    for (severity, category) in receivers_by_severity_category.keys():
        receiver_name_alertmanager = f"{severity}-{category}"
        if receiver_name_alertmanager not in valid_receiver_names:
            continue
        explicit_rule = explicit_rule_by_key.get((severity, category))
        match_conditions = {'severity': severity, 'category': category}
        if explicit_rule and explicit_rule.get('match_alert_type'):
            match_conditions['alert_type'] = explicit_rule['match_alert_type']
        route = {
            'match': match_conditions,
            'receiver': receiver_name_alertmanager,
            'group_wait': (explicit_rule or {}).get('group_wait') or '10s',
            'group_interval': (explicit_rule or {}).get('group_interval') or '10s',
            'repeat_interval': (explicit_rule or {}).get('repeat_interval') or '12h',
            'continue': True
        }
        if explicit_rule and explicit_rule.get('group_by'):
            route['group_by'] = explicit_rule['group_by']
        root_routes.append(route)
        logger.debug(f"Route for severity={severity} category={category} -> receiver {receiver_name_alertmanager}" + (" (explicit rule)" if explicit_rule else " (defaults)"))
    
    # Only include routes whose receiver exists in our config (remove stale routes for deleted receivers)
    before_count = len(root_routes)
    root_routes = [r for r in root_routes if r.get('receiver') in valid_receiver_names]
    if len(root_routes) < before_count:
        logger.warning(f"Removed {before_count - len(root_routes)} route(s) that referenced non-existent receivers")

    # Build complete Alertmanager configuration
    # Only global config is preserved from file, everything else from database
    route_config = {
        'group_by': ['alertname', 'category', 'severity'],
        'group_wait': '10s',
        'group_interval': '10s',
        'repeat_interval': '12h'
    }
    
    # Root default receiver is always default-admin (not tied to any organization, ADMIN role)
    route_config['receiver'] = default_receiver_name
    
    # Routes: only include routes for receivers that exist in config
    if not root_routes:
        logger.info("No severity/category routes; all alerts will go to default-admin receiver.")
    route_config['routes'] = root_routes
    
    config = {
        'global': global_config,
        'route': route_config,
        'receivers': receivers_config
    }
    
    # Add inhibition rules (optional, can be configured via API later)
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
    """Trigger Alertmanager configuration reload"""
    try:
        # Alertmanager can reload via HTTP API or SIGHUP
        # Try HTTP API first (Alertmanager 0.16+)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{ALERTMANAGER_URL}/-/reload")
                if response.status_code == 200:
                    logger.info("Alertmanager configuration reloaded successfully via HTTP API")
                    return True
                else:
                    logger.warning(f"Alertmanager reload returned status {response.status_code}: {response.text}")
        except Exception as e:
            logger.debug(f"Alertmanager HTTP reload not available: {e}")
        
        # Fallback: Alertmanager watches config file for changes
        # File modification will trigger automatic reload
        logger.info("Alertmanager will reload automatically when config file changes")
        return True
    except Exception as e:
        logger.error(f"Failed to trigger Alertmanager reload: {e}")
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

            # Generate YAML configurations - separate files for application and infrastructure
            application_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='application')
            infrastructure_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='infrastructure')
            alertmanager_config = generate_alertmanager_yaml(receivers, routing_rules, default_admin_emails=default_admin_emails)
            
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

app = FastAPI(title="Alert Config Sync Service")

@app.post("/sync")
async def trigger_sync_endpoint():
    """Manually trigger configuration sync (called by API Gateway after create/update/delete)"""
    try:
        # Ensure DB pool is initialized (should already be from startup)
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

async def start_background_sync():
    """Start periodic sync in background task"""
    try:
        await run_periodic_sync()
    except Exception as e:
        logger.error(f"Background sync task failed: {e}")

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Alert Configuration Sync Service...")
    
    # Start periodic sync in background
    import threading
    sync_thread = threading.Thread(target=lambda: asyncio.run(start_background_sync()), daemon=True)
    sync_thread.start()
    
    # Start HTTP server for manual triggers
    try:
        port = int(os.getenv("PORT", "8097"))
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Close pools if still open
        if db_pool:
            asyncio.run(close_db_pool())
        if auth_db_pool:
            asyncio.run(close_auth_db_pool())

