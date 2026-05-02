"""Cross-module constants used by schemas, services, and routes."""


# ── Environment names — single source of truth ──────────────────────
ENV_PRODUCTION = "production"
ENV_STAGING = "staging"
ENV_DEVELOPMENT = "development"


class TokenType:
    ACCESS = "access_token"
    REFRESH = "refresh"
    SETUP = "setup"
    VERIFY = "verify"
    RESET = "reset"


# ── Password policy ──────────────────────────────────────────────────
# Mirrored in PasswordManager.validate_strength and every Pydantic
# password field — keep them in lockstep with the security spec.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64

# ── String-field max lengths used across user/tenant schemas ─────────
USERNAME_MAX_LENGTH = 100
FULL_NAME_MAX_LENGTH = 255
PHONE_NUMBER_MAX_LENGTH = 20
TIMEZONE_MAX_LENGTH = 50
ORGANISATION_MAX_LENGTH = 255
