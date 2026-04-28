"""EmailMessage payload + safe MIME builder.

Header-injection defense:
- Recipient and subject are pre-validated to reject CR/LF before being
  attached to the MIME message. email.message.EmailMessage already folds
  headers safely, but explicit rejection guards against any future code
  path that builds raw header strings.
"""

from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr
from typing import Optional


def _reject_crlf(value: str, field_name: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError(
            f"{field_name} must not contain CR or LF characters (header injection)"
        )
    return value


@dataclass
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str
    headers: dict[str, str] = field(default_factory=dict)
    reply_to: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None

    def __post_init__(self) -> None:
        _reject_crlf(self.to, "to")
        _reject_crlf(self.subject, "subject")
        if self.reply_to is not None:
            _reject_crlf(self.reply_to, "reply_to")
        if self.from_email is not None:
            _reject_crlf(self.from_email, "from_email")
        if self.from_name is not None:
            _reject_crlf(self.from_name, "from_name")
        for k, v in self.headers.items():
            _reject_crlf(k, f"headers[{k}]")
            _reject_crlf(v, f"headers[{k}]")


def build_mime(
    message: EmailMessage,
    *,
    default_from_email: Optional[str],
    default_from_name: str,
    default_reply_to: Optional[str],
    extra_headers: dict[str, str],
) -> MimeMessage:
    """Build a multipart/alternative MIME message with text + HTML parts.

    Caller-supplied message-level fields override the EmailSettings-level
    defaults. extra_headers from settings are merged with per-message headers
    (per-message wins on collision).
    """
    sender = message.from_email or default_from_email
    if not sender:
        raise ValueError("from_email is required (set EMAIL_FROM or message.from_email)")

    sender_name = message.from_name if message.from_name is not None else default_from_name
    # formataddr quotes names with commas, quotes, or special chars per RFC 5322.
    from_header = formataddr((sender_name, sender)) if sender_name else sender

    mime = MimeMessage()
    mime["From"] = from_header
    mime["To"] = message.to
    mime["Subject"] = message.subject
    reply_to = message.reply_to or default_reply_to
    if reply_to:
        mime["Reply-To"] = reply_to

    merged_headers = {**extra_headers, **message.headers}
    for k, v in merged_headers.items():
        if k.lower() in {"from", "to", "subject", "reply-to"}:
            continue
        mime[k] = v

    mime.set_content(message.text_body or "", subtype="plain", charset="utf-8")
    mime.add_alternative(message.html_body or "", subtype="html", charset="utf-8")
    return mime
