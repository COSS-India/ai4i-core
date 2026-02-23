import re
import os
import hashlib
import base64
import logging
from datetime import datetime, timezone
import secrets
import uuid
import string
from passlib.context import CryptContext
from passlib.hash import argon2
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)



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


# Encryption utilities for email and phone_number
ENCRYPTION_KEY = os.getenv("API_KEY_ENCRYPTION_KEY", None)

def _get_encryption_key() -> bytes:
    """Get or generate encryption key for email/phone encryption (Fernet key format)"""
    if ENCRYPTION_KEY:
        try:
            Fernet(ENCRYPTION_KEY.encode())
            return ENCRYPTION_KEY.encode()
        except Exception:
            logger.warning("Invalid API_KEY_ENCRYPTION_KEY format, generating new key")
    
    # Generate a key from JWT_SECRET_KEY if available
    jwt_secret = os.getenv("JWT_SECRET_KEY", None)
    if jwt_secret and jwt_secret != "dhruva-jwt-secret-key-2024-super-secure":
        key_material = hashlib.sha256(jwt_secret.encode()).digest()[:32]
        fernet_key = base64.urlsafe_b64encode(key_material)
        return fernet_key
    
    logger.warning("No API_KEY_ENCRYPTION_KEY set, using generated key (will change on restart)")
    return Fernet.generate_key()

# Initialize Fernet cipher
try:
    encryption_key = _get_encryption_key()
    _fernet = Fernet(encryption_key)
    
    # Warn if using generated key (will cause decryption failures if data was encrypted with different key)
    if not ENCRYPTION_KEY:
        logger.warning(
            "⚠️  API_KEY_ENCRYPTION_KEY environment variable is not set! "
            "Using generated encryption key which will change on restart. "
            "This will cause decryption failures for existing encrypted data. "
            "Set API_KEY_ENCRYPTION_KEY to a consistent value to fix this issue."
        )
except Exception as e:
    logger.error(f"Failed to initialize Fernet cipher: {e}")
    _fernet = Fernet(Fernet.generate_key())
    logger.error(
        "⚠️  Using fallback generated encryption key. "
        "Decryption of existing encrypted data will fail. "
        "Set API_KEY_ENCRYPTION_KEY environment variable to fix this."
    )


def encrypt_sensitive_data(data: str) -> str:
    """
    Encrypt sensitive data (email or phone_number) using Fernet.
    
    Args:
        data: Plain text data to encrypt
        
    Returns:
        Encrypted string (base64 encoded)
    """
    if not data:
        return data
    try:
        encrypted = _fernet.encrypt(data.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Error encrypting data: {e}")
        raise ValueError("Failed to encrypt sensitive data")


def decrypt_sensitive_data(encrypted_data: str) -> Optional[str]:
    """
    Decrypt sensitive data (email or phone_number) using Fernet.
    
    Args:
        encrypted_data: Encrypted string (base64 encoded)
        
    Returns:
        Decrypted plain text string, or None if decryption fails
    """
    if not encrypted_data:
        return encrypted_data
    try:
        decrypted = _fernet.decrypt(encrypted_data.encode())
        return decrypted.decode()
    except Exception as e:
        logger.warning(f"Error decrypting data: {e}")
        # If the input looks like a Fernet token (starts with the Fernet prefix),
        # raise a clear error so callers can surface an actionable message
        # (e.g. key mismatch / wrong API_KEY_ENCRYPTION_KEY).
        try:
            if isinstance(encrypted_data, str) and encrypted_data.startswith("gAAAA"):
                # Raise a specific exception for callers to handle
                raise DecryptionError("Failed to decrypt Fernet token - possible encryption key mismatch or corrupted token")
        except DecryptionError:
            raise
        except Exception:
            pass
        # Otherwise, assume it's plain text (backward compatibility) and return it.
        return encrypted_data


class DecryptionError(Exception):
    """Raised when decryption of a Fernet token fails due to key mismatch or corruption."""
    pass

