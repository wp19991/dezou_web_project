from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    root = ROOT
    artifacts = root / ".test_artifacts"
    artifacts.mkdir(exist_ok=True)
    db_path = artifacts / f"pytest-{uuid4().hex}.db"
    settings = Settings(
        project_root=root,
        db_path=db_path,
        db_url=f"sqlite+pysqlite:///{db_path.as_posix()}",
        schema_path=root / "poker_table_sqlite_schema.sql",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    app.state.poker_service.store.engine.dispose()
    db_path.unlink(missing_ok=True)
