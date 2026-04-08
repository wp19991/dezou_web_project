from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, text


def create_sqlite_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)


def initialize_schema(engine: Engine, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        raw.executescript(sql)
        raw.commit()
    finally:
        raw.close()
    _apply_compat_migrations(engine)


def _apply_compat_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        session_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        }
        if "rng_seed" not in session_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE sessions
                    ADD COLUMN rng_seed INTEGER NOT NULL DEFAULT 0
                    """
                )
            )
        if "user_participates" not in session_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE sessions
                    ADD COLUMN user_participates INTEGER NOT NULL DEFAULT 0
                    """
                )
            )
