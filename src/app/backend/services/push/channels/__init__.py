"""Push channel registry.

Maps a rule's ``channel`` field to a channel implementation. Adding a new
channel = add a class and register it here; push rules and trigger logic stay
unchanged.
"""
from __future__ import annotations

from .base import PushChannel
from .email_channel import EmailChannel

CHANNELS: dict[str, PushChannel] = {
    "email": EmailChannel(),
}


def get_channel(name: str) -> PushChannel | None:
    """Return the channel implementation for ``name``, or None if unknown."""
    return CHANNELS.get(name)
