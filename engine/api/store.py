"""In-memory context store: idempotent by (scope, context_id, version), higher
version replaces atomically (challenge-testing-brief.md §2.1)."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class StoredContext:
    version: int
    payload: dict[str, Any]


class ContextStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[tuple[str, str], StoredContext] = {}

    def push(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> tuple[bool, Optional[int]]:
        """Returns (accepted, current_version_if_rejected)."""
        key = (scope, context_id)
        with self._lock:
            cur = self._data.get(key)
            if cur is not None and cur.version >= version:
                return False, cur.version
            self._data[key] = StoredContext(version=version, payload=payload)
            return True, None

    def get(self, scope: str, context_id: str) -> Optional[dict[str, Any]]:
        cur = self._data.get((scope, context_id))
        return cur.payload if cur else None

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _cid) in self._data:
            out[scope] = out.get(scope, 0) + 1
        return out

    def all_of_scope(self, scope: str) -> dict[str, dict[str, Any]]:
        return {cid: v.payload for (s, cid), v in self._data.items() if s == scope}

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
