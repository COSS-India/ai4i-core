import re
from datetime import datetime, timezone
import secrets
import uuid
import string
from passlib.context import CryptContext
from passlib.hash import argon2



BASE_DOMAIN = "ai4i.com"  # replace via env var in production
DEFAULT_QUOTAS = {
    "api_calls_per_day": 10_000,
    "storage_gb": 10,
}

def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")

def generate_tenant_id(org_name: str) -> str:
    base = slugify(org_name)
    suffix = secrets.token_hex(3)  # short random suffix to avoid collisions
    return f"{base}-{suffix}"

def generate_subdomain(tenant_id: str) -> str:
    # subdomain like <tenant_id>.<BASE_DOMAIN>
    return f"{tenant_id}.{BASE_DOMAIN}"

def schema_name_from_tenant_id(tenant_id: str) -> str:
    # safe schema name: tenant_<slug>
    return f"tenant_{re.sub(r'[^a-z0-9_]+', '_', tenant_id)}"

def now_utc():
    return datetime.now(timezone.utc)

def generate_billing_customer_id(tenant_id: str) -> str:
    """
    Generate billing customer ID.
    Later this can be replaced by Stripe/Razorpay/Google pay customer id.
    """
    return f"BILL-{tenant_id[:8]}-{uuid.uuid4().hex[:6]}"

def generate_email_verification_token() -> str:
    """
    Generate token for email verification
    """
    return secrets.token_urlsafe(32)


def generate_service_id() -> int:
    """
    Generate a random positive BIGINT (fits PostgreSQL BIGINT).
    """
    return secrets.randbits(25)  # max 9.22e18


# def generate_random_password(length: int = 8) -> str:
#     alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
#     return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_random_password(length: int = 8) -> str:
    if length < 4:
        raise ValueError("Password length must be at least 4")

    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"

    # Ensure required characters
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special),
    ]

    # Fill remaining length
    all_chars = lowercase + uppercase + digits + special
    password += [secrets.choice(all_chars) for _ in range(length - 4)]

    # Shuffle so order is unpredictable
    secrets.SystemRandom().shuffle(password)

    return "".join(password)


def hash_password(password: str) -> str:
    """
    Hash a password using argon2 (same algorithm as auth service).
    """
    # pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") # old bcrypt
    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
    return pwd_context.hash(password)

