"""
Centralized message constants for auth-service.

All user-facing messages and log messages are defined here with consistent keys.
This provides a single source of truth for message management and translations.
"""

# ── Authentication Errors (4xx user-facing) ──
AUTH_REQUIRED = "Authentication required."
AUTH_FAILED = "Authentication failed."
TOKEN_INVALID = "Token validation failed."
TOKEN_EXPIRED = "Token has expired."
TOKEN_MISSING = "Token header missing 'kid'."
TOKEN_MISSING_SUB = "Token missing 'sub' claim."
TOKEN_HEADER_INVALID = "Invalid token header."
TOKEN_ALGORITHM_UNSUPPORTED = "Unsupported algorithm. Expected RS256."
TOKEN_NO_KEYS = "No verification keys available."
CREDENTIALS_NOT_FOUND = "No credentials found for user."
PASSWORD_CURRENT_INCORRECT = "Current password is incorrect."

# ── Authorization Errors ──
API_KEY_MISMATCH = "API key does not belong to you."
PERMISSION_DENIED = "Permission denied."

# ── OAuth Errors ──
OAUTH_PROVIDER_UNKNOWN = "OAuth provider is not configured."
OAUTH_PROVIDER_MISMATCH = "OAuth provider mismatch."
OAUTH_PROVIDER_UNREACHABLE = "OAuth provider unreachable."
OAUTH_STATE_INVALID = "Invalid or expired OAuth state."
OAUTH_REDIRECT_URI_INVALID = "Redirect URI is not allowed."
OAUTH_CODE_INVALID = "Invalid or expired exchange code."
OAUTH_CODE_EXCHANGE_FAILED = "Failed to exchange authorization code."
OAUTH_USERINFO_FETCH_FAILED = "Failed to fetch user info from provider."
OAUTH_ACCESS_TOKEN_MISSING = "No access token received from provider."
OAUTH_EMAIL_UNVERIFIED = "OAuth email address is not verified."

# ── Email/Token Verification Errors ──
VERIFICATION_LINK_INVALID = "Invalid verification link."
VERIFICATION_LINK_EXPIRED = "Verification link has expired."
VERIFICATION_ALREADY_DONE = "Email already verified."
SETUP_LINK_INVALID = "Invalid setup link."
SETUP_LINK_EXPIRED = "Setup link has expired."
SETUP_LINK_USED = "Setup link has already been used."
RESET_LINK_INVALID = "Invalid reset link."
RESET_LINK_EXPIRED = "Reset link has expired."
RESET_LINK_USED = "Reset link has already been used."

# ── Entity Not Found ──
USER_NOT_FOUND = "User not found."
USER_INACTIVE = "User account is inactive."
ROLE_NOT_FOUND = "Role not found."
TENANT_NOT_FOUND = "Tenant not found."
PERMISSION_NOT_FOUND = "Permission not found."

# ── Validation Errors ──
FIELD_REQUIRED = "This field is required."
FIELD_INVALID = "Invalid value for this field."
UPDATE_NEEDS_FIELDS = "Provide at least one field to update."
UPDATE_TENANT_NEEDS_FIELDS = "Provide at least one of is_active or is_tenant_active."
TOKEN_TYPE_INVALID = "Expected a '{expected_type}' token."
JWK_MISSING_FIELDS = "JWK missing required 'n' or 'e' field."

# ── Success Messages (user-facing) ──
PASSWORD_CHANGED = "Password changed successfully."
PASSWORD_RESET = "Password reset successfully."
SETUP_COMPLETE = "Account setup completed successfully."
VERIFICATION_SENT = "Verification link sent to your email."
SETUP_LINK_SENT = "Setup link sent to your email."
SETUP_LINK_RESENT = "New setup link issued."
RESET_LINK_SENT = "Password reset link sent to your email."
API_KEY_CREATED = "API key created successfully."
API_KEY_REVOKED = "API key revoked successfully."

