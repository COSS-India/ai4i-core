"""
Authentication middleware for API Gateway
Authentication is delegated to auth-service for centralized validation
"""
import os
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")

security = HTTPBearer(auto_error=False)

class AuthMiddleware:
    """Authentication middleware for API Gateway"""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token with auth service (authentication happens at auth-service level)"""
        try:
            # Always validate token through auth-service for centralized authentication
            # This ensures user status, permissions, and token validity are checked in one place
            response = await self.http_client.post(
                f"{AUTH_SERVICE_URL}/api/v1/auth/validate",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                data = response.json()
                # Return token payload format expected by API Gateway
                return {
                    "sub": str(data.get("user_id")),
                    "username": data.get("username"),
                    "permissions": data.get("permissions", []),
                    "roles": data.get("roles", [])
                }
            else:
                logger.warning(f"Auth service validation failed with status {response.status_code}")
                return None
        except httpx.RequestError as e:
            logger.error(f"Auth service request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Auth service validation failed: {e}")
            return None
    
    async def get_current_user(self, credentials: Optional[HTTPAuthorizationCredentials] = None) -> Optional[Dict[str, Any]]:
        """Get current user from token"""
        if not credentials:
            return None
        
        token = credentials.credentials
        payload = await self.verify_token(token)
        
        if payload is None:
            return None
        
        return {
            "user_id": payload.get("sub"),
            "username": payload.get("username"),
            "permissions": payload.get("permissions", [])
        }
    
    async def require_auth(self, request: Request) -> Dict[str, Any]:
        """Require authentication for protected routes"""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(" ")[1]
        user = await self.verify_token(token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
    
    async def require_permission(self, permission: str, request: Request) -> Dict[str, Any]:
        """Require specific permission for protected routes"""
        user = await self.require_auth(request)
        
        if permission not in user.get("permissions", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}"
            )
        
        return user
    
    async def optional_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """Optional authentication for public routes that can benefit from user context"""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        
        token = auth_header.split(" ")[1]
        return await self.verify_token(token)
    
    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()

# Global auth middleware instance
auth_middleware = AuthMiddleware()
