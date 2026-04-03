from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime | None = None) -> str:
    current = value or utc_now()
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None) -> object:
    if not value:
        return None
    return json.loads(value)


def generate_session_id() -> str:
    return f"session-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"


def generate_hand_id(session_id: str, hand_no: int, started_at: str) -> str:
    timestamp = started_at.replace("-", "").replace(":", "").replace("T", "").replace("Z", "")
    return f"{timestamp}-{session_id}-h{hand_no:03d}"

