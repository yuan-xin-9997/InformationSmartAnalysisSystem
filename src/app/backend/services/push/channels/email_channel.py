"""Email push channel: sends mail via stdlib ``smtplib`` + ``email.mime``.

No third-party dependency. The channel takes a resolved SMTP config plus a
rendered subject/HTML/text and performs the actual delivery. Optional
``attachments`` (``multipart/mixed``) and ``inline_images`` (``multipart/related``
with ``Content-ID`` for CID-embedded charts in the HTML body) are supported.

MIME structure:
- no media:                 ``multipart/alternative`` (text + html)
- attachments only:         ``multipart/mixed`` > alternative + attachments
- inline images (no atts):  ``multipart/related`` > alternative + inline parts
- inline + attachments:     ``multipart/mixed`` > related(alternative + inline) + attachments
"""
from __future__ import annotations

import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ....core.logging import get_logger
from ..attachments import Attachment, InlineImage
from ..smtp_config import ResolvedSmtpConfig

_logger = get_logger("push.email")

_SMTP_TIMEOUT = 30


class EmailChannel:
    """Send one email (HTML + plain-text alternative, optional inline/attachments)."""

    def _alt_part(self, html: str, text: str) -> MIMEMultipart:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html", "utf-8"))
        return alt

    def _inline_part(self, img: InlineImage) -> MIMEBase:
        maintype, _, subtype = (img.mime or "image/png").partition("/")
        part = MIMEBase(maintype or "image", subtype or "png")
        part.set_payload(img.data)
        encoders.encode_base64(part)
        part.add_header("Content-ID", f"<{img.cid}>")
        part.add_header("Content-Disposition", "inline", filename=img.filename)
        return part

    def _attachment_part(self, a: Attachment) -> MIMEBase:
        maintype, _, subtype = (a.mime or "application/octet-stream").partition("/")
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(a.data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=a.filename)
        return part

    def send(
        self,
        cfg: ResolvedSmtpConfig,
        recipients: list[str],
        subject: str,
        html: str,
        text: str,
        attachments: list | None = None,
        inline_images: list | None = None,
    ) -> None:
        inline_images = inline_images or []
        attachments = attachments or []
        alt = self._alt_part(html, text)

        if inline_images:
            related = MIMEMultipart("related")
            related.attach(alt)
            for img in inline_images:
                related.attach(self._inline_part(img))
            if attachments:
                msg = MIMEMultipart("mixed")
                msg.attach(related)
                for a in attachments:
                    msg.attach(self._attachment_part(a))
            else:
                msg = related
        elif attachments:
            msg = MIMEMultipart("mixed")
            msg.attach(alt)
            for a in attachments:
                msg.attach(self._attachment_part(a))
        else:
            msg = alt

        msg["Subject"] = subject
        if cfg.from_name:
            msg["From"] = f"{cfg.from_name} <{cfg.from_email}>"
        else:
            msg["From"] = cfg.from_email
        msg["To"] = ", ".join(recipients)

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
