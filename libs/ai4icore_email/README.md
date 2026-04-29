# ai4icore-email

Provider-agnostic transactional email client for AI4ICore services.

The transport is pluggable. Today the default `smtp` provider is configured to use Amazon SES SMTP, but it works with any RFC-compliant SMTP relay (SendGrid SMTP, Mailgun SMTP, Postmark SMTP, your own MTA). Future API-based providers (SendGrid HTTP API, Mailgun HTTP API, etc.) drop in by implementing `EmailProvider` — consumer code does not change.

## Quickstart

```python
from ai4icore_email import (
    EmailClient,
    EmailMessage,
    EmailSettings,
    TemplateRenderer,
    get_email_client,
)

# In a FastAPI service:
async def my_route(client: EmailClient = Depends(get_email_client)):
    msg = EmailMessage(
        to="user@example.com",
        subject="Welcome",
        html_body="<p>Hi</p>",
        text_body="Hi",
    )
    await client.send_safe(msg)
```

## Configuration

| Env var | Notes |
|---|---|
| `EMAIL_PROVIDER` | `smtp` (default) \| `console` \| future `sendgrid_api`, `mailgun_api` |
| `EMAIL_FROM` | Sender. For SES: a verified identity. |
| `EMAIL_FROM_NAME` | Optional friendly name |
| `EMAIL_REPLY_TO` | Optional |
| `EMAIL_EXTRA_HEADERS` | JSON map. For SES Configuration Set: `{"X-SES-CONFIGURATION-SET": "..."}` |
| `SMTP_HOST` | For SES: `email-smtp.<region>.amazonaws.com` |
| `SMTP_PORT` | Default 587 |
| `SMTP_USERNAME` | For SES: SMTP user (NOT IAM access key) |
| `SMTP_PASSWORD` | For SES: SMTP password (NOT IAM secret) |
| `SMTP_USE_TLS` | Default true (STARTTLS). Plaintext is not supported. |
| `ENVIRONMENT` | `development` \| `staging` \| `production`. In dev, missing `SMTP_HOST` auto-falls back to console provider. In staging/production, missing creds raise at startup. |

## Switching providers

- **SES → SendGrid SMTP:** change `SMTP_HOST=smtp.sendgrid.net`, `SMTP_USERNAME=apikey`, `SMTP_PASSWORD=<sendgrid-api-key>`. No code changes.
- **SMTP → SendGrid HTTP API (future):** add `providers/sendgrid_api.py`, register in `providers/factory.py`, set `EMAIL_PROVIDER=sendgrid_api`. No consumer changes.
