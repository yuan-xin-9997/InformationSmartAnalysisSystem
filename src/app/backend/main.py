"""FastAPI application entry point.

Run from the ``src`` directory::

    uvicorn app.backend.main:app --host 0.0.0.0 --port 28080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import analysis_tasks as analysis_tasks_api
from .api import auth as auth_api
from .api import config_view as config_api
from .api import info_sources as info_sources_api
from .api import task_center as task_center_api
from .api import users as users_api
from .core.config import PROJECT_ROOT, settings
from .core.database import SessionLocal, init_db
from .core.logging import cleanup_old_logs, get_logger, setup_logging
from .core.runtime import set_started_at
from .core.security import sync_users_from_password_file
from .core.timeutil import utcnow
from .services import worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logging()
    cleanup_old_logs()
    set_started_at(utcnow())
    logger.info("启动信息智能分析系统 (InformationSmartAnalysisSystem)")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "downloads").mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("数据库初始化完成: %s", settings.database_path)
    # Sync users from password.txt (file may not exist yet on first deploy ->
    # sync tolerates a missing file and is a no-op).
    with SessionLocal() as db:
        sync_users_from_password_file(db)
    yield
    worker.shutdown()
    logger.info("信息智能分析系统已停止")


app = FastAPI(title="信息智能分析系统", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router)
app.include_router(users_api.router)
app.include_router(config_api.router)
app.include_router(task_center_api.router)
app.include_router(info_sources_api.router)
app.include_router(analysis_tasks_api.router)
app.include_router(analysis_tasks_api.results_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check (used by start/status scripts and monitoring)."""
    return {"status": "ok"}


# Serve the built frontend (SPA) when present. The frontend ``dist`` is produced
# by the start scripts (npm run build). API routes registered above take
# precedence; any other GET falls back to index.html for client-side routing.
_frontend_dist = PROJECT_ROOT / "app" / "frontend" / "dist"
if _frontend_dist.exists():
    _index_html = _frontend_dist / "index.html"
    app.mount(
        "/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets"
    )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_index_html))
