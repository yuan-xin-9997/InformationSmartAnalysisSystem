"""Push endpoints.

SMTP config (GET/PUT/test) is implemented here; push-rule CRUD, manual trigger
and push history are added in a later task.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..core.secrets import mask_value
from ..models.push import get_smtp_config_row
from ..models.user import User
from ..schemas.push import SmtpConfigIn, SmtpConfigOut, TestEmailRequest
from ..services.push.channels.email_channel import EmailChannel
from ..services.push.smtp_config import SmtpConfigError, resolve_smtp_config

router = APIRouter(prefix="/api/push", tags=["推送"])


def _to_out(cfg) -> SmtpConfigOut:
    pwd = mask_value(cfg.password) if cfg.password else ""
    return SmtpConfigOut(
        host=cfg.host,
        port=cfg.port,
        use_tls=cfg.use_tls,
        use_ssl=cfg.use_ssl,
        username=cfg.username,
        from_email=cfg.from_email,
        from_name=cfg.from_name,
        password=pwd,
    )


@router.get("/smtp", response_model=SmtpConfigOut)
def get_smtp(
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> SmtpConfigOut:
    cfg = get_smtp_config_row(db)
    return _to_out(cfg)


@router.put("/smtp", response_model=SmtpConfigOut)
def put_smtp(
    req: SmtpConfigIn,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> SmtpConfigOut:
    cfg = get_smtp_config_row(db)
    cfg.host = req.host
    cfg.port = req.port
    cfg.use_tls = req.use_tls
    cfg.use_ssl = req.use_ssl
    cfg.username = req.username
    if req.password:  # 空表示保留旧密码
        cfg.password = req.password
    cfg.from_email = req.from_email
    cfg.from_name = req.from_name
    db.commit()
    db.refresh(cfg)
    return _to_out(cfg)


@router.post("/smtp/test")
def test_smtp(
    req: TestEmailRequest,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        cfg = resolve_smtp_config(db)
    except SmtpConfigError as e:
        return {"ok": False, "error": str(e)}
    try:
        EmailChannel().send(
            cfg,
            [req.to_email],
            "【信息分析】SMTP 测试邮件",
            "<p>这是一封来自信息智能分析系统的 SMTP 测试邮件。</p>",
            "这是一封来自信息智能分析系统的 SMTP 测试邮件。",
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "error": None}
