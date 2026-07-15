"""Logging setup.

- Daily rotation: today's log is ``logs/app.log``; rotated files are named
  ``logs/app.YYYY-MM-DD.log`` (CLAUDE.md log layout).
- Log record timestamps are rendered in Beijing time (CLAUDE.md 规范2).
- Old logs beyond ``retention_days`` are purged at startup.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from .config import settings
from .timeutil import to_beijing


class BeijingFormatter(logging.Formatter):
    """Render record timestamps in Beijing time."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        dt = to_beijing(dt)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def _rotated_namer(name: str) -> str:
    """TimedRotatingFileHandler rotates ``app.log`` -> ``app.log.YYYY-MM-DD``.

    Rename to the CLAUDE.md layout ``app.YYYY-MM-DD.log``.
    """
    directory, filename = os.path.split(name)
    prefix = "app.log."
    if filename.startswith(prefix):
        suffix = filename[len(prefix):]
        return os.path.join(directory, f"app.{suffix}.log")
    return name


def cleanup_old_logs() -> None:
    """Delete ``app.*.log`` files older than ``retention_days``."""
    cutoff = time.time() - settings.log_retention_days * 86400
    if not settings.log_dir.exists():
        return
    for f in settings.log_dir.glob("app.*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def setup_logging() -> logging.Logger:
    """Configure and return the application logger."""
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("isas")
    logger.setLevel(settings.log_level)
    logger.propagate = False
    if logger.handlers:  # avoid duplicate handlers on reload
        return logger

    fmt = BeijingFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    file_handler = TimedRotatingFileHandler(
        settings.log_dir / "app.log",
        when="midnight",
        backupCount=settings.log_retention_days,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.namer = _rotated_namer
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)
    return logger


def get_logger(name: str = "isas") -> logging.Logger:
    return logging.getLogger(name)
