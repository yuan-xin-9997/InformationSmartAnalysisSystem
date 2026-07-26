"""SMTP configuration resolver.

Page config (the ``smtp_config`` DB row) takes priority over the ``email``
section in ``config/app.json``; when both are missing the minimum required
fields (host + from_email) a :class:`SmtpConfigError` is raised so callers can
surface a clear message instead of failing silently.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...core.config import settings
from ...models.push import get_smtp_config_row


class SmtpConfigError(RuntimeError):
    """Raised when SMTP config is insufficient to send mail."""


@dataclass
class ResolvedSmtpConfig:
    """Effective SMTP settings after layering (page > app.json)."""

    host: str
    port: int
    use_tls: bool
    use_ssl: bool
    username: str
    password: str
    from_email: str
    from_name: str
    source: str  # "page" | "app.json"


def resolve_smtp_config(db: Session) -> ResolvedSmtpConfig:
    """页面 SMTP 配置优先；页面 host 为空时回退 app.json；两处皆缺则抛异常。"""
    cfg = get_smtp_config_row(db)
    if cfg.host:
        src = "page"
        host, port = cfg.host, cfg.port
        use_tls, use_ssl = cfg.use_tls, cfg.use_ssl
        username, password = cfg.username, cfg.password
        from_email, from_name = cfg.from_email, cfg.from_name
    elif settings.email_smtp_host:
        src = "app.json"
        host, port = settings.email_smtp_host, settings.email_smtp_port
        use_tls, use_ssl = settings.email_use_tls, settings.email_use_ssl
        username, password = settings.email_username, settings.email_password
        from_email, from_name = settings.email_from_email, settings.email_from_name
    else:
        raise SmtpConfigError(
            "SMTP 未配置：请在推送管理页或 config/app.json 的 email 段配置 SMTP 主机与发件人"
        )
    if not from_email:
        raise SmtpConfigError(f"SMTP 发件人未配置（来源：{src}），请补全 from_email")
    return ResolvedSmtpConfig(
        host=host,
        port=port,
        use_tls=use_tls,
        use_ssl=use_ssl,
        username=username,
        password=password,
        from_email=from_email,
        from_name=from_name,
        source=src,
    )
