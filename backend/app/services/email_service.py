import logging
from email.message import EmailMessage
import aiosmtplib

from app.config.settings import settings

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
        and settings.SMTP_FROM_EMAIL
    )


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an email through SMTP; a true result means SMTP accepted the message."""
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
        logger.error("SMTP delivery failed host=%s recipient=%s error=%s", settings.SMTP_HOST, to_email, type(exc).__name__)
        raise
    return True
