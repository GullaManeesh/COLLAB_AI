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
    """Send an email via configured SMTP server.
    
    If SMTP credentials are not configured, logs a clear warning without raising an error,
    allowing the invitation workflow to continue.
    """
    if not is_smtp_configured():
        logger.warning(
            "SMTP email settings are incomplete. Required environment variables: "
            "SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL. "
            "In-app invitation notification was created, but email delivery is skipped."
        )
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        start_tls=settings.SMTP_USE_TLS,
        timeout=15,
    )
    return True
