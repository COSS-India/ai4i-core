import os

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from dotenv import load_dotenv

load_dotenv()


def test_sendgrid_api_key(
    api_key: str | None = None,
    to_email: str | None = None,
    from_email: str | None = None,
) -> None:
    """
    Simple helper to validate that the SendGrid API key works.

    - Reads values from arguments, then environment variables:
      - SENDGRID_API_KEY
      - SENDGRID_TEST_TO_EMAIL
      - SENDGRID_TEST_FROM_EMAIL
    - Sends a minimal test email and prints the status code.
    """
    api_key = api_key or os.getenv("SENDGRID_API_KEY")
    # Print masked key for debugging (avoid dumping full key)
    if api_key:
        print("API KEY ---------------->", api_key[:8] + "..." if len(api_key) > 8 else "***set***")
    else:
        print("API KEY ----------------> None")
    to_email = to_email or os.getenv("SENDGRID_TEST_TO_EMAIL","gangulyambarish1373@gmail.com")
    from_email = from_email or os.getenv("SENDGRID_TEST_FROM_EMAIL","ambarish.ganguly@tarento.com")

    if not api_key:
        raise ValueError("SendGrid API key not provided. Set SENDGRID_API_KEY or pass api_key.")
    if not to_email:
        raise ValueError("Test recipient email not provided. Set SENDGRID_TEST_TO_EMAIL or pass to_email.")
    if not from_email:
        raise ValueError("Test sender email not provided. Set SENDGRID_TEST_FROM_EMAIL or pass from_email.")

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject="SendGrid API key test from multi-tenant-feature",
        plain_text_content="If you received this email, your SendGrid API key is working.",
    )

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        print(f"SendGrid test email sent. Status code: {response.status_code}")
        if response.status_code >= 400:
            print(f"Response body: {response.body}")
    except Exception as exc:  # noqa: BLE001
        body = getattr(exc, "body", None)
        print(f"Error sending SendGrid test email: {exc}")
        if body:
            print(f"SendGrid error body: {body}")
        raise


if __name__ == "__main__":
    test_sendgrid_api_key()


