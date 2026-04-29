"""
Tests for exception handling and response format.
"""

from app.core.exceptions import (
    AuthServiceError,
    DuplicateEntityError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    PasswordValidationError,
    TokenExpiredError,
    TokenRevokedError,
    UserNotFoundError,
)


class TestExceptions:
    def test_invalid_credentials(self):
        exc = InvalidCredentialsError()
        assert exc.code == "INVALID_CREDENTIALS"
        assert "password" in exc.message.lower()

    def test_token_expired(self):
        exc = TokenExpiredError()
        assert exc.code == "TOKEN_EXPIRED"

    def test_token_revoked(self):
        exc = TokenRevokedError()
        assert exc.code == "TOKEN_REVOKED"

    def test_insufficient_permissions(self):
        exc = InsufficientPermissionsError("users", "delete")
        assert exc.code == "INSUFFICIENT_PERMISSIONS"
        assert "users.delete" in exc.message

    def test_user_not_found(self):
        exc = UserNotFoundError()
        assert exc.code == "USER_NOT_FOUND"

    def test_duplicate_entity(self):
        exc = DuplicateEntityError("User", "email")
        assert exc.code == "DUPLICATE_ENTITY"
        assert "email" in exc.message

    def test_password_validation(self):
        exc = PasswordValidationError(["Too short", "No uppercase"])
        assert exc.code == "PASSWORD_VALIDATION_ERROR"
        assert len(exc.errors) == 2

    def test_base_error(self):
        exc = AuthServiceError("Custom error", "CUSTOM_CODE")
        assert exc.code == "CUSTOM_CODE"
        assert exc.message == "Custom error"
