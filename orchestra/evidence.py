"""EvidenceBus: capture and validate evidence artifacts for gates/reporting.

A claim ("test passed", "allure generated", "docker ran") is only meaningful when an
artifact is recorded and, where required, verified to actually exist on disk. This
module prevents fabrication: no artifact, no PASS.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import StateStore


class EvidenceBus:
    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._items: List[Dict[str, Any]] = []

    def add(self, key: str, value: Any, *, kind: str = "artifact") -> None:
        item = {"key": key, "kind": kind, "value": value}
        self._items.append(item)
        self._store.record(f"evidence.{key}", value)

    def existing(self, paths: List[str]) -> Dict[str, bool]:
        """Check which path artifacts actually exist on disk (fabrication guard)."""
        result: Dict[str, bool] = {}
        for p in paths:
            result[p] = Path(p).exists()
        return result

    def require_exists(self, paths: List[str], what: str) -> Optional[RuntimeError]:
        missing = [p for p, ok in self.existing(paths).items() if not ok]
        if missing:
            return RuntimeError(f"{what}: missing artifact(s): {missing}")
        return None

    def items(self) -> List[Dict[str, Any]]:
        return list(self._items)
