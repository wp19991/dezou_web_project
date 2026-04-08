from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BOT_NAMES = ("阿岚", "老岩", "唐梨", "温策", "小顾")


def parse_bot_names(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return DEFAULT_BOT_NAMES

    names = tuple(item.strip() for item in raw_value.split(","))
    if len(names) != 5:
        raise ValueError("POKER_BOT_NAMES 必须提供 5 个名字")
    if any(not item for item in names):
        raise ValueError("POKER_BOT_NAMES 不能包含空名字")
    if len(set(names)) != len(names):
        raise ValueError("POKER_BOT_NAMES 里的名字必须唯一")
    if any(not (1 <= len(item) <= 32) for item in names):
        raise ValueError("POKER_BOT_NAMES 里的每个名字长度必须在 1 到 32 之间")
    return names


@dataclass(slots=True)
class Settings:
    project_root: Path
    db_path: Path
    db_url: str
    schema_path: Path
    service_name: str = "poker-table"
    poll_interval_ms: int = 1000
    bot_names: tuple[str, ...] = DEFAULT_BOT_NAMES

    @classmethod
    def load(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[2]
        raw_db_path = Path(os.getenv("POKER_DB_PATH", project_root / "poker_table.db"))
        db_path = raw_db_path if raw_db_path.is_absolute() else project_root / raw_db_path
        schema_path = project_root / "poker_table_sqlite_schema.sql"
        db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
        bot_names = parse_bot_names(os.getenv("POKER_BOT_NAMES"))

        return cls(
            project_root=project_root,
            db_path=db_path,
            db_url=db_url,
            schema_path=schema_path,
            bot_names=bot_names,
        )
