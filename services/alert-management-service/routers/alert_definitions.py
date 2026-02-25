"""
Router for alert definitions endpoints
"""
from fastapi import APIRouter, Request, Query, Body, Depends
from typing import Optional, List
from pydantic import BaseModel

from alert_management import (
    AlertDefinitionCreate, AlertDefinitionUpdate, AlertDefinitionResponse,
    extract_organization, validate_organization, get_organization_for_audit_from_request,
    create_alert_definition, get_alert_definition_by_id, list_alert_definitions,
    update_alert_definition, delete_alert_definition, toggle_alert_definition
)
from utils.auth_deps import (
    require_alerts_create,
    require_alerts_read,
    require_alerts_update,
    require_alerts_delete,
)

router = APIRouter(
    prefix="/alerts/definitions",
    tags=["Alerts"]
)


def get_username_from_request(request: Request) -> str:
    """Extract username from request headers or state"""
    # Try to get from request state (set by gateway middleware)
    username = getattr(request.state, "username", None)
    if username:
        return username
    
    # Try to get from X-Username header
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


@router.post("", response_model=AlertDefinitionResponse, status_code=201)
async def create_alert_definition_endpoint(
    request: Request,
    payload: AlertDefinitionCreate = Body(..., embed=True),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_create),
):
    """
    Create a new alert definition
    
    - Regular users: organization is automatically extracted from API key or X-Organization header
    - Admin users: Can specify organization as query parameter to create alerts for any organization
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        # Admin explicitly specified organization - use it
        validate_organization(organization)
        target_organization = organization
    else:
        # Regular user or admin didn't specify - extract from request
        target_organization = extract_organization(request)
    organization_for_audit = get_organization_for_audit_from_request(request, organization if is_admin else None)
    username = get_username_from_request(request)
    return await create_alert_definition(target_organization, payload, username, request, organization_for_audit=organization_for_audit)


@router.get("", response_model=List[AlertDefinitionResponse])
async def list_alert_definitions_endpoint(
    request: Request,
    enabled_only: bool = Query(False, description="Only return enabled alerts"),
    _: None = Depends(require_alerts_read),
):
    """
    List alert definitions.
    
    - Regular users: See only alerts for their organization (determined by API key or X-Organization header)
    - Admin users: See all alerts across all organizations
    """
    is_admin = is_admin_user(request)
    
    # If admin, return all alerts (organization=None)
    # Otherwise, return only alerts for the user's organization
    if is_admin:
        organization = None  # None means return all alerts
    else:
        organization = extract_organization(request)
    
    return await list_alert_definitions(organization, enabled_only)


@router.get("/{alert_id}", response_model=AlertDefinitionResponse)
async def get_alert_definition_endpoint(
    alert_id: int,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_read),
):
    """
    Get a specific alert definition by ID
    
    - Regular users: Can only get alerts for their organization
    - Admin users: Can get alerts for any organization by specifying organization, or omit to get any alert
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin:
        # Admin can access any alert - pass None to skip organization check
        if organization:
            validate_organization(organization)
            return await get_alert_definition_by_id(alert_id, organization)
        else:
            # Admin didn't specify organization - allow access to any alert
            return await get_alert_definition_by_id(alert_id, None)
    else:
        # Regular user - only their organization
        target_organization = extract_organization(request)
        return await get_alert_definition_by_id(alert_id, target_organization)


@router.put("/{alert_id}", response_model=AlertDefinitionResponse)
async def update_alert_definition_endpoint(
    alert_id: int,
    payload: AlertDefinitionUpdate,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_update),
):
    """
    Update an alert definition
    
    - Regular users: Can only update alerts for their organization
    - Admin users: Can update alerts for any organization by specifying organization
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        # Admin explicitly specified organization - use it
        validate_organization(organization)
        target_organization = organization
    elif is_admin:
        # Admin didn't specify - allow update of any alert (will be checked in update function)
        target_organization = None
    else:
        # Regular user - only their organization
        target_organization = extract_organization(request)
    
    username = get_username_from_request(request)
    return await update_alert_definition(alert_id, target_organization, payload, username, request)


@router.delete("/{alert_id}")
async def delete_alert_definition_endpoint(
    alert_id: int,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_delete),
):
    """
    Delete an alert definition
    
    - Regular users: Can only delete alerts for their organization
    - Admin users: Can delete alerts for any organization by specifying organization
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin and organization:
        # Admin explicitly specified organization - use it
        validate_organization(organization)
        target_organization = organization
    elif is_admin:
        # Admin didn't specify - allow delete of any alert
        target_organization = None
    else:
        # Regular user - only their organization
        target_organization = extract_organization(request)
    
    username = get_username_from_request(request)
    await delete_alert_definition(alert_id, target_organization, username, request)
    return {"message": "Alert definition deleted successfully"}


@router.patch("/{alert_id}/enabled", response_model=AlertDefinitionResponse)
async def toggle_alert_definition_endpoint(
    alert_id: int,
    request: Request,
    enabled: bool = Body(..., embed=True, description="Enable or disable the alert"),
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_update),
):
    """
    Enable or disable an alert definition
    
    - Regular users: Can only toggle alerts for their organization (determined by API key or X-Organization header)
    - Admin users: Can toggle alerts for any organization by specifying organization, or omit to toggle any alert
    """
    is_admin = is_admin_user(request)
    
    # Determine target organization
    if is_admin:
        if organization:
            # Admin explicitly specified organization - use it
            validate_organization(organization)
            target_organization = organization
        else:
            # Admin didn't specify - allow toggling any alert (pass None)
            target_organization = None
    else:
        # Regular user - extract from request
        target_organization = extract_organization(request)
    
    username = get_username_from_request(request)
    return await toggle_alert_definition(alert_id, target_organization, enabled, username, request)

