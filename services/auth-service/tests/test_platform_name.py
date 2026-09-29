"""Platform branding resolution for auth email copy (AI4IDS-2809 / AI4IDS-3043)."""

import pytest
from pydantic import ValidationError

from app.core.config import AuthSettings, settings as app_settings
from app.services import auth_email_templates


def _settings(**kwargs: str) -> AuthSettings:
    return AuthSettings(_env_file=None, **kwargs)


class TestPlatformNameSettings:
    def test_missing_platform_name_fails_startup(self, monkeypatch):
        """No in-code default: an env without PLATFORM_NAME must not start and
        silently send emails under a baked-in name."""
        monkeypatch.delenv("PLATFORM_NAME", raising=False)
        with pytest.raises(ValidationError, match="platform_name"):
            AuthSettings(_env_file=None)

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_platform_name_fails_startup(self, monkeypatch, blank):
        # setup-env.sh writes PLATFORM_NAME= (empty) when the root .env leaves it blank.
        monkeypatch.setenv("PLATFORM_NAME", blank)
        with pytest.raises(ValidationError, match="PLATFORM_NAME must be set"):
            AuthSettings(_env_file=None)

    def test_strips_surrounding_whitespace(self):
        assert _settings(platform_name="  Custom Brand  ").get_platform_name() == "Custom Brand"

    def test_reads_platform_name_env(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "Custom Brand")
        monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)
        settings = AuthSettings(_env_file=None)
        assert settings.get_platform_name() == "Custom Brand"

    def test_get_platform_name_ignores_email_from_name(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "AI4I Orchestrate")
        monkeypatch.setenv("EMAIL_FROM_NAME", "COSS Support")
        settings = AuthSettings(_env_file=None)
        assert settings.get_platform_name() == "AI4I Orchestrate"


class TestAdopterLogoUrlSettings:
    def test_defaults_to_none(self, monkeypatch):
        monkeypatch.delenv("ADOPTER_LOGO_URL", raising=False)
        settings = AuthSettings(_env_file=None)
        assert settings.get_adopter_logo_url() is None

    def test_reads_absolute_https_url(self, monkeypatch):
        monkeypatch.setenv("ADOPTER_LOGO_URL", "https://cdn.example.com/logo.png")
        settings = AuthSettings(_env_file=None)
        assert settings.get_adopter_logo_url() == "https://cdn.example.com/logo.png"

    def test_rejects_relative_path(self):
        settings = _settings(adopter_logo_url="/logo.png")
        assert settings.get_adopter_logo_url() is None

    def test_rejects_blank(self):
        settings = _settings(adopter_logo_url="   ")
        assert settings.get_adopter_logo_url() is None


class TestGetBranding:
    def test_returns_name_and_logo_together(self):
        settings = _settings(
            platform_name="AI4I Orchestrate",
            adopter_logo_url="https://cdn.example.com/orch.png",
        )
        assert settings.get_branding() == {
            "platform_name": "AI4I Orchestrate",
            "logo_url": "https://cdn.example.com/orch.png",
        }

    def test_logo_null_when_unset(self):
        settings = _settings(platform_name="AI4I Orchestrate", adopter_logo_url="")
        assert settings.get_branding() == {
            "platform_name": "AI4I Orchestrate",
            "logo_url": None,
        }


class TestResolveSmtpFromName:
    def test_inherits_platform_name_when_blank(self):
        settings = _settings(platform_name="MahaVistaar")
        assert settings.resolve_smtp_from_name("") == "MahaVistaar"
        assert settings.resolve_smtp_from_name("   ") == "MahaVistaar"

    def test_keeps_explicit_from_name(self):
        settings = _settings(platform_name="AI4I Orchestrate")
        assert settings.resolve_smtp_from_name("COSS Support") == "COSS Support"

    def test_email_from_name_mirror_defaults_blank_so_it_inherits(self, monkeypatch):
        # Matches ai4i_core EmailSettings.email_from_name's "" default — not a baked-in name.
        monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)
        settings = _settings(platform_name="MahaVistaar")
        assert settings.email_from_name == ""
        assert settings.resolve_smtp_from_name(settings.email_from_name) == "MahaVistaar"


class TestRenderedEmailUsesEnvPlatformName:
    """The reported bug end to end: the name in a sent email must be exactly the
    configured PLATFORM_NAME, never a name hardcoded in the code."""

    def test_account_deleted_email_uses_configured_name(self, monkeypatch):
        monkeypatch.setattr(app_settings, "platform_name", "MahaVistaar")

        message = auth_email_templates.render_account_deleted("a@b.com", "Priya")

        assert message.subject == "Your MahaVistaar account has been deleted"
        for body in (message.html_body, message.text_body):
            assert "MahaVistaar" in body
            assert "AI Switch" not in body
            assert "Orchestrate" not in body
