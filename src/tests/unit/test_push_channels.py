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


def test_email_channel_send_with_attachments(monkeypatch):
    import smtplib

    from app.backend.services.push.attachments import Attachment
    from app.backend.services.push.channels.email_channel import EmailChannel
    from app.backend.services.push.smtp_config import ResolvedSmtpConfig

    sent: dict = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, frm, to, msg):
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = ResolvedSmtpConfig(
        host="h", port=25, use_tls=False, use_ssl=False, username="", password="",
        from_email="f@x.com", from_name="", source="page",
    )
    atts = [Attachment(filename="r.pdf", mime="application/pdf", data=b"%PDF-1.4 fake")]
    EmailChannel().send(cfg, ["a@x.com"], "主题", "<b>html</b>", "text", attachments=atts)
    assert "multipart/mixed" in sent["msg"]
    assert "attachment" in sent["msg"]
    assert "r.pdf" in sent["msg"]


def test_email_channel_send_with_inline_images(monkeypatch):
    """有内联图：multipart/related 包裹 alternative + 内联图（Content-ID / inline）。"""
    import smtplib
    from email import message_from_string

    from app.backend.services.push.attachments import InlineImage
    from app.backend.services.push.channels.email_channel import EmailChannel
    from app.backend.services.push.smtp_config import ResolvedSmtpConfig

    sent: dict = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, frm, to, msg):
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = ResolvedSmtpConfig(
        host="h", port=25, use_tls=False, use_ssl=False, username="", password="",
        from_email="f@x.com", from_name="", source="page",
    )
    inlines = [
        InlineImage(cid="fig-1-0@isas", filename="f0.png", mime="image/png", data=b"\x89PNG", item_id=1),
    ]
    EmailChannel().send(
        cfg, ["a@x.com"], "主题", '<img src="cid:fig-1-0@isas" />', "text",
        inline_images=inlines,
    )
    m = message_from_string(sent["msg"])
    # 顶层 multipart/related
    assert m.is_multipart()
    assert m.get_content_type() == "multipart/related"
    # related 的子部分：alternative + inline image
    payloads = m.get_payload()
    assert any(p.get_content_type() == "multipart/alternative" for p in payloads)
    inline_parts = [p for p in payloads if p.get_content_type() == "image/png"]
    assert len(inline_parts) == 1
    assert inline_parts[0]["Content-ID"] == "<fig-1-0@isas>"
    assert "inline" in inline_parts[0]["Content-Disposition"]


def test_email_channel_send_with_inline_and_attachments(monkeypatch):
    """内联图 + 附件：multipart/mixed > related(alternative + inline) + attachments。"""
    import smtplib
    from email import message_from_string

    from app.backend.services.push.attachments import Attachment, InlineImage
    from app.backend.services.push.channels.email_channel import EmailChannel
    from app.backend.services.push.smtp_config import ResolvedSmtpConfig

    sent: dict = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, frm, to, msg):
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = ResolvedSmtpConfig(
        host="h", port=25, use_tls=False, use_ssl=False, username="", password="",
        from_email="f@x.com", from_name="", source="page",
    )
    inlines = [
        InlineImage(cid="fig-1-0@isas", filename="f0.png", mime="image/png", data=b"\x89PNG", item_id=1),
    ]
    atts = [Attachment(filename="r.pdf", mime="application/pdf", data=b"%PDF-1.4")]
    EmailChannel().send(
        cfg, ["a@x.com"], "主题", '<img src="cid:fig-1-0@isas" />', "text",
        attachments=atts, inline_images=inlines,
    )
    m = message_from_string(sent["msg"])
    assert m.get_content_type() == "multipart/mixed"
    children = m.get_payload()
    # related + attachment
    assert any(p.get_content_type() == "multipart/related" for p in children)
    assert any(p.get_content_type() == "application/pdf" for p in children)
    # related -> alternative + inline
    related = next(p for p in children if p.get_content_type() == "multipart/related")
    rel_children = related.get_payload()
    assert any(p.get_content_type() == "multipart/alternative" for p in rel_children)
    assert any(p.get_content_type() == "image/png" for p in rel_children)


def test_email_channel_send_no_inline_no_attachments_backward_compat(monkeypatch):
    """无内联无附件：multipart/alternative（向后兼容）。"""
    import smtplib
    from email import message_from_string

    from app.backend.services.push.channels.email_channel import EmailChannel
    from app.backend.services.push.smtp_config import ResolvedSmtpConfig

    sent: dict = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, frm, to, msg):
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = ResolvedSmtpConfig(
        host="h", port=25, use_tls=False, use_ssl=False, username="", password="",
        from_email="f@x.com", from_name="", source="page",
    )
    EmailChannel().send(cfg, ["a@x.com"], "主题", "<b>html</b>", "text")
    m = message_from_string(sent["msg"])
    assert m.get_content_type() == "multipart/alternative"
