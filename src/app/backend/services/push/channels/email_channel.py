"""Email push channel: sends mail via stdlib ``smtplib`` + ``email.mime``.

No third-party dependency. The channel takes a resolved SMTP config plus a
rendered subject/HTML/text and performs the actual delivery.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ....core.logging import get_logger
from ..smtp_config import ResolvedSmtpConfig

_logger = get_logger("push.email")

_SMTP_TIMEOUT = 30


class EmailChannel:
    """Send one email (HTML + plain-text alternative) to one or more recipients."""

    def send(
        self,
        cfg: ResolvedSmtpConfig,
        recipients: list[str],
        subject: str,
        html: str,
        text: str,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        if cfg.from_name:
            msg["From"] = f"{cfg.from_name} <{cfg.from_email}>"
        else:
            msg["From"] = cfg.from_email
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        if cfg.use_ssl:
            smtp = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=_SMTP_TIMEOUT)
        else:
            smtp = smtplib.SMTP(cfg.host, cfg.port, timeout=_SMTP_TIMEOUT)
        try:
            smtp.ehlo()
            if cfg.use_tls and not cfg.use_ssl:
                smtp.starttls()
                smtp.ehlo()
            if cfg.username:
                smtp.login(cfg.username, cfg.password)
            smtp.sendmail(cfg.from_email, list(recipients), msg.as_string())
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
