from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    project_root: Path
    db_path: Path
    db_url: str
    schema_path: Path
    service_name: str = "poker-table"
    poll_interval_ms: int = 1000

    @classmethod
    def load(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[2]
        raw_db_path = Path(os.getenv("POKER_DB_PATH", project_root / "poker_table.db"))
        db_path = raw_db_path if raw_db_path.is_absolute() else project_root / raw_db_path
        schema_path = project_root / "poker_table_sqlite_schema.sql"
        db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

        return cls(
            project_root=project_root,
            db_path=db_path,
            db_url=db_url,
            schema_path=schema_path,
        )

