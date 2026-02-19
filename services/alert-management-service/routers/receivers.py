"""
Router for notification receivers endpoints
"""
from fastapi import APIRouter, Request, Query, Depends
from typing import Optional, List

from alert_management import (
    NotificationReceiverCreate, NotificationReceiverUpdate, NotificationReceiverResponse,
    extract_organization, validate_organization, get_organization_for_audit_from_request,
    create_notification_receiver, get_notification_receiver_by_id, list_notification_receivers,
    update_notification_receiver, delete_notification_receiver
)
from utils.auth_deps import (
    require_alerts_create,
    require_alerts_read,
    require_alerts_update,
    require_alerts_delete,
)

router = APIRouter(
    prefix="/alerts/receivers",
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


@router.post("", response_model=NotificationReceiverResponse, status_code=201)
async def create_notification_receiver_endpoint(
    payload: NotificationReceiverCreate,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_create),
):
    """
    Create a new notification receiver
    
    - Regular users: organization is automatically extracted from API key or X-Organization header
    - Admin users: Can specify organization as query parameter to create receivers for any organization
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
    return await create_notification_receiver(target_organization, payload, username, request, organization_for_audit=organization_for_audit)


@router.get("", response_model=List[NotificationReceiverResponse])
async def list_notification_receivers_endpoint(
    request: Request,
    enabled_only: bool = Query(False, description="Only return enabled receivers"),
    _: None = Depends(require_alerts_read),
):
    """
    List notification receivers
    
    - Regular users: See only receivers for their organization
    - Admin users: See all receivers across all organizations
    """
    is_admin = is_admin_user(request)
    
    # If admin, return all receivers (organization=None)
    if is_admin:
        organization = None
    else:
        organization = extract_organization(request)
    
    return await list_notification_receivers(organization, enabled_only)


@router.get("/{receiver_id}", response_model=NotificationReceiverResponse)
async def get_notification_receiver_endpoint(
    receiver_id: int,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_read),
):
    """
    Get a specific notification receiver by ID
    
    - Regular users: Can only get receivers for their organization
    - Admin users: Can get receivers for any organization by specifying organization, or omit to get any receiver
    """
    is_admin = is_admin_user(request)
    
    # Determine organization
    if is_admin:
        if organization:
            validate_organization(organization)
            return await get_notification_receiver_by_id(receiver_id, organization)
        else:
            return await get_notification_receiver_by_id(receiver_id, None)
    else:
        target_organization = extract_organization(request)
        return await get_notification_receiver_by_id(receiver_id, target_organization)


@router.put("/{receiver_id}", response_model=NotificationReceiverResponse)
async def update_notification_receiver_endpoint(
    receiver_id: int,
    payload: NotificationReceiverUpdate,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_update),
):
    """
    Update a notification receiver
    
    - Regular users: Can only update receivers for their organization
    - Admin users: Can update receivers for any organization by specifying organization
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
    return await update_notification_receiver(receiver_id, target_organization, payload, username, request)


@router.delete("/{receiver_id}")
async def delete_notification_receiver_endpoint(
    receiver_id: int,
    request: Request,
    organization: Optional[str] = Query(None, description="Organization (admin only - if not provided, uses organization from API key)"),
    _: None = Depends(require_alerts_delete),
):
    """
    Delete a notification receiver
    
    - Regular users: Can only delete receivers for their organization
    - Admin users: Can delete receivers for any organization by specifying organization
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
    await delete_notification_receiver(receiver_id, target_organization, username, request)
    return {"message": "Notification receiver deleted successfully"}

