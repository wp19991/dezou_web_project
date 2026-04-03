from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeRegistry:
    runtimes: dict[str, Any] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self.locks:
            self.locks[session_id] = asyncio.Lock()
        return self.locks[session_id]

    def get_runtime(self, session_id: str) -> Any | None:
        return self.runtimes.get(session_id)

    def set_runtime(self, session_id: str, runtime: Any) -> None:
        self.runtimes[session_id] = runtime

    def clear_runtime(self, session_id: str) -> None:
        self.runtimes.pop(session_id, None)
