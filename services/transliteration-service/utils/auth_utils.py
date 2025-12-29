"""
Authentication Utilities
Helper functions for extracting and forwarding authentication headers
"""

from typing import Dict, Optional
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


def extract_auth_headers(request: Request) -> Dict[str, str]:
    """
    Extract authentication headers from FastAPI request
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Dictionary of authentication headers to forward
    """
    auth_headers = {}
    
    # Extract Authorization header (Bearer token)
    authorization = request.headers.get("Authorization") or request.headers.get("authorization")
    if authorization:
        auth_headers["Authorization"] = authorization
        logger.debug("Extracted Authorization header")
    
    # Extract X-API-Key header
    api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if api_key:
        auth_headers["X-API-Key"] = api_key
        logger.debug("Extracted X-API-Key header")
    
    # Extract X-Auth-Source header (if present)
    auth_source = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
    if auth_source:
        auth_headers["X-Auth-Source"] = auth_source
        logger.debug(f"Extracted X-Auth-Source header: {auth_source}")
    
    # Log if no auth headers found
    if not auth_headers:
        logger.warning("No authentication headers found in request")
    
    return auth_headers

