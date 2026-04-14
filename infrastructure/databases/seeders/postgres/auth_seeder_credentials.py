"""
Shared password material for auth_db user seeders.

Matches auth-service-v2: Argon2 hash of (plaintext + per-user salt). When re-seeding,
reuse existing hash/salt if the configured plaintext still verifies — avoids churn and
unnecessary password column rewrites on every deployment.
"""

import secrets

from passlib.context import CryptContext

# Stored on users.hash_rounds for schema compatibility; Argon2 params live in the hash string.
DEFAULT_HASH_ROUNDS = 12


def resolve_password_hash_material(
    plain_password: str,
    adapter,
    email: str,
) -> tuple[str, str, int]:
    """
    Return (password_hash, password_salt, hash_rounds) for INSERT ... ON CONFLICT.

    If a row exists and plain_password verifies against the stored hash, reuse stored
    hash/salt/rounds. Otherwise generate a new salt and hash.
    """
    ctx = CryptContext(schemes=["argon2"], default="argon2")
    row = adapter.fetch_one(
        "SELECT password_hash, password_salt, hash_rounds FROM users WHERE email = :email",
        {"email": email},
    )
    if row and row[0] and row[1]:
        stored_hash, stored_salt, stored_rounds = row[0], row[1], row[2]
        try:
            if ctx.verify(plain_password + stored_salt, stored_hash):
                return (
                    stored_hash,
                    stored_salt,
                    int(stored_rounds) if stored_rounds is not None else DEFAULT_HASH_ROUNDS,
                )
        except Exception:
            pass

    salt = secrets.token_hex(16)
    password_hash = ctx.hash(plain_password + salt)
    return password_hash, salt, DEFAULT_HASH_ROUNDS
