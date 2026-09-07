"""Platform branding resolution for auth email copy (AI4IDS-2809 / AI4IDS-3043)."""

from app.core.config import AuthSettings


def _settings(**kwargs: str) -> AuthSettings:
    return AuthSettings(_env_file=None, **kwargs)


class TestPlatformNameSettings:
    def test_defaults_to_ai4i_orchestrate(self, monkeypatch):
        monkeypatch.delenv("PLATFORM_NAME", raising=False)
        monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)
        monkeypatch.delenv("ADOPTER_LOGO_URL", raising=False)
        settings = AuthSettings(_env_file=None)
        assert settings.platform_name == "AI4I Orchestrate"
        assert settings.get_platform_name() == "AI4I Orchestrate"

    def test_reads_platform_name_env(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "Custom Brand")
        monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)
        settings = AuthSettings(_env_file=None)
        assert settings.get_platform_name() == "Custom Brand"

    def test_falls_back_when_blank(self):
        settings = _settings(platform_name="   ")
        assert settings.get_platform_name() == "AI4I Orchestrate"

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

    def test_falls_back_when_both_blank(self):
        settings = _settings(platform_name="")
        assert settings.resolve_smtp_from_name("") == "AI4I Orchestrate"
