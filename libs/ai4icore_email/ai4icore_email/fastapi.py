"""FastAPI dependency factory.

Lazily builds an EmailClient singleton from EmailSettings on first request.
Use via:

    from ai4icore_email import EmailClient, get_email_client
    @app.post("/something")
    async def handler(client: EmailClient = Depends(get_email_client)):
        ...

Tests can override with FastAPI's dependency_overrides[get_email_client].
"""

from functools import lru_cache

from ai4icore_email.client import EmailClient
from ai4icore_email.providers.factory import build_provider
from ai4icore_email.settings import EmailSettings


@lru_cache(maxsize=1)
def _build_default_client() -> EmailClient:
    settings = EmailSettings()
    provider = build_provider(settings)
    return EmailClient(provider)


def get_email_client() -> EmailClient:
    return _build_default_client()


def reset_default_client_cache() -> None:
    """Test helper: clear the lru_cache so a new EmailSettings() is read."""
    _build_default_client.cache_clear()
