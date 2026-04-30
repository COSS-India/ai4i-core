"""
RS256 key management and password hashing (argon2).
"""

import base64
import logging
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# RS256 Key Manager
# ─────────────────────────────────────────────


class RSAKeyPair:
    """Holds a single RSA key pair with its key ID."""

    def __init__(self, kid: str, private_key, public_key):
        self.kid = kid
        self.private_key = private_key
        self.public_key = public_key


class RS256KeyManager:
    """
    Manages multiple RSA key pairs for RS256 JWT signing/verification.

    - Loads PEM files from disk (production) or auto-generates (development).
    - Supports key rotation: sign with the active key, verify with any loaded key.
    - Exposes JWKS for external verification (APISIX, other services).
    """

    def __init__(self) -> None:
        self._keys: list[RSAKeyPair] = []
        self._keys_by_kid: dict[str, RSAKeyPair] = {}
        self._active_index: int = 0

    async def initialize(self) -> None:
        """
        Load keys from disk. In production, FAIL FAST if keys are missing.
        Auto-generation is only allowed in development/testing.
        """
        key_dir = settings.get_rs256_key_path()
        is_production = settings.environment in ("production", "staging")

        if key_dir.exists() and any(key_dir.glob("*.pem")):
            self._load_from_directory(key_dir)
        elif is_production:
            raise RuntimeError(
                f"FATAL: No RSA keys found at '{key_dir}'. "
                f"In production/staging, pre-provisioned PEM key pairs are required. "
                f"Mount them via Docker volume or Kubernetes secret. "
                f"Auto-generation is disabled in '{settings.environment}' to prevent "
                f"cross-replica key mismatch and token invalidation."
            )
        else:
            logger.warning(
                "No RSA keys found at %s — generating %d key pairs for development.",
                key_dir, settings.rs256_min_key_count,
            )
            key_dir.mkdir(parents=True, exist_ok=True)
            self._generate_keys(key_dir, settings.rs256_min_key_count)

        if len(self._keys) < settings.rs256_min_key_count:
            if is_production:
                raise RuntimeError(
                    f"FATAL: Only {len(self._keys)} key pair(s) found, "
                    f"minimum required is {settings.rs256_min_key_count}. "
                    f"Provision at least {settings.rs256_min_key_count} RSA key pairs."
                )
            logger.warning(
                "Only %d key pair(s) found, minimum is %d. Generating additional keys.",
                len(self._keys), settings.rs256_min_key_count,
            )
            self._generate_keys(key_dir, settings.rs256_min_key_count - len(self._keys))

        self._active_index = min(settings.rs256_active_key_index, len(self._keys) - 1)
        logger.info("RS256 KeyManager: %d key(s) loaded, active kid=%s", len(self._keys), self.active_kid)

    def _load_from_directory(self, key_dir: Path) -> None:
        """Load key pairs from PEM files: key_01_private.pem / key_01_public.pem."""
        private_files = sorted(key_dir.glob("*_private.pem"))
        for priv_path in private_files:
            kid = priv_path.stem.replace("_private", "")
            pub_path = priv_path.parent / f"{kid}_public.pem"
            if not pub_path.exists():
                logger.warning("Missing public key for %s, skipping.", kid)
                continue
            try:
                private_key = serialization.load_pem_private_key(
                    priv_path.read_bytes(), password=None, backend=default_backend()
                )
                public_key = serialization.load_pem_public_key(
                    pub_path.read_bytes(), backend=default_backend()
                )
                pair = RSAKeyPair(kid=kid, private_key=private_key, public_key=public_key)
                self._keys.append(pair)
                self._keys_by_kid[kid] = pair
            except (ValueError, TypeError, OSError):
                logger.exception("Failed to load key pair %s", kid)

    def _generate_keys(self, key_dir: Path, count: int) -> None:
        """Generate RSA key pairs and persist to disk."""
        existing = len(self._keys)
        for i in range(count):
            idx = existing + i + 1
            kid = f"key_{idx:02d}"
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
            public_key = private_key.public_key()

            priv_path = key_dir / f"{kid}_private.pem"
            pub_path = key_dir / f"{kid}_public.pem"
            priv_path.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            pub_path.write_bytes(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

            pair = RSAKeyPair(kid=kid, private_key=private_key, public_key=public_key)
            self._keys.append(pair)
            self._keys_by_kid[kid] = pair

        logger.info("Generated %d RSA key pair(s) in %s", count, key_dir)

    # ── Public API ──

    @property
    def active_kid(self) -> str:
        return self._keys[self._active_index].kid

    def get_signing_key(self):
        return self._keys[self._active_index].private_key

    def get_signing_kid(self) -> str:
        return self._keys[self._active_index].kid

    def get_public_key(self, kid: str):
        pair = self._keys_by_kid.get(kid)
        if pair is None:
            raise ValueError(f"Unknown key ID: {kid}")
        return pair.public_key

    def get_all_public_keys(self) -> list[RSAKeyPair]:
        return list(self._keys)

    def get_jwks(self) -> dict:
        """Return a JWKS (JSON Web Key Set) dict with all public keys."""
        keys = []
        for pair in self._keys:
            pub_numbers = pair.public_key.public_numbers()
            n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, byteorder="big")
            e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, byteorder="big")
            keys.append({
                "kty": "RSA",
                "use": "sig",
                "kid": pair.kid,
                "alg": "RS256",
                "n": base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode(),
                "e": base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode(),
            })
        return {"keys": keys}


# Module-level singleton
key_manager = RS256KeyManager()


# ─────────────────────────────────────────────
# Password Manager (argon2 only)
# ─────────────────────────────────────────────


class PasswordHashResult:
    """Result of hashing a password."""

    def __init__(self, hashed: str, salt: str, rounds: int):
        self.hashed = hashed
        self.salt = salt
        self.rounds = rounds


class PasswordManager:
    """
    Handles password hashing with per-user salt using argon2.
    Fresh install — argon2 only.
    """

    def __init__(self) -> None:
        from passlib.context import CryptContext
        self._context = CryptContext(schemes=["argon2"], default="argon2")

    def hash_password(self, password: str) -> PasswordHashResult:
        """Hash a password with a unique salt. Returns hash, salt, and rounds."""
        salt = secrets.token_hex(settings.argon2_salt_length)
        salted_password = password + salt
        hashed = self._context.hash(salted_password)
        return PasswordHashResult(
            hashed=hashed,
            salt=salt,
            rounds=settings.default_hash_rounds,
        )

    def verify_password(self, plain_password: str, hashed_password: str, salt: str) -> bool:
        """Verify a password against its hash using the stored salt."""
        salted_password = plain_password + salt
        return self._context.verify(salted_password, hashed_password)

    @staticmethod
    def validate_strength(password: str) -> tuple[bool, list[str]]:
        """Validate password meets minimum strength requirements."""
        errors: list[str] = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number.")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            errors.append("Password must contain at least one special character.")
        return len(errors) == 0, errors


password_manager = PasswordManager()
