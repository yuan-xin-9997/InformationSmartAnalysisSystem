"""Push endpoints: SMTP config + push rules (CRUD, manual trigger, history)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..core.secrets import mask_value
from ..models.push import PushRule, PushRun, get_smtp_config_row
from ..models.user import User
from ..schemas.push import (
    PushRuleCreate,
    PushRuleOut,
    PushRuleUpdate,
    PushRunOut,
    SmtpConfigIn,
    SmtpConfigOut,
    TestEmailRequest,
)
from ..services import worker
from ..services.push.channels.email_channel import EmailChannel
from ..services.push.push_scheduler import (
    add_push_job,
    remove_push_job,
    reschedule_push_job,
)
from ..services.push.service import run_push
from ..services.push.smtp_config import SmtpConfigError, resolve_smtp_config

router = APIRouter(prefix="/api/push", tags=["推送"])


def _validate_rule(trigger_mode: str, cron_expr: str | None, interval_seconds: int | None) -> None:
    if trigger_mode not in ("on_run", "scheduled", "manual"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trigger_mode 取值: on_run|scheduled|manual",
        )
    if trigger_mode == "scheduled":
        if not cron_expr and not (interval_seconds and interval_seconds > 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scheduled 模式必须填写 cron_expr 或大于 0 的 interval_seconds",
            )


# ---------- SMTP config ----------


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


# ---------- Push rules ----------


@router.get("/rules", response_model=list[PushRuleOut])
def list_rules(
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> list[PushRule]:
    return db.scalars(select(PushRule).order_by(PushRule.id.desc())).all()


@router.post("/rules", response_model=PushRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    req: PushRuleCreate,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> PushRule:
    _validate_rule(req.trigger_mode, req.cron_expr, req.interval_seconds)
    rule = PushRule(
        name=req.name,
        channel=req.channel,
        task_ids=req.task_ids,
        event_types=req.event_types,
        recipients=req.recipients,
        trigger_mode=req.trigger_mode,
        cron_expr=req.cron_expr,
        interval_seconds=req.interval_seconds,
        enabled=req.enabled,
        max_events_per_email=req.max_events_per_email,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    if rule.enabled and rule.trigger_mode == "scheduled":
        add_push_job(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=PushRuleOut)
def update_rule(
    rule_id: int,
    req: PushRuleUpdate,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> PushRule:
    rule = db.get(PushRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推送规则不存在")
    if req.name is not None:
        rule.name = req.name
    if req.channel is not None:
        rule.channel = req.channel
    if req.task_ids is not None:
        rule.task_ids = req.task_ids
    if req.event_types is not None:
        rule.event_types = req.event_types
    if req.recipients is not None:
        rule.recipients = req.recipients
    if req.trigger_mode is not None:
        rule.trigger_mode = req.trigger_mode
    if req.cron_expr is not None:
        rule.cron_expr = req.cron_expr
    if req.interval_seconds is not None:
        rule.interval_seconds = req.interval_seconds
    if req.enabled is not None:
        rule.enabled = req.enabled
    if req.max_events_per_email is not None:
        rule.max_events_per_email = req.max_events_per_email
    _validate_rule(rule.trigger_mode, rule.cron_expr, rule.interval_seconds)
    db.commit()
    db.refresh(rule)
    reschedule_push_job(rule)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> dict:
    rule = db.get(PushRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推送规则不存在")
    remove_push_job(rule_id)
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/rules/{rule_id}/trigger")
def trigger_rule(
    rule_id: int,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> dict:
    rule = db.get(PushRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推送规则不存在")
    worker.submit(run_push, rule_id, "manual")
    return {"ok": True}


@router.get("/rules/{rule_id}/runs", response_model=list[PushRunOut])
def list_runs(
    rule_id: int,
    _: User = Depends(require_page("push_management")),
    db: Session = Depends(get_db),
) -> list[PushRun]:
    return (
        db.scalars(
            select(PushRun).where(PushRun.rule_id == rule_id).order_by(PushRun.id.desc())
        ).all()
    )
