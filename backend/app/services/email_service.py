import logging
from email.message import EmailMessage
import aiosmtplib
import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
        and settings.SMTP_FROM_EMAIL
    )


async def send_email(to_email: str, subject: str, body: str, *, idempotency_key: str | None = None) -> dict:
    """Send via the selected provider and report provider acceptance (not inbox delivery)."""
    provider = settings.EMAIL_PROVIDER.strip().lower()
    if provider == "resend":
        if not settings.RESEND_API_KEY or not settings.RESEND_FROM_EMAIL:
            raise RuntimeError("Resend is not configured; set RESEND_API_KEY and RESEND_FROM_EMAIL")
        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers=headers,
                    json={
                        "from": settings.RESEND_FROM_EMAIL,
                        "to": [to_email],
                        "subject": subject,
                        "text": body,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.error("Resend API request failed error=%s", type(exc).__name__)
            raise
        return {
            "provider": "resend",
            "status": "accepted_by_provider",
            "message_id": payload.get("id"),
        }
    if provider != "smtp":
        raise RuntimeError("EMAIL_PROVIDER must be either 'smtp' or 'resend'")

    if not is_smtp_configured():
        missing = [name for name, value in (
            ("SMTP_HOST", settings.SMTP_HOST), ("SMTP_USERNAME", settings.SMTP_USERNAME),
            ("SMTP_PASSWORD", settings.SMTP_PASSWORD), ("SMTP_FROM_EMAIL", settings.SMTP_FROM_EMAIL),
        ) if not value]
        raise RuntimeError("SMTP is not configured; missing " + ", ".join(missing))

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message, hostname=settings.SMTP_HOST, port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME, password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS, timeout=15,
        )
    except Exception as exc:
        logger.error("SMTP delivery failed host=%s error=%s", settings.SMTP_HOST, type(exc).__name__)
        raise
    return {"provider": "smtp", "status": "accepted_by_smtp", "message_id": None}
