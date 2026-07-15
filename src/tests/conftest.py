"""Shared pytest fixtures.

Environment variables for an isolated temp DB / data / logs / password file are
set at import time (before any `app.backend.*` import), so the module-level
`settings` singleton picks them up.
"""
from __future__ import annotations

import os
import pathlib
import tempfile

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="isas_test_"))

os.environ.setdefault("ISAS_AUTH_SECRET_KEY", "test-secret")
os.environ.setdefault("ISAS_LLM_BASE_URL", "http://mock-llm")
os.environ.setdefault("ISAS_LLM_API_KEY", "mock-key")
os.environ.setdefault("ISAS_WEB_FETCH_BASE_URL", "http://mock-webfetch")
os.environ.setdefault("ISAS_WEB_FETCH_API_KEY", "mock-wf-key")
os.environ["ISAS_DB_PATH"] = str(_TMP / "test.sqlite3")
os.environ["ISAS_LOG_DIR"] = str(_TMP / "logs")
os.environ["ISAS_DATA_DIR"] = str(_TMP / "data")
_PW = _TMP / "password.txt"
os.environ["ISAS_PASSWORD_FILE"] = str(_PW)
_PW.write_text(
    "# comment\nadmin:admin123:admin\ntester:tester123:user\n", encoding="utf-8"
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    """A FastAPI TestClient backed by a freshly-reset SQLite database."""
    from app.backend import models  # noqa: F401  (register ORM models)
    from app.backend.core.database import Base, engine
    from app.backend.main import app

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_token(client) -> str:
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def sync_worker(monkeypatch):
    """Make the background worker run jobs synchronously in the calling thread."""
    import app.backend.services.worker as worker

    def _submit(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, "submit", _submit)


@pytest.fixture
def mock_llm(monkeypatch):
    """Replace the LLM client with a deterministic mock; returns the call list."""
    import app.backend.services.analysis.engine as engine

    calls: list[str] = []

    class _MockLLM:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, system: str, user: str) -> str:
            calls.append(user)
            return f"[分析] {user[:15]}"

    monkeypatch.setattr(engine, "LLMClient", _MockLLM)
    return calls
