"""SMTP email service.

Generic SMTP — works with Resend, Postmark, AWS SES, Gmail, Mailgun, etc.
Configure via the SMTP_* env vars; the from-address is `digest_from_email`.

Provider quick reference (set in .env):

  Resend     SMTP_HOST=smtp.resend.com       PORT=465  USER=resend     PASS=<api-key>
  Postmark   SMTP_HOST=smtp.postmarkapp.com  PORT=587  USER=<token>    PASS=<token>
  AWS SES    SMTP_HOST=email-smtp.us-east-1.amazonaws.com PORT=587 USER=<key> PASS=<secret>
  Gmail      SMTP_HOST=smtp.gmail.com        PORT=465  USER=<address>  PASS=<app-pw>
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Sequence

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def send_email(
    *,
    to: str | Sequence[str],
    subject: str,
    html: str,
    text: str | None = None,
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """Send a multipart text+html email. Returns the Message-Id."""
    if isinstance(to, str):
        recipients = [to]
    else:
        recipients = list(to)
    if not recipients:
        raise ValueError("send_email: at least one recipient is required")

    msg = EmailMessage()
    msg["From"] = formataddr((settings.digest_from_name, settings.digest_from_email))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Reply-To"] = reply_to or settings.digest_reply_to or settings.digest_from_email
    msg_id = make_msgid(domain=settings.digest_from_email.split("@", 1)[-1] or "ai2wj.com")
    msg["Message-Id"] = msg_id
    if headers:
        for k, v in headers.items():
            msg[k] = v

    msg.set_content(text or _html_to_text(html))
    msg.add_alternative(html, subtype="html")

    log.info(
        "sending email",
        host=settings.smtp_host,
        port=settings.smtp_port,
        to=recipients,
        subject=subject,
    )

    if settings.smtp_use_tls and settings.smtp_port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg, from_addr=settings.digest_from_email, to_addrs=recipients)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg, from_addr=settings.digest_from_email, to_addrs=recipients)

    return msg_id


def _html_to_text(html: str) -> str:
    """Cheap fallback for the text/plain part. Keeps links visible."""
    import re
    s = re.sub(r"<a[^>]*href=\"([^\"]+)\"[^>]*>([^<]*)</a>", r"\2 (\1)", html, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
