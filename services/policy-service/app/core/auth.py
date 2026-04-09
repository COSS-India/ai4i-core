from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

try:
    # Preferred layout (when ai4icore_auth is installed as a package)
    from ai4icore_auth.providers import create_auth_providers  # type: ignore
    from ai4icore_auth.jwt_verifier import AuthClaims  # type: ignore
except ModuleNotFoundError:
    # Dev/docker-compose-local layout: /app/libs/ai4icore_auth is on PYTHONPATH,
    # so the actual package lives at ai4icore_auth/ai4icore_auth/.
    from ai4icore_auth.ai4icore_auth.providers import create_auth_providers  # type: ignore
    from ai4icore_auth.ai4icore_auth.jwt_verifier import AuthClaims  # type: ignore


AuthProvider, OptionalAuthProvider = create_auth_providers()


async def require_adopter_admin(
    request: Request,
    claims: AuthClaims = Depends(AuthProvider),
) -> AuthClaims:
    """
    Enforce Adopter Admin access (platform admin).

    Convention in this repo:
    - "ADMIN" is platform-wide admin (adopter admin)
    - "TENANT ADMIN" is tenant-scoped and must be blocked for these APIs
    """
    roles = [str(r).upper() for r in (claims.roles or [])]
    if "ADMIN" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Adopter admin privileges required",
                }
            },
        )
    # Make claims accessible to downstream code if needed
    request.state.jwt_claims = claims
    request.state.is_platform_admin = True
    return claims

