"""
Audit logging utility for alert management operations.

Logs all actions related to alert configuration, routing, delivery, and governance
to OpenSearch via structured JSON logging.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import Request

# Use ai4icore_logging (same as nmt-service, ocr-service)
from ai4icore_logging import get_logger
logger = get_logger(__name__)

# Import OpenTelemetry for trace_id extraction
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False


def get_username_from_request(request: Optional[Request] = None) -> str:
    """
    Extract username for audit logs.
    Source (in order): request.state.username, X-Username header, then "system".
    The actual username comes from the API gateway: it validates the JWT with the auth service,
    gets username from the /api/v1/auth/validate response, and forwards it in the X-Username
    header. If requests reach this service directly (not via the gateway), X-Username is never
    set and audit logs show "system". Ensure alert API calls go through the gateway so the
    JWT-derived username is present.
    """
    if request:
        # Try to get from request state (if set by any middleware)
        username = getattr(request.state, "username", None)
        if username:
            return username
        # API gateway forwards JWT-derived username in X-Username
        username = request.headers.get("X-Username")
        if username:
            return username
    return "system"


def get_user_roles_from_request(request: Optional[Request] = None) -> List[str]:
    """Extract user roles from request headers (forwarded by API gateway from JWT)."""
    if not request:
        return []
    # API gateway forwards JWT roles as comma-separated X-User-Roles
    roles_header = request.headers.get("X-User-Roles")
    if not roles_header:
        return []
    return [r.strip() for r in roles_header.split(",") if r.strip()]


def get_actor_from_request(request: Optional[Request] = None) -> str:
    """
    Build audit actor string: username and their role(s) from JWT (via X-Username, X-User-Roles).
    Returns e.g. "johndoe (ADMIN)" or "johndoe (USER, MODERATOR)" or "johndoe" if no roles.
    """
    username = get_username_from_request(request)
    roles = get_user_roles_from_request(request)
    if not roles:
        return username
    return f"{username} ({', '.join(roles)})"


def get_organization_from_request(request: Optional[Request] = None) -> Optional[str]:
    """
    Extract organization from request for audit only (header or state).
    Only uses X-Organization header or request.state.organization — never
    API-key-based mapping. Callers should pass the resource's organization
    (e.g. from DB for update/delete, or header/admin for create) when known.
    """
    if request:
        organization = getattr(request.state, "organization", None)
        if organization:
            return organization
        organization = request.headers.get("X-Organization") or request.headers.get("x-organization")
        if organization:
            return organization
    return None


def get_trace_id() -> Optional[str]:
    """Extract trace_id from OpenTelemetry context"""
    if not TRACING_AVAILABLE:
        return None
    
    try:
        current_span = trace.get_current_span()
        if current_span:
            span_context = current_span.get_span_context()
            if span_context.is_valid and span_context.trace_id != 0:
                return format(span_context.trace_id, '032x')
    except Exception:
        pass
    
    return None


def log_audit_event(
    operation: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    organization: Optional[str] = None,
    actor: Optional[str] = None,
    request: Optional[Request] = None,
    before_values: Optional[Dict[str, Any]] = None,
    after_values: Optional[Dict[str, Any]] = None,
    change_description: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
):
    """
    Log an audit event to OpenSearch via structured JSON logging.
    
    Args:
        operation: Operation type (CREATE, UPDATE, DELETE, ENABLE, DISABLE, SYNC)
        resource_type: Type of resource (alert_definition, notification_receiver, routing_rule, config_sync)
        resource_id: ID of the resource (if applicable)
        organization: Organization for which the action is performed (which org's resource is affected).
            Should be the resource's org from DB for update/delete, or from X-Organization/admin for create.
            Never use API-key-derived org. If not provided, falls back to X-Organization header only.
        actor: Username/identifier of the actor performing the action
        request: FastAPI Request object (used to extract additional context)
        before_values: State before the change (for UPDATE operations)
        after_values: State after the change (for CREATE/UPDATE operations)
        change_description: Human-readable description of the change
        additional_context: Any additional context to include in the audit log
    """
    # Extract actor (username + role(s) from JWT) from request if not provided
    if not actor and request:
        actor = get_actor_from_request(request)
    if not actor:
        actor = "system"

    # Extract username and roles for audit context (from JWT via gateway headers)
    username = get_username_from_request(request) if request else "system"
    user_roles = get_user_roles_from_request(request) if request else []

    # Extract organization from request if not provided
    if not organization and request:
        organization = get_organization_from_request(request)

    # Extract trace_id
    trace_id = get_trace_id()

    # Extract additional request context
    request_context = {}
    if request:
        request_context = {
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
        if user_roles:
            request_context["user_roles"] = ",".join(user_roles)
        permissions = request.headers.get("X-User-Permissions")
        if permissions:
            request_context["user_permissions"] = permissions
    
    # Build audit log entry (actor = username + role(s) from JWT)
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "alert-management-service",
        "level": "INFO",
        "logger": "audit",
        "message": f"Alert config audit: {operation} {resource_type}" + (f" (ID: {resource_id})" if resource_id else ""),
        "audit": {
            "operation": operation,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "organization": organization,
            "actor": actor,
            "actor_username": username,
            "actor_roles": user_roles,
            "change_description": change_description,
        }
    }
    
    # Add before/after values
    if before_values:
        audit_entry["audit"]["before"] = before_values
    if after_values:
        audit_entry["audit"]["after"] = after_values
    
    # Add trace_id if available
    if trace_id:
        audit_entry["trace_id"] = trace_id
        audit_entry["jaeger_trace_url"] = trace_id
    
    # Add request context
    if request_context:
        audit_entry["audit"]["request"] = request_context
    
    # Add additional context
    if additional_context:
        audit_entry["audit"]["context"] = additional_context
    
    # Log as JSON (structured logging), same pattern as nmt/ocr: message + extra with context and audit
    log_context = {
        "organization": organization,
        "actor": actor,
        "actor_username": username,
        "actor_roles": user_roles,
        "operation": operation,
        "resource_type": resource_type,
        "resource_id": resource_id,
    }
    if trace_id:
        log_context["trace_id"] = trace_id
    logger.info(
        audit_entry["message"],
        extra={
            "context": log_context,
            "audit": audit_entry["audit"],
            "trace_id": trace_id,
            "organization": organization,
            **request_context
        }
    )


# Convenience functions for specific operations

def log_alert_definition_create(
    alert_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    alert_data: Optional[Dict[str, Any]] = None
):
    """Log creation of an alert definition"""
    log_audit_event(
        operation="CREATE",
        resource_type="alert_definition",
        resource_id=alert_id,
        organization=organization,
        actor=actor,
        request=request,
        after_values=alert_data,
        change_description=f"Created alert definition '{alert_data.get('name', 'unknown')}' for organization '{organization}'"
    )


def log_alert_definition_update(
    alert_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    before_values: Optional[Dict[str, Any]] = None,
    after_values: Optional[Dict[str, Any]] = None
):
    """Log update of an alert definition"""
    log_audit_event(
        operation="UPDATE",
        resource_type="alert_definition",
        resource_id=alert_id,
        organization=organization,
        actor=actor,
        request=request,
        before_values=before_values,
        after_values=after_values,
        change_description=f"Updated alert definition ID {alert_id} for organization '{organization}'"
    )


def log_alert_definition_delete(
    alert_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    alert_data: Optional[Dict[str, Any]] = None
):
    """Log deletion of an alert definition"""
    log_audit_event(
        operation="DELETE",
        resource_type="alert_definition",
        resource_id=alert_id,
        organization=organization,
        actor=actor,
        request=request,
        before_values=alert_data,
        change_description=f"Deleted alert definition ID {alert_id} for organization '{organization}'"
    )


def log_alert_definition_toggle(
    alert_id: int,
    organization: str,
    enabled: bool,
    actor: str,
    request: Optional[Request] = None
):
    """Log enable/disable of an alert definition"""
    operation = "ENABLE" if enabled else "DISABLE"
    log_audit_event(
        operation=operation,
        resource_type="alert_definition",
        resource_id=alert_id,
        organization=organization,
        actor=actor,
        request=request,
        after_values={"enabled": enabled},
        change_description=f"{operation}d alert definition ID {alert_id} for organization '{organization}'"
    )


def log_receiver_create(
    receiver_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    receiver_data: Optional[Dict[str, Any]] = None
):
    """Log creation of a notification receiver"""
    log_audit_event(
        operation="CREATE",
        resource_type="notification_receiver",
        resource_id=receiver_id,
        organization=organization,
        actor=actor,
        request=request,
        after_values=receiver_data,
        change_description=f"Created notification receiver '{receiver_data.get('receiver_name', 'unknown')}' for organization '{organization}'"
    )


def log_receiver_update(
    receiver_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    before_values: Optional[Dict[str, Any]] = None,
    after_values: Optional[Dict[str, Any]] = None
):
    """Log update of a notification receiver"""
    log_audit_event(
        operation="UPDATE",
        resource_type="notification_receiver",
        resource_id=receiver_id,
        organization=organization,
        actor=actor,
        request=request,
        before_values=before_values,
        after_values=after_values,
        change_description=f"Updated notification receiver ID {receiver_id} for organization '{organization}'"
    )


def log_receiver_delete(
    receiver_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    receiver_data: Optional[Dict[str, Any]] = None
):
    """Log deletion of a notification receiver"""
    log_audit_event(
        operation="DELETE",
        resource_type="notification_receiver",
        resource_id=receiver_id,
        organization=organization,
        actor=actor,
        request=request,
        before_values=receiver_data,
        change_description=f"Deleted notification receiver ID {receiver_id} for organization '{organization}'"
    )


def log_routing_rule_create(
    rule_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    rule_data: Optional[Dict[str, Any]] = None
):
    """Log creation of a routing rule"""
    log_audit_event(
        operation="CREATE",
        resource_type="routing_rule",
        resource_id=rule_id,
        organization=organization,
        actor=actor,
        request=request,
        after_values=rule_data,
        change_description=f"Created routing rule '{rule_data.get('rule_name', 'unknown')}' for organization '{organization}'"
    )


def log_routing_rule_update(
    rule_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    before_values: Optional[Dict[str, Any]] = None,
    after_values: Optional[Dict[str, Any]] = None
):
    """Log update of a routing rule"""
    log_audit_event(
        operation="UPDATE",
        resource_type="routing_rule",
        resource_id=rule_id,
        organization=organization,
        actor=actor,
        request=request,
        before_values=before_values,
        after_values=after_values,
        change_description=f"Updated routing rule ID {rule_id} for organization '{organization}'"
    )


def log_routing_rule_delete(
    rule_id: int,
    organization: str,
    actor: str,
    request: Optional[Request] = None,
    rule_data: Optional[Dict[str, Any]] = None
):
    """Log deletion of a routing rule"""
    log_audit_event(
        operation="DELETE",
        resource_type="routing_rule",
        resource_id=rule_id,
        organization=organization,
        actor=actor,
        request=request,
        before_values=rule_data,
        change_description=f"Deleted routing rule ID {rule_id} for organization '{organization}'"
    )


def log_config_sync(
    organization: Optional[str] = None,
    actor: Optional[str] = None,
    sync_details: Optional[Dict[str, Any]] = None
):
    """Log configuration sync operation"""
    log_audit_event(
        operation="SYNC",
        resource_type="config_sync",
        organization=organization,
        actor=actor or "system",
        additional_context=sync_details,
        change_description="Synchronized alert configuration (Prometheus/Alertmanager)"
    )

