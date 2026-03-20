"""
Password hashing, verification, and strength validation.
Argon2 with per-user salt.
"""

from app.core.exceptions import PasswordMismatchError, PasswordValidationError
from app.core.security import PasswordHashResult, password_manager


class PasswordService:
    """Wraps the PasswordManager for use as an injectable service."""

    def hash_password(self, password: str) -> PasswordHashResult:
        """Hash a new password with a unique per-user salt."""
        return password_manager.hash_password(password)

    def verify_password(self, plain_password: str, hashed_password: str, salt: str) -> bool:
        """Verify a password against its stored hash."""
        return password_manager.verify_password(plain_password, hashed_password, salt)

    def validate_and_confirm(self, password: str, confirm_password: str) -> None:
        """Validate strength and confirm passwords match. Raises on failure."""
        if password != confirm_password:
            raise PasswordMismatchError()
        valid, errors = password_manager.validate_strength(password)
        if not valid:
            raise PasswordValidationError(errors)
