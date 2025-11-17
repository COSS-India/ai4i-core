"""
OAuth 2.0 utilities for Google and other providers
"""
import os
import secrets
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class OAuthUtils:
    """OAuth 2.0 utility functions"""
    
    @staticmethod
    async def generate_state_token(redis_client: redis.Redis) -> str:
        """Generate and store state token for CSRF protection"""
        state = secrets.token_urlsafe(32)
        # Store state with 10 minute TTL
        await redis_client.setex(f"oauth_state:{state}", 600, "1")
        logger.info(f"Generated OAuth state token: {state[:16]}...")
        return state
    
    @staticmethod
    async def validate_state_token(redis_client: redis.Redis, state: str) -> bool:
        """Validate state token from Redis (one-time use)"""
        if not state:
            return False
        
        key = f"oauth_state:{state}"
        exists = await redis_client.exists(key)
        
        if exists:
            # Delete after validation (one-time use)
            await redis_client.delete(key)
            logger.info(f"Validated and consumed OAuth state token: {state[:16]}...")
            return True
        
        logger.warning(f"Invalid or expired OAuth state token: {state[:16]}...")
        return False
    
    @staticmethod
    def get_google_authorization_url(state: str, redirect_uri: str) -> str:
        """Generate Google OAuth authorization URL"""
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        if not client_id:
            raise ValueError("GOOGLE_CLIENT_ID environment variable not set")
        
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent"  # Force consent screen to get refresh token
        }
        
        auth_url = f"{base_url}?{urlencode(params)}"
        logger.info(f"Generated Google authorization URL")
        return auth_url
    
    @staticmethod
    async def exchange_google_code_for_tokens(code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange Google authorization code for access token"""
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            raise ValueError("Google OAuth credentials not configured")
        
        client = AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret
        )
        
        token_url = "https://oauth2.googleapis.com/token"
        
        try:
            token = await client.fetch_token(
                token_url,
                code=code,
                redirect_uri=redirect_uri
            )
            logger.info("Successfully exchanged Google authorization code for tokens")
            return token
        except Exception as e:
            logger.error(f"Error exchanging Google code for tokens: {str(e)}")
            raise
    
    @staticmethod
    async def get_google_user_info(access_token: str) -> Dict[str, Any]:
        """Fetch user info from Google using access token"""
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0
                )
                response.raise_for_status()
                user_info = response.json()
                logger.info(f"Fetched Google user info for: {user_info.get('email')}")
                return user_info
        except httpx.HTTPError as e:
            logger.error(f"Error fetching Google user info: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching Google user info: {str(e)}")
            raise
    
    @staticmethod
    async def refresh_google_token(refresh_token: str) -> Dict[str, Any]:
        """Refresh Google access token using refresh token"""
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            raise ValueError("Google OAuth credentials not configured")
        
        client = AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret
        )
        
        token_url = "https://oauth2.googleapis.com/token"
        
        try:
            token = await client.refresh_token(
                token_url,
                refresh_token=refresh_token
            )
            logger.info("Successfully refreshed Google access token")
            return token
        except Exception as e:
            logger.error(f"Error refreshing Google token: {str(e)}")
            raise

