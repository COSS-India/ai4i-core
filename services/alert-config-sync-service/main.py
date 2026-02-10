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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_USER = os.getenv("POSTGRES_USER", "dhruva_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "dhruva_secure_password_2024")
DB_NAME = "alerting_db"

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")

# Paths for YAML files (mounted volumes)
PROMETHEUS_APPLICATION_ALERTS_PATH = os.getenv("PROMETHEUS_APPLICATION_ALERTS_PATH", "/etc/prometheus/rules/application-alerts.yml")
PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH = os.getenv("PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH", "/etc/prometheus/rules/infrastructure-alerts.yml")
ALERTMANAGER_CONFIG_PATH = os.getenv("ALERTMANAGER_CONFIG_PATH", "/etc/alertmanager/alertmanager.yml")

# Sync interval (seconds)
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "60"))

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None
db_pool_lock = asyncio.Lock()

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
    
    Key insight: Each customer gets their own alert rule, even if monitoring the same metric.
    This ensures customer isolation and allows different thresholds per customer.
    """
    # Filter by category if specified
    if category:
        alert_definitions = [a for a in alert_definitions if a['category'] == category]
    
    # Group alerts by category (or use single category if filtered)
    groups_by_category = {}
    
    for alert in alert_definitions:
        alert_category = alert['category']
        organization = alert['organization']
        alert_name = alert['name']
        
        # Create unique alert name per organization: {alert_name}_{organization}
        unique_alert_name = f"{alert_name}_{organization}"
        
        # Build alert rule
        alert_rule = {
            'alert': unique_alert_name,
            'expr': alert['promql_expr'],
            'for': alert['for_duration'],
            'labels': {
                'organization': organization,
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
            annotations['summary'] = f"{alert_name} for {organization}"
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

# Default email templates (must match API Gateway defaults)
DEFAULT_EMAIL_SUBJECT_TEMPLATE = "[{{ if eq .GroupLabels.severity \"critical\" }}CRITICAL{{ else if eq .GroupLabels.severity \"warning\" }}WARNING{{ else }}INFO{{ end }}] {{ .GroupLabels.alertname }} - {{ .GroupLabels.organization }}"
DEFAULT_EMAIL_BODY_TEMPLATE = """<h2 style="color: {{ if eq .GroupLabels.severity \"critical\" }}#d32f2f{{ else if eq .GroupLabels.severity \"warning\" }}#f57c00{{ else }}#1976d2{{ end }};">
  {{ if eq .GroupLabels.severity "critical" }}🚨 CRITICAL{{ else if eq .GroupLabels.severity "warning" }}⚠️ WARNING{{ else }}ℹ️ INFO{{ end }}: {{ .GroupLabels.category | title }} Alert
