"""Provider-agnostic email settings.

Loaded by each consuming service from its own .env. The lib never reads
credentials except through this class, so logging / repr stays clean.
"""

import json
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Provider selection: "smtp" (default) | "console" | future "sendgrid_api", "mailgun_api"
    email_provider: str = "smtp"

    # Generic sender identity (every provider needs these)
    email_from: Optional[str] = None
    email_from_name: str = ""
    email_reply_to: Optional[str] = None

    # Optional extra headers as JSON. For SES Configuration Set:
    # EMAIL_EXTRA_HEADERS={"X-SES-CONFIGURATION-SET": "my-config-set"}
    email_extra_headers: Optional[str] = None

    # SMTP transport settings (used by SmtpEmailProvider)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    # Network timeout for one SMTP send attempt, in seconds. Provider-level —
    # e.g. SES typically responds in < 1s; bump if behind a slow relay.
    smtp_timeout: int = 30

    # Gates dev fallback to ConsoleEmailProvider
    environment: str = "development"

    @field_validator("smtp_use_tls", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on"}
        return bool(v)

    @field_validator("email_from", "email_from_name", "email_reply_to")
    @classmethod
    def _no_crlf(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and ("\r" in v or "\n" in v):
            raise ValueError("must not contain CR or LF (header injection)")
        return v

    def parsed_extra_headers(self) -> dict[str, str]:
        if not self.email_extra_headers:
            return {}
        try:
            data = json.loads(self.email_extra_headers)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "EMAIL_EXTRA_HEADERS must be a JSON object string"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("EMAIL_EXTRA_HEADERS must decode to a JSON object")
        return {str(k): str(v) for k, v in data.items()}

    def is_dev(self) -> bool:
        return self.environment.strip().lower() == "development"
