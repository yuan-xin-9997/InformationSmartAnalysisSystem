"""Push channel protocol (extensible: email now, more channels later)."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..smtp_config import ResolvedSmtpConfig


@runtime_checkable
class PushChannel(Protocol):
    """A delivery channel that sends one rendered email to recipients."""

    def send(
        self,
        cfg: ResolvedSmtpConfig,
        recipients: list[str],
        subject: str,
        html: str,
        text: str,
    ) -> None: ...
