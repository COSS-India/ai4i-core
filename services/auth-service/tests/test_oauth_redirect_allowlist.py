"""Unit tests for OAuth redirect allowlist helper (_get_allowed_redirect).

This helper is the only gate between a client redirect_uri and RedirectResponse,
so regressions here are open-redirect / broken-login bugs.
"""

from app.routes.oauth import _get_allowed_redirect


_ALLOWLIST = (
    "http://localhost:3000/auth/callback,"
    "https://app.example.com/auth/callback,"
    "https://app.example.com/admin/callback"
)


class TestGetAllowedRedirect:
    def test_exact_match_returns_allowlist_entry(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert (
            _get_allowed_redirect("https://app.example.com/auth/callback")
            == "https://app.example.com/auth/callback"
        )

    def test_query_string_still_matches_same_path(self, monkeypatch):
        """Query on the request must not block a path match; returned URL is
        the allowlist entry (no client query)."""
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert (
            _get_allowed_redirect("https://app.example.com/auth/callback?next=/home")
            == "https://app.example.com/auth/callback"
        )

    def test_same_origin_different_path_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert _get_allowed_redirect("https://app.example.com/other/page") is None

    def test_two_paths_on_same_host_resolve_to_matching_entry(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert (
            _get_allowed_redirect("https://app.example.com/admin/callback")
            == "https://app.example.com/admin/callback"
        )
        assert (
            _get_allowed_redirect("https://app.example.com/auth/callback")
            == "https://app.example.com/auth/callback"
        )

    def test_cross_origin_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert _get_allowed_redirect("https://evil.com/auth/callback") is None

    def test_userinfo_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert (
            _get_allowed_redirect("https://evil.com@app.example.com/auth/callback")
            is None
        )

    def test_non_empty_fragment_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert (
            _get_allowed_redirect("https://app.example.com/auth/callback#token")
            is None
        )

    def test_non_http_scheme_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert _get_allowed_redirect("javascript:alert(1)") is None
        assert _get_allowed_redirect("data:text/html,hi") is None

    def test_empty_allowlist_rejects(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            "",
        )
        assert _get_allowed_redirect("https://app.example.com/auth/callback") is None

    def test_empty_uri_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.oauth.settings.oauth_allowed_redirect_uris",
            _ALLOWLIST,
        )
        assert _get_allowed_redirect("") is None
        assert _get_allowed_redirect(None) is None  # type: ignore[arg-type]
