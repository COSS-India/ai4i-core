"""
JWKS (JSON Web Key Set) endpoint handler.

Exposes the RS256 public key so that API gateways and downstream services
can verify JWTs without sharing a symmetric secret.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from auth_utils import get_jwks

router = APIRouter()


@router.get("/.well-known/jwks.json", tags=["auth"])
async def jwks_endpoint():
    """Return the public signing key in JWKS format (RFC 7517)."""
    return JSONResponse(
        content=get_jwks(),
        headers={"Cache-Control": "public, max-age=3600"},
    )
