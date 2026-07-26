"""PushRule / PushRun / SmtpConfig model tests."""
from __future__ import annotations

from app.backend.core.database import SessionLocal
from app.backend.models.push import PushRule, PushRun, SmtpConfig, get_smtp_config_row


def test_push_rule_defaults_and_json(client):
    with SessionLocal() as db:
        rule = PushRule(
            name="r1",
            task_ids=[1, 2],
            event_types=["per_item", "aggregate"],
            recipients=["a@example.com"],
            trigger_mode="on_run",
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        assert rule.channel == "email"
        assert rule.enabled is True
        assert rule.last_pushed_result_id is None
        assert rule.max_events_per_email == 50
        assert rule.task_ids == [1, 2]
        assert rule.event_types == ["per_item", "aggregate"]
        assert rule.recipients == ["a@example.com"]
        assert rule.created_at is not None


def test_push_run_cascade_on_rule_delete(client):
    with SessionLocal() as db:
        rule = PushRule(
            name="r2",
            task_ids=[1],
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="manual",
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        db.add(
            PushRun(
                rule_id=rule.id,
                trigger_mode="manual",
                recipients=["a@x.com"],
                event_count=0,
                status="no_new",
            )
        )
        db.commit()
        rid = rule.id
        db.delete(rule)
        db.commit()
        assert db.query(PushRun).filter(PushRun.rule_id == rid).count() == 0


def test_smtp_config_singleton_roundtrip(client):
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        cfg.host = "smtp.example.com"
        cfg.port = 587
        cfg.use_tls = True
        cfg.username = "u"
        cfg.password = "secret"
        cfg.from_email = "n@x.com"
        db.commit()
        first_id = cfg.id
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        assert cfg.id == first_id  # 单行：再次获取是同一行
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 587
        assert cfg.use_tls is True
        assert cfg.password == "secret"
        assert cfg.from_email == "n@x.com"