# ── Logging: Info/Success ──
LOG_SERVICE_START = "Starting {service_name} v{version} [{environment}]"
LOG_SERVICE_SHUTDOWN = "Shutdown complete."
LOG_TELEMETRY_ENABLED = "OpenTelemetry FastAPI instrumentation enabled."
LOG_TELEMETRY_UNAVAILABLE = "Telemetry not available, skipping."
LOG_JWT_VERIFIER_INIT = "Shared JWTVerifier initialized with {key_count} public keys."
LOG_JWKS_REFRESHED = "JWKS refreshed: {key_count} public key(s) loaded from {url}"
LOG_KEYS_GENERATED = "Generated {count} RSA key pair(s) in {path}"
LOG_KEYS_LOADED = "RS256 KeyManager: {count} key(s) loaded, active kid={kid}"
LOG_API_PERMISSIONS_LOADED = "API permission mapping loaded: {endpoint_count} endpoints."
LOG_REDIS_CONNECTED = "Redis connection established for {name}."
LOG_REDIS_DISCONNECTED = "Redis connection closed."
LOG_ROLE_ASSIGNED = "Role '{role}' assigned to user {user_id}"
LOG_EMAIL_VERIFIED = "Email verified for user id={user_id}"
LOG_PASSWORD_CHANGED = "Password changed for user id={user_id}"
LOG_PASSWORD_RESET = "Password reset for user id={user_id}; refresh tokens revoked"
LOG_RESET_LINK_ISSUED = "Password reset link issued for user id={user_id}"
LOG_SETUP_LINK_RESENT = "Setup link resent for user id={user_id}"
LOG_SETUP_VIA_LINK = "Password set via activation link for user id={user_id}"
LOG_API_KEY_CREATED = "API key created: name={name} user={user_id}"
LOG_API_KEY_REVOKED = "API key revoked: api_key={api_key_id}"
LOG_OAUTH_LOGIN = "OAuth login: {email} via {provider} (user_id={user_id})"
LOG_OAUTH_USER_CREATED = "OAuth user created: {email} via {provider} (id={user_id})"
LOG_DEFAULT_ROLE_MISSING = "Default USER role not found, skipping role assignment."
LOG_NO_PERMISSIONS_FILE = "No api_permissions.json found, skipping."

# ── Logging: Warnings ──
LOG_WARN_JWT_NO_KEYS = "JWTVerifier: no JWKS URL configured and no keys loaded."
LOG_WARN_JWK_CONVERT_FAILED = "Failed to convert JWK kid={kid} to PEM"
LOG_WARN_KEY_MISSING = "Missing public key for {kid}, skipping."
LOG_WARN_OAUTH_REDIRECT_INVALID = "OAuth redirect URI not allowed: {uri}"
LOG_WARN_OAUTH_REDIRECT_BLOCKED = "Blocked redirect to unallowed URI: {uri}"
LOG_WARN_PERMISSIONS_LOAD_FAILED = "Failed to load API permission mapping: {error}"
LOG_WARN_ROLE_ASSIGNMENT_FAILED = "Role '{role}' not found, skipping role assignment."
LOG_WARN_ROLE_NAME_MAPPING_FAILED = "Unknown role name {role}, skipping."

# ── Logging: Errors ──
LOG_ERROR_DEBUG_IN_PROD = "FATAL: DEBUG=true is not allowed in {environment}."
LOG_ERROR_JWT_NOT_INITIALIZED = "JWTVerifier not initialized. Call init_jwt_verifier() during startup."
LOG_ERROR_REDIS_NOT_INITIALIZED = "Redis not initialized."
LOG_ERROR_JWKS_LOAD_FAILED = "Cannot load JWKS from {url}: {error}"
LOG_ERROR_JWKS_REFRESH_FAILED = "JWKS refresh failed — using {key_count} stale key(s). Token verification may accept revoked keys. Error: {error}"
LOG_ERROR_KEY_LOAD_FAILED = "Failed to load key pair {path}"
LOG_ERROR_PERMISSIONS_LOAD_FAILED = "Giving up loading API permission mapping after {attempts} attempts: {error}"
LOG_ERROR_EMAIL_RENDER_FAILED = "email render failed"
LOG_ERROR_OAUTH_TOKEN_EXCHANGE = "OAuth token exchange request failed for {provider}: {error}"
LOG_ERROR_OAUTH_TOKEN_EXCHANGE_STATUS = "OAuth token exchange failed: status={status}"
LOG_ERROR_OAUTH_USERINFO = "OAuth user info request failed for {provider}: {error}"
LOG_ERROR_CACHE_REFRESH_FAILED = "RolePermissionCache refresh failed (database/network issue); will retry next cycle."
LOG_ERROR_CACHE_REFRESH_UNEXPECTED = "RolePermissionCache refresh failed with unexpected error; will retry next cycle."

# ── Configuration Errors ──
CONFIG_MISSING = "{env_var} is not configured"
CONFIG_DEBUG_NOT_ALLOWED = "FATAL: DEBUG=true is not allowed in {environment}."

# ── Generic/Framework Messages ──
ENTITY_NOT_FOUND = "Entity not found: {entity_type}"
INTERNAL_ERROR = "An internal error occurred. Please try again later."
UNKNOWN_KEY_ID = "Unknown key ID"

# ── Guest Inference ──
LOG_GUEST_INFERENCE_SET = "GUEST inference services set to: {services}"
