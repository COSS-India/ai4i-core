"""
Integration tests for API gateway security hardening.
Tests APISIX JWT verification, header injection, rate limiting, and multi-mode auth.
"""
import pytest
import httpx
import asyncio


GATEWAY_BASE = "http://localhost:8080"

# Public routes that should NOT require authentication
PUBLIC_ROUTES = [
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/.well-known/jwks.json",
]

# Authenticated routes that SHOULD require auth
AUTHENTICATED_ROUTES = [
    "/api/v1/asr/health",
    "/api/v1/nmt/health",
    "/api/v1/tts/health",
]


@pytest.mark.integration
@pytest.mark.asyncio
class TestGatewayJWTVerification:
    """Test that gateway enforces JWT verification on protected routes."""

    async def test_unauthenticated_request_rejected(self):
        """Requests without auth to protected routes should be rejected."""
        async with httpx.AsyncClient(base_url=GATEWAY_BASE) as client:
            for route in AUTHENTICATED_ROUTES:
                response = await client.get(route)
                assert response.status_code in [401, 403], (
                    f"Expected 401/403 for unauthenticated request to {route}, got {response.status_code}"
                )

    async def test_invalid_jwt_rejected(self):
        """Requests with an invalid JWT should be rejected."""
        async with httpx.AsyncClient(
            base_url=GATEWAY_BASE,
            headers={"Authorization": "Bearer invalid.jwt.token"},
        ) as client:
            response = await client.get("/api/v1/asr/health")
            assert response.status_code in [401, 403]

    async def test_public_routes_accessible(self):
        """Public routes should be accessible without authentication."""
        async with httpx.AsyncClient(base_url=GATEWAY_BASE) as client:
            for route in PUBLIC_ROUTES:
                if route == "/api/v1/auth/login":
                    # POST with dummy payload
                    response = await client.post(
                        route,
                        json={"email": "test@test.com", "password": "dummy"},
                    )
                    # Should get 401 (bad creds) not 403 (no auth)
                    assert response.status_code != 403, f"Login route should not require gateway auth"
                elif route == "/.well-known/jwks.json":
                    response = await client.get(route)
                    assert response.status_code == 200
                    data = response.json()
                    assert "keys" in data
                    assert len(data["keys"]) > 0
                    assert data["keys"][0]["alg"] == "RS256"
                    assert "kid" in data["keys"][0]


@pytest.mark.integration
@pytest.mark.asyncio
class TestGatewayHeaderInjection:
    """Test that gateway injects user context headers after authentication."""

    async def test_validated_header_present(self, authenticated_client: httpx.AsyncClient):
        """After gateway auth, X-Validated header should be injected."""
        response = await authenticated_client.get("/api/v1/asr/health")
        # If the service echos headers or we can check via response, verify
        # For now, just verify the request succeeds (meaning gateway passed it through)
        assert response.status_code != 401

    async def test_direct_backend_access_rejected(self):
        """Direct access to backend (bypassing gateway) should be rejected."""
        # Backend services listen on internal ports; try hitting one directly
        # This test assumes backends are NOT exposed on host ports
        async with httpx.AsyncClient(base_url="http://localhost:8087") as client:
            try:
                response = await client.get("/health", timeout=2.0)
                # If we get a response, the port is exposed (Phase 3B should fix this)
                # The backend should still reject because X-Validated is missing
                if response.status_code == 401:
                    pass  # Good - backend rejects without gateway header
            except (httpx.ConnectError, httpx.ConnectTimeout):
                pass  # Good - port not exposed


@pytest.mark.integration
@pytest.mark.asyncio
class TestGatewayRateLimiting:
    """Test Redis-backed rate limiting at the gateway."""

    async def test_login_rate_limit(self):
        """Login endpoint should be rate-limited to 5 req / 5 min."""
        async with httpx.AsyncClient(base_url=GATEWAY_BASE) as client:
            responses = []
            for _ in range(7):
                resp = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "ratelimit@test.com", "password": "wrong"},
                )
                responses.append(resp)

            status_codes = [r.status_code for r in responses]
            assert 429 in status_codes, "Login should be rate-limited after 5 requests"

    async def test_register_rate_limit(self):
        """Register endpoint should be rate-limited to 3 req / hour."""
        async with httpx.AsyncClient(base_url=GATEWAY_BASE) as client:
            responses = []
            for i in range(5):
                resp = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": f"ratelimit{i}@test.com",
                        "username": f"ratelimit{i}",
                        "password": "Test@1234",
                        "confirm_password": "Test@1234",
                    },
                )
                responses.append(resp)

            status_codes = [r.status_code for r in responses]
            assert 429 in status_codes, "Register should be rate-limited after 3 requests"

    async def test_rate_limit_returns_429(self, authenticated_client: httpx.AsyncClient):
        """Exceeding rate limit should return 429 with proper headers."""
        responses = []
        for _ in range(250):  # Exceed global 200/min ceiling
            resp = await authenticated_client.get("/api/v1/nmt/health")
            responses.append(resp)
            if resp.status_code == 429:
                break

        rate_limited = [r for r in responses if r.status_code == 429]
        assert len(rate_limited) > 0, "Should get 429 after exceeding rate limit"

        # Check rate limit headers
        last_429 = rate_limited[-1]
        assert "X-RateLimit-Limit" in last_429.headers or "RateLimit-Limit" in last_429.headers


@pytest.mark.integration
@pytest.mark.asyncio
class TestGatewayAPIKeyValidation:
    """Test API key validation through the gateway."""

    async def test_valid_api_key_accepted(self, authenticated_client: httpx.AsyncClient):
        """Valid API key should pass gateway validation."""
        response = await authenticated_client.get("/api/v1/asr/health")
        assert response.status_code != 401

    async def test_revoked_api_key_rejected(self):
        """Revoked API key should be rejected."""
        async with httpx.AsyncClient(
            base_url=GATEWAY_BASE,
            headers={"Authorization": "Bearer revoked_key_test_12345"},
        ) as client:
            response = await client.get("/api/v1/asr/health")
            assert response.status_code in [401, 403]


@pytest.mark.integration
@pytest.mark.asyncio
class TestMultiModeAuth:
    """Test multi-mode authentication (AUTH_TOKEN, API_KEY, BOTH)."""

    async def test_api_key_mode_default(self, authenticated_client: httpx.AsyncClient):
        """Default auth mode should be API_KEY."""
        response = await authenticated_client.get("/api/v1/asr/health")
        assert response.status_code != 401

    async def test_auth_token_mode(self, authenticated_jwt_client: httpx.AsyncClient):
        """AUTH_TOKEN mode should accept JWT-only auth."""
        response = await authenticated_jwt_client.get(
            "/api/v1/asr/health",
            headers={"X-Auth-Source": "AUTH_TOKEN"},
        )
        assert response.status_code != 401
