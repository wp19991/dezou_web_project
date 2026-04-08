from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from app.core.config import DEFAULT_BOT_NAMES, Settings
from app.db.database import create_sqlite_engine, initialize_schema

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".test_artifacts"
ARTIFACTS.mkdir(exist_ok=True)


def test_settings_load_reads_custom_bot_names(monkeypatch) -> None:
    monkeypatch.setenv("POKER_BOT_NAMES", "甲,乙,丙,丁,戊")

    settings = Settings.load()

    assert settings.bot_names == ("甲", "乙", "丙", "丁", "戊")


def test_index_embeds_default_bot_name_pool(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    for name in DEFAULT_BOT_NAMES:
        assert name in response.text


def test_initialize_schema_adds_user_participates_for_legacy_sessions_table() -> None:
    db_path = ARTIFACTS / f"legacy-{uuid4().hex}.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            seat_count INTEGER NOT NULL,
            small_blind INTEGER NOT NULL,
            big_blind INTEGER NOT NULL,
            starting_stack INTEGER NOT NULL,
            phase TEXT NOT NULL,
            current_hand_id TEXT NULL,
            next_dealer_seat INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        INSERT INTO sessions (
            session_id, seat_count, small_blind, big_blind, starting_stack,
            phase, current_hand_id, next_dealer_seat, created_at, updated_at
        ) VALUES (
            'legacy-table', 3, 50, 100, 5000,
            'waiting_start', NULL, 0, '2026-04-04T00:00:00Z', '2026-04-04T00:00:00Z'
        );
        """
    )
    raw.commit()
    raw.close()

    engine = create_sqlite_engine(f"sqlite+pysqlite:///{db_path.as_posix()}")
    initialize_schema(engine, ROOT / "poker_table_sqlite_schema.sql")

    try:
        with engine.connect() as conn:
            columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
            }
            row = conn.execute(
                text(
                    """
                    SELECT rng_seed, user_participates
                    FROM sessions
                    WHERE session_id = 'legacy-table'
                    """
                )
            ).mappings().first()
        assert "rng_seed" in columns
        assert "user_participates" in columns
        assert row is not None
        assert row["rng_seed"] == 0
        assert row["user_participates"] == 0
    finally:
        engine.dispose()
        db_path.unlink(missing_ok=True)
