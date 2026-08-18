"""Platform name resolution for auth email copy (AI4IDS-2809)."""

from app.core.config import AuthSettings


def _settings(**env: str) -> AuthSettings:
    return AuthSettings(_env_file=None, **env)


class TestPlatformNameSettings:
    def test_defaults_to_ai_switch(self, monkeypatch):
        monkeypatch.delenv("PLATFORM_NAME", raising=False)
        monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)
        settings = AuthSettings(_env_file=None)
        assert settings.platform_name == "AI Switch"
        assert settings.get_platform_name() == "AI Switch"

    def test_reads_platform_name_env(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "Custom Brand")
        monkeypatch.delenv("EMAIL_FROM_NAME", raising=False)
        settings = AuthSettings(_env_file=None)
        assert settings.get_platform_name() == "Custom Brand"

    def test_falls_back_when_blank(self):
        settings = _settings(platform_name="   ")
        assert settings.get_platform_name() == "AI Switch"

    def test_email_from_name_inherits_platform_name_when_blank(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "Custom Brand")
        monkeypatch.setenv("EMAIL_FROM_NAME", "")
        settings = AuthSettings(_env_file=None)
        assert settings.email_from_name == "Custom Brand"

    def test_email_from_name_stays_independent(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "AI Switch")
        monkeypatch.setenv("EMAIL_FROM_NAME", "COSS Support")
        settings = AuthSettings(_env_file=None)
        assert settings.get_platform_name() == "AI Switch"
        assert settings.email_from_name == "COSS Support"

    def test_get_platform_name_ignores_email_from_name(self):
        settings = _settings(platform_name="AI Switch", email_from_name="COSS Support")
        assert settings.get_platform_name() == "AI Switch"
