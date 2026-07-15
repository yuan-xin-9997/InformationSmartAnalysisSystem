"""System-config endpoint: read-only display of app.json (secrets masked)."""
from __future__ import annotations

import sys

from fastapi import APIRouter, Depends

from ..core.config import settings
from ..core.deps import require_page
from ..core.runtime import get_started_at
from ..core.secrets import mask_sensitive
from ..core.timeutil import format_beijing
from ..models.user import User
from ..schemas.config import ConfigResponse, RuntimeInfo

router = APIRouter(prefix="/api/config", tags=["系统配置"])


@router.get("", response_model=ConfigResponse)
def get_config(_: User = Depends(require_page("system_config"))) -> ConfigResponse:
    runtime = RuntimeInfo(
        started_at=format_beijing(get_started_at()),
        pid=_safe_pid(),
        version="0.1.0",
        host=settings.server_host,
        port=settings.server_port,
        db_path=str(settings.database_path),
        log_dir=str(settings.log_dir),
        data_dir=str(settings.data_dir),
        python_version=sys.version.split()[0],
    )
    import copy

    return ConfigResponse(config=mask_sensitive(copy.deepcopy(settings.raw)), runtime=runtime)


def _safe_pid() -> int:
    import os

    return os.getpid()
