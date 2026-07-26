"""Push schemas.

SMTP config schemas here; push-rule and push-run schemas are added alongside
the rule API in a later task.
"""
from __future__ import annotations

from pydantic import BaseModel


class SmtpConfigOut(BaseModel):
    host: str
    port: int
    use_tls: bool
    use_ssl: bool
    username: str
    from_email: str
    from_name: str
    password: str  # 脱敏后的展示值


class SmtpConfigIn(BaseModel):
    host: str = ""
    port: int = 25
    use_tls: bool = False
    use_ssl: bool = False
    username: str = ""
    password: str = ""  # 空表示保留旧密码（避免前端回传脱敏值覆盖）
    from_email: str = ""
    from_name: str = "信息智能分析系统"


class TestEmailRequest(BaseModel):
    to_email: str
