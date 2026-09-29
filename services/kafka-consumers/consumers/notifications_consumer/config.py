"""Settings specific to notifications_consumer. Nothing here belongs in
bootstrap/config.py — topics, service URLs and domain constants are
per-consumer (ARCHITECTURE.md §3.1/§5).

See skills/notification-kafka-design/notification-kafka-design.md for the
design this consumer implements.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from ai4i_core.kafka.constants import REDIS_KEY_PREFIX
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Constants:
    # One claim per delivered event_id (SET NX) — catches a Kafka
    # redelivery of an event this consumer already handled.
    DELIVERY_CLAIM_KEY_PREFIX = f"{REDIS_KEY_PREFIX}delivered:"
    DELIVERY_CLAIM_TTL_SECONDS = 7 * 24 * 3600


class Settings(BaseSettings):
    TOPIC_NOTIFICATION: str = Field(
        description="Kafka topic this consumer subscribes to — design doc §10."
    )
    PORTAL_URL: Optional[str] = Field(
        default=None,
        description="Same setting as platform-core-service's settings.portal_url — "
        "the '_portal_line.html' include (email_templates.py) links here when set, "
        "and falls back to unlinked plain text in every rendered email when it isn't.",
    )
    # Branding — same PLATFORM_NAME / ADOPTER_LOGO_URL pair as auth-service
    # (AI4IDS-3043), copied here from the root .env by ./scripts/setup-env.sh.
    # Independent of the SMTP From display name (EMAIL_FROM_NAME, read by
    # ai4i_core EmailSettings) — see resolve_smtp_from_name.
    PLATFORM_NAME: str = Field(
        description="Product name in every rendered email's title, header, footer, "
        "portal line and sign-off. Required, no in-code default: a missing/blank "
        "value fails startup (main.py loads settings first) instead of silently "
        "sending emails under a baked-in name.",
    )
    ADOPTER_LOGO_URL: Optional[str] = Field(
        default=None,
        description="Absolute http(s) logo URL for the email header. Relative paths "
        "are ignored (email clients cannot resolve them); unset ⇒ text brand mark.",
    )

    def get_platform_name(self) -> str:
        """Product name for email copy (PLATFORM_NAME, validated non-blank)."""
        return self.PLATFORM_NAME

    def get_adopter_logo_url(self) -> Optional[str]:
        """Absolute http(s) logo for email headers; None when unset/invalid."""
        raw = (self.ADOPTER_LOGO_URL or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
        return None

    def resolve_smtp_from_name(self, email_from_name: str) -> str:
        """SMTP From display name: explicit EMAIL_FROM_NAME, else platform name.

        The provider is built from ai4i_core EmailSettings, so emailer.py passes
        that value in and applies this result when constructing the client."""
        return (email_from_name or "").strip() or self.get_platform_name()

    @field_validator("PLATFORM_NAME")
    @classmethod
    def _platform_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("PLATFORM_NAME must be set to the product name used in emails")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
