"""
Router for routing rules endpoints
"""
from fastapi import APIRouter, Request, Query, Body, Depends
from typing import Optional, List, Dict, Any

from alert_management import (
    RoutingRuleCreate, RoutingRuleUpdate, RoutingRuleResponse, RoutingRuleTimingUpdate,
    extract_organization, validate_organization, get_organization_for_audit_from_request,
    create_routing_rule, get_routing_rule_by_id, list_routing_rules,
    update_routing_rule, delete_routing_rule, update_routing_rule_timing
)
from utils.auth_deps import (
    require_alerts_create,
    require_alerts_read,
    require_alerts_update,
    require_alerts_delete,
)

router = APIRouter(
    prefix="/alerts/routing-rules",
    tags=["Alerts"]
)


def get_username_from_request(request: Request) -> str:
    """Extract username from request headers or state"""
    username = getattr(request.state, "username", None)
    if username:
        return username
    username = request.headers.get("X-Username")
    if username:
        return username
    return "system"


def is_admin_user(request: Request) -> bool:
    """Check if user is admin from request.state (set by auth) or headers (when behind gateway)."""
    if getattr(request.state, "is_admin", None) is True:
        return True
    if request.headers.get("X-Admin", "").lower() == "true":
        return True
    roles = request.headers.get("X-User-Roles", "")
    if "ADMIN" in roles.upper():
        return True
    permissions = request.headers.get("X-User-Permissions", "")
    if "alerts.admin" in permissions:
        return True
    return False


@router.post("", response_model=RoutingRuleResponse, status_code=201)
async def create_routing_rule_endpoint(
    payload: RoutingRuleCreate,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_create),
):
    """
    Create a new routing rule
    
    - Regular users: organization is automatically extracted from API key or X-Organization header
    - Admin users: Can specify organization as query parameter to create rules for any organization
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        validate_organization(organization)
        target_organization = organization
    else:
        target_organization = extract_organization(request)
    organization_for_audit = get_organization_for_audit_from_request(request, organization if is_admin else None)
    username = get_username_from_request(request)
    return await create_routing_rule(target_organization, payload, username, request, organization_for_audit=organization_for_audit)


@router.get("", response_model=List[RoutingRuleResponse])
async def list_routing_rules_endpoint(
    request: Request,
    enabled_only: bool = Query(False, description="Only return enabled rules"),
    _: None = Depends(require_alerts_read),
):
    """
    List routing rules
    
    - Regular users: See only rules for their organization
    - Admin users: See all rules across all organizations
    """
    is_admin = is_admin_user(request)
    
    # If admin, return all rules (organization=None)
    if is_admin:
        organization = None
    else:
        organization = extract_organization(request)
    
    return await list_routing_rules(organization, enabled_only)


@router.get("/{rule_id}", response_model=RoutingRuleResponse)
async def get_routing_rule_endpoint(
    rule_id: int,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_read),
):
    """
    Get a specific routing rule by ID
    
    - Regular users: Can only get rules for their organization
    - Admin users: Can get rules for any organization by specifying organization, or omit to get any rule
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin:
        if organization:
            validate_organization(organization)
            return await get_routing_rule_by_id(rule_id, organization)
        else:
            return await get_routing_rule_by_id(rule_id, None)
    else:
        target_organization = extract_organization(request)
        return await get_routing_rule_by_id(rule_id, target_organization)


@router.put("/{rule_id}", response_model=RoutingRuleResponse)
async def update_routing_rule_endpoint(
    rule_id: int,
    payload: RoutingRuleUpdate,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_update),
):
    """
    Update a routing rule
    
    - Regular users: Can only update rules for their organization
    - Admin users: Can update rules for any organization by specifying organization
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        validate_organization(organization)
        target_organization = organization
    elif is_admin:
        target_organization = None
    else:
        target_organization = extract_organization(request)
    
    username = get_username_from_request(request)
    return await update_routing_rule(rule_id, target_organization, payload, username, request)


@router.delete("/{rule_id}")
async def delete_routing_rule_endpoint(
    rule_id: int,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_delete),
):
    """
    Delete a routing rule
    
    - Regular users: Can only delete rules for their organization
    - Admin users: Can delete rules for any organization by specifying organization
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        validate_organization(organization)
        target_organization = organization
    elif is_admin:
        target_organization = None
    else:
        target_organization = extract_organization(request)
    
    username = get_username_from_request(request)
    await delete_routing_rule(rule_id, target_organization, username, request)
    return {"message": "Routing rule deleted successfully"}


@router.patch("/timing")
async def update_routing_rule_timing_endpoint(
    payload: RoutingRuleTimingUpdate,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_update),
):
    """
    Update timing parameters (group_wait, group_interval, repeat_interval) for routing rules
    matching the specified criteria.
    
    This endpoint updates all routing rules that match:
    - organization (if specified, or all for admin)
    - category
    - severity
    - alert_type (if specified)
    - priority (if specified)
    
    - Regular users: Can only update rules for their organization
    - Admin users: Can update rules for any organization by specifying organization, or all organizations if not specified
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        validate_organization(organization)
        target_organization = organization
    elif is_admin:
        target_organization = None  # Admin can update across all organizations
    else:
        target_organization = extract_organization(request)
    
    username = get_username_from_request(request)
    return await update_routing_rule_timing(target_organization, payload, username, request)

