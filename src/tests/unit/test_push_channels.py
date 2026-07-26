"""Push channel registry + EmailChannel.send tests."""
from __future__ import annotations


def test_registry_has_email_channel():
    from app.backend.services.push.channels import CHANNELS, get_channel
    from app.backend.services.push.channels.email_channel import EmailChannel

    assert "email" in CHANNELS
    assert isinstance(get_channel("email"), EmailChannel)
    assert get_channel("unknown") is None


def test_email_channel_send_uses_smtp(monkeypatch):
    import smtplib

    from app.backend.services.push.channels.email_channel import EmailChannel
    from app.backend.services.push.smtp_config import ResolvedSmtpConfig

    sent: dict = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def ehlo(self):
            pass

        def starttls(self):
            sent["starttls"] = True

        def login(self, u, p):
            sent["login"] = (u, p)

        def sendmail(self, frm, to, msg):
            sent["from"] = frm
            sent["to"] = to
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = ResolvedSmtpConfig(
        host="h",
        port=25,
        use_tls=True,
        use_ssl=False,
        username="u",
        password="p",
        from_email="f@x.com",
        from_name="机器人",
        source="page",
    )
    EmailChannel().send(cfg, ["a@x.com"], "主题", "<b>html</b>", "text")
    assert sent["host"] == "h"
    assert sent["starttls"] is True
    assert sent["login"] == ("u", "p")
    assert sent["from"] == "f@x.com"
    assert sent["to"] == ["a@x.com"]
    # 主题/发件人名(中文)经 MIME 编码，校验结构而非字面值
    assert "Subject:" in sent["msg"]
    assert "From:" in sent["msg"]
    assert "multipart/alternative" in sent["msg"]
