from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router
from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.db.database import create_sqlite_engine, initialize_schema
from app.engine.table_kernel import TableKernel
from app.repositories.store import Store
from app.services.poker_service import PokerService
from app.services.runtime_registry import RuntimeRegistry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    logging.basicConfig(level=logging.INFO)

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(settings.db_url)
    initialize_schema(engine, settings.schema_path)

    app = FastAPI(title="Poker Table API", version="1.0.0")
    app.state.settings = settings
    app.state.templates = Jinja2Templates(
        directory=str(settings.project_root / "app" / "templates")
    )
    app.state.poker_service = PokerService(
        settings=settings,
        store=Store(engine),
        registry=RuntimeRegistry(),
        kernel=TableKernel(),
    )

    register_exception_handlers(app)
    app.include_router(router)
    app.mount(
        "/static",
        StaticFiles(directory=str(settings.project_root / "app" / "static")),
        name="static",
    )
    return app


app = create_app()
