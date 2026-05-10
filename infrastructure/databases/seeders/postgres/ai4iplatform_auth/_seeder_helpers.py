"""Shared helpers for ai4iplatform_auth seeders."""

import secrets

from passlib.context import CryptContext


# Fixed identity for all rows written by seeders — readable as "seed0000…"
SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

DEFAULT_TENANT_ORG = "default organisation"

_CTX = CryptContext(schemes=["argon2"], default="argon2")


def resolve_credentials(adapter, email: str, plain_password: str) -> tuple[str, str]:
    """Return (password_hash, password_salt) for the given user.

    Reuses the stored hash/salt when the plain password still verifies against
    the stored hash, to avoid unnecessary column rewrites on every deployment.
    """
    row = adapter.fetch_one(
        """
        SELECT uc.password_hash, uc.password_salt
        FROM users u
        JOIN user_credentials uc ON u.id = uc.user_id
        WHERE u.email = :email
        """,
        {"email": email},
    )
    if row and row[0] and row[1]:
        stored_hash, stored_salt = row[0], row[1]
        try:
            if _CTX.verify(plain_password + stored_salt, stored_hash):
                return stored_hash, stored_salt
        except Exception:
            pass

    salt = secrets.token_hex(16)
    return _CTX.hash(plain_password + salt), salt