</h2>
<p><strong>Alert:</strong> {{ .GroupLabels.alertname }}</p>
<p><strong>Organization:</strong> {{ .GroupLabels.organization }}</p>
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
    routing_rules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate Alertmanager configuration from receivers and routing rules.
    Preserves global SMTP config from existing file, everything else comes from database.
    """
    # Load global config from existing file (preserves SMTP settings)
    global_config = load_global_config_from_file()
    
    # Build receivers from database
    receivers_config = []
    receivers_by_organization = {}
    
    for receiver in receivers:
        organization = receiver['organization']
        receiver_name = receiver['receiver_name']
        
        receiver_config = {
            'name': f"{organization}-{receiver_name}"
        }
        
        # Build email configuration
        email_configs = []
        if receiver.get('email_to'):
            # Extract first email from list (database stores as array)
            email_to = receiver['email_to']
            if isinstance(email_to, list):
                # Take first email from list
                email_to = email_to[0] if email_to else None
            elif isinstance(email_to, str):
                # Already a string, use as-is
                pass
            else:
                # Convert to list and take first
                email_list = list(email_to) if email_to else []
                email_to = email_list[0] if email_list else None
            
            if email_to:
                # Alertmanager expects 'to' as a single string
                # Format: to: 'email@example.com'
                email_config = {
                    'to': str(email_to).strip(),  # Single string, not a list
                    'send_resolved': True
                }
                # Use default templates if not provided
                email_subject_template = receiver.get('email_subject_template') or DEFAULT_EMAIL_SUBJECT_TEMPLATE
                email_body_template = receiver.get('email_body_template') or DEFAULT_EMAIL_BODY_TEMPLATE
                
                email_config['headers'] = {
                    'Subject': email_subject_template
                }
                # Store HTML template - will be formatted as YAML literal block in post-processing
                email_config['html'] = email_body_template
                email_configs.append(email_config)
        
        receiver_config['email_configs'] = email_configs
        receivers_config.append(receiver_config)
        
        # Track receivers by customer
        if organization not in receivers_by_organization:
            receivers_by_organization[organization] = []
        receivers_by_organization[organization].append(f"{organization}-{receiver_name}")
    
    # Build routing tree from database
    # Structure: Each customer gets their own routes based on routing rules
    # Hybrid mode: Use explicit routing rules where they exist, auto-generate for organizations without rules
    root_routes = []
    
    # Group routing rules by organization
    rules_by_organization = {}
    if routing_rules:
        for rule in routing_rules:
            organization = rule['organization']
            if organization not in rules_by_organization:
                rules_by_organization[organization] = []
            rules_by_organization[organization].append(rule)
    
    # Group receivers by organization
    receivers_by_organization = {}
    for receiver in receivers:
        organization = receiver['organization']
        if organization not in receivers_by_organization:
            receivers_by_organization[organization] = []
        receivers_by_organization[organization].append(receiver)
    
    # Process each organization
    # Hybrid mode: Use explicit rules where they exist, auto-generate for routes without explicit rules
    for organization, org_receivers in receivers_by_organization.items():
        # Build a set of explicit route matches for this organization
        # Key format: (severity, category, alert_type) - None values mean "any"
        explicit_route_keys = set()
        explicit_rules_map = {}  # Maps (severity, category, alert_type) -> rule
        
        if organization in rules_by_organization:
            org_rules = rules_by_organization[organization]
            # Sort by priority (lower = higher priority)
            org_rules.sort(key=lambda r: r.get('priority', 100))
            
            for rule in org_rules:
                # Build match key for this rule
                severity = rule.get('match_severity')
                category = rule.get('match_category')
                alert_type = rule.get('match_alert_type')
                route_key = (severity, category, alert_type)
                
                explicit_route_keys.add(route_key)
                explicit_rules_map[route_key] = rule
        
        # Process receivers: use explicit rules if available, otherwise auto-generate
        for receiver in org_receivers:
            receiver_name = receiver['receiver_name']
            full_receiver_name = f"{organization}-{receiver_name}"
            
            # Parse receiver name to extract severity and category
            # Format: {severity}-{category} (e.g., "critical-application")
            parts = receiver_name.split('-', 1)
            if len(parts) != 2:
                logger.warning(f"Receiver name '{receiver_name}' doesn't follow pattern 'severity-category', skipping route generation for organization '{organization}'")
                continue
            
            severity, category = parts
            route_key = (severity, category, None)  # alert_type is None for auto-generated routes
            
            # Check if there's an explicit rule for this route
            # Try exact match first, then try with None alert_type
            explicit_rule = None
            if route_key in explicit_rules_map:
                explicit_rule = explicit_rules_map[route_key]
            else:
                # Try to find a rule that matches severity and category (alert_type can be None or match)
                for key, rule in explicit_rules_map.items():
                    rule_severity, rule_category, rule_alert_type = key
                    if rule_severity == severity and rule_category == category:
                        # Found a matching rule (alert_type might be None or specific)
                        explicit_rule = rule
                        route_key = key  # Use the actual key from the rule
                        break
            
            if explicit_rule:
                # Use explicit rule from database
                receiver_id = explicit_rule['receiver_id']
                # Verify receiver matches (should match, but double-check)
                if receiver['id'] != receiver_id:
                    logger.warning(f"Explicit rule for {organization}/{severity}/{category} references receiver {receiver_id}, but receiver '{receiver_name}' has ID {receiver['id']}. Using explicit rule's receiver.")
                    # Find the correct receiver
                    for r in receivers:
                        if r['id'] == receiver_id:
                            full_receiver_name = f"{organization}-{r['receiver_name']}"
                            break
                
                # Build match conditions - organization is always included
                match_conditions = {'organization': organization}
                if explicit_rule.get('match_severity'):
                    match_conditions['severity'] = explicit_rule['match_severity']
                if explicit_rule.get('match_category'):
                    match_conditions['category'] = explicit_rule['match_category']
                if explicit_rule.get('match_alert_type'):
                    match_conditions['alert_type'] = explicit_rule['match_alert_type']
                
                # Create route with match first, then receiver (correct order for Alertmanager)
                route = {
                    'match': match_conditions,
                    'receiver': full_receiver_name,
                    'group_wait': explicit_rule.get('group_wait', '10s'),
                    'group_interval': explicit_rule.get('group_interval', '10s'),
                    'repeat_interval': explicit_rule.get('repeat_interval', '12h'),
                    'continue': explicit_rule.get('continue_routing', False)
                }
                
                # Add group_by if specified
                if explicit_rule.get('group_by'):
                    route['group_by'] = explicit_rule['group_by']
                
                root_routes.append(route)
                logger.debug(f"Using explicit routing rule for {organization}/{severity}/{category}")
            else:
                # No explicit rule - auto-generate route from receiver name
                route = {
                    'match': {
                        'organization': organization,
                        'severity': severity,
                        'category': category
                    },
                    'receiver': full_receiver_name,
                    'group_wait': '10s',
                    'group_interval': '10s',
                    'repeat_interval': '12h',
                    'continue': False
                }
                root_routes.append(route)
                logger.debug(f"Auto-generated routing rule for {organization}/{severity}/{category}")
    
    # Build complete Alertmanager configuration
    # Only global config is preserved from file, everything else from database
    route_config = {
        'group_by': ['alertname', 'category', 'severity', 'organization'],
        'group_wait': '10s',
        'group_interval': '10s',
        'repeat_interval': '12h'
    }
    
    # Alertmanager requires a default receiver at root level
    # Use the first available receiver as default, or create a fallback
    default_receiver = None
    if receivers:
        # Use the first enabled receiver as default
        first_receiver = receivers[0]
        default_receiver = f"{first_receiver['organization']}-{first_receiver['receiver_name']}"
        logger.info(f"Using '{default_receiver}' as default receiver")
    else:
        # Create a fallback default receiver if no receivers exist
        logger.warning("No receivers found, creating fallback default receiver")
        default_receiver = 'default-receiver'
        # Add a default receiver to receivers_config
        receivers_config.append({
            'name': 'default-receiver',
            'email_configs': [{
                'to': 'bharathia6@gmail.com',  # Fallback email
                'send_resolved': True,
                'headers': {'Subject': '[ALERT] Default Receiver - {{ .GroupLabels.alertname }}'},
                'html': '<html><body><h2>Alert: {{ .GroupLabels.alertname }}</h2><p>This is a fallback receiver.</p></body></html>'
            }]
        })
    
    route_config['receiver'] = default_receiver
    
    # Routes must exist - no generic receiver at root level
    # If no routing rules exist, we cannot create a valid config
    if not root_routes:
        logger.warning("No routing rules configured in database. All alerts will go to default receiver.")
        # Create empty routes list - alerts will go to default receiver
        route_config['routes'] = []
    else:
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
            'equal': ['alertname', 'organization', 'category']
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
            
            # Generate YAML configurations - separate files for application and infrastructure
            application_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='application')
            infrastructure_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='infrastructure')
            alertmanager_config = generate_alertmanager_yaml(receivers, routing_rules)
            
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
        # Close pool if still open
        if db_pool:
            asyncio.run(close_db_pool())

