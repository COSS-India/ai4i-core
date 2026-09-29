"""Cross-module constants used by schemas, services, and routes."""

import enum


# ── Permission IDs (match permissions.id — NOT roles.id) ─────────────
class RoleId:
    ADMIN = 1
    MODERATOR = 2
    GUEST = 3
    USER = 4
    TENANT_ADMIN = 5


# ── Role Names (must match the seeded values in roles table) ──────────
class RoleName(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"
    MODERATOR = "MODERATOR"
    TENANT_ADMIN = "TENANT ADMIN"
    USAGE_VIEWER = "USAGE VIEWER"


# ── Environment ──────────────────────────────────────────────────────
# We only differentiate "development" from everything else. Anything that
# isn't local dev (production, staging, preprod, anything else) is treated
# the same: hide /docs, refuse RS256 key autogen, reject http://localhost
# email links, etc. This is the safer default — staging mirrors prod.
ENV_DEVELOPMENT = "development"

# Product name used when PLATFORM_NAME is unset or blank (email copy + SMTP From name).
DEFAULT_PLATFORM_NAME = "AI Switch"


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

# ── API-key cache: tier ──────────────────────────────────────────────
# Cached tier_id written onto every key of a tenant whose tier was removed
# (DELETE /auth/tenants/{id}/tier). Deliberately distinct from the field
# being ABSENT (legacy keys issued before tiers existed, still served on
# budget alone): present-and-empty means "tier explicitly removed", and
# /auth/validate rejects it with NO_ACTIVE_TIER. Empty rather than a
# non-UUID word so nothing downstream that CASTs X-Tier-ID to uuid can
# ever see a malformed value.
UNASSIGNED_TIER_ID = ""
