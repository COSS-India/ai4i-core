"""
Centralized message constants for auth-service.

All user-facing messages and log messages are defined here with consistent keys.
This provides a single source of truth for message management and translations.
"""

# ── Token/JWT Errors ──
TOKEN_INVALID = "Token validation failed."
TOKEN_MISSING = "Token header missing 'kid'."
TOKEN_MISSING_SUB = "Token missing 'sub' claim."
TOKEN_HEADER_INVALID = "Invalid token header."
TOKEN_ALGORITHM_UNSUPPORTED = "Unsupported algorithm. Expected RS256."
TOKEN_NO_KEYS = "No verification keys available."
JWK_MISSING_FIELDS = "JWK missing required 'n' or 'e' field."

# ── OAuth Errors ──
OAUTH_PROVIDER_UNKNOWN = "OAuth provider is not configured."
OAUTH_PROVIDER_MISMATCH = "OAuth provider mismatch."
OAUTH_PROVIDER_UNREACHABLE = "OAuth provider unreachable."
OAUTH_STATE_INVALID = "Invalid or expired OAuth state."
OAUTH_REDIRECT_URI_INVALID = "Redirect URI is not allowed."
OAUTH_CODE_INVALID = "Invalid or expired exchange code."
OAUTH_CODE_EXCHANGE_FAILED = "Failed to exchange authorization code."
OAUTH_USERINFO_FETCH_FAILED = "Failed to fetch user info from provider."
OAUTH_EMAIL_UNVERIFIED = "OAuth email address is not verified."

# ── Logging: Info/Success ──
LOG_JWKS_REFRESHED = "JWKS refreshed: {key_count} public key(s) loaded from {url}"
LOG_OAUTH_LOGIN = "OAuth login: {email} via {provider} (user_id={user_id})"
LOG_OAUTH_USER_CREATED = "OAuth user created: {email} via {provider} (id={user_id})"
LOG_DEFAULT_ROLE_MISSING = "Default USER role not found, skipping role assignment."

# ── Logging: Warnings ──
LOG_WARN_JWT_NO_KEYS = "JWTVerifier: no JWKS URL configured and no keys loaded."
LOG_WARN_JWK_CONVERT_FAILED = "Failed to convert JWK kid={kid} to PEM"
LOG_WARN_OAUTH_REDIRECT_INVALID = "OAuth redirect URI not allowed: {uri}"
LOG_WARN_OAUTH_REDIRECT_BLOCKED = "Blocked redirect to unallowed URI: {uri}"
LOG_WARN_CONFIG_REDIRECT_ALLOWLIST = "OAUTH_ALLOWED_REDIRECT_URIS not configured — rejecting redirect"

# ── Logging: Debug ──
LOG_DEBUG_RS256_VERIFICATION_FAILED = "RS256 verification failed: %s"

# ── Logging: Errors ──
LOG_ERROR_JWKS_LOAD_FAILED = "Cannot load JWKS from {url}: {error}"
LOG_ERROR_JWKS_REFRESH_FAILED = "JWKS refresh failed — using {key_count} stale key(s). Token verification may accept revoked keys. Error: {error}"
LOG_ERROR_OAUTH_TOKEN_EXCHANGE = "OAuth token exchange request failed for {provider}: {error}"
LOG_ERROR_OAUTH_TOKEN_EXCHANGE_STATUS = "OAuth token exchange failed: status={status}"
LOG_ERROR_OAUTH_USERINFO = "OAuth user info request failed for {provider}: {error}"
LOG_ERROR_CONFIG_OAUTH_REDIRECT_URL = "OAUTH_REDIRECT_BASE_URL must be configured for OAuth"

# ── Audit log message templates (audit_logs.message, TENANT status changes) ──
# Picked by app/services/audit_messages.py and filled by ai4i_core.audit when
# the row is written. Each one only says what happened; placeholders are the
# tracked tenant properties ({organisation}, {status}, {reason}) and their old
# values ({previous_status}, ...). ai4i_core.audit adds
# " by <user id> on <time UTC>." and " Reason: <reason>." itself.
# Wording is product-owned.
AUDIT_TENANT_SUSPENDED = "Tenant '{organisation}' suspended"
AUDIT_TENANT_DEACTIVATED = "Tenant '{organisation}' deactivated"
AUDIT_TENANT_REACTIVATED = "Tenant '{organisation}' activated"
AUDIT_TENANT_STATUS_CHANGED = (
    "Tenant '{organisation}' status changed from {previous_status} to {status}"
)
AUDIT_TENANT_SETUP_COMPLETED = (
    "Tenant '{organisation}' activated after the contact admin completed setup"
)
