"""Immutable, append-only per-run state + transition log (local JSONL event log)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class StateError(RuntimeError):
    """Raised when an invalid state transition is attempted."""


_TERMINAL_STATES = frozenset({
    "COMPLETED", "PR_READY", "CICD_LOCKED", "HEALING_EXHAUSTED",
    "REGRESSION_FAILURE", "BLOCKED",
})


class StateStore:
    """Append-only event log + materialized run state.

    Every transition appends a line to a JSONL file and updates the in-memory state.
    The log is the source of truth for audit and reporting; it is never rewritten.
    """

    def __init__(
        self,
        run_id: str,
        log_path: Optional[Path] = None,
        resumed: bool = False,
    ) -> None:
        self.run_id = run_id
        self._lock = threading.Lock()
        self.resumed = resumed  # True when state was hydrated from a prior run log
        self._state: Dict[str, Any] = {"run_id": run_id, "state": "REQUIREMENT_RECEIVED"}
        self._log_path = log_path or self._log_path_for(run_id)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # -- persistence ------------------------------------------------------
    def _append(self, event: Dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    # -- state access -----------------------------------------------------
    def current_state(self) -> str:
        return self._state["state"]

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    # -- transitions ------------------------------------------------------
    def transition(self, new_state: str, allowed: bool = False, **evidence: Any) -> None:
        """Record a state transition, appending evidence.

        `allowed` is True when the calling code has already validated the transition
        against the stage/edge table. This keeps the kernel's machine as the single
        authority; callers pass `allowed=...` only after the StageRegistry verifies the
        edge exists.
        """
        with self._lock:
            old = self._state["state"]
            if old in _TERMINAL_STATES or not allowed:
                raise StateError(
                    f"Disallowed transition: {old} -> {new_state}"
                )
            self._state["state"] = new_state
            if evidence:
                self._state.update(evidence)
            self._append(
                {
                    "type": "transition",
                    "from": old,
                    "to": new_state,
                    "evidence_keys": list(evidence.keys()),
                }
            )
            if evidence:
                self._append(
                    {"type": "evidence", "run_id": self.run_id, "evidence": evidence}
                )

    def record(self, key: str, value: Any, *, expose_evidence: bool = True) -> None:
        """Record non-transition state (a stage output) without changing stage."""
        with self._lock:
            self._state[key] = value
            self._append(
                {
                    "type": "record",
                    "key": key,
                    "value": value if expose_evidence else "<redacted>",
                }
            )

    # -- resume -----------------------------------------------------------
    @classmethod
    def resume(cls, run_id: str, log_path: Optional[Path] = None) -> "StateStore":
        """Hydrate a StateStore by replaying the append-only JSONL run log.

        This is the ONLY way to continue a previously started run without
        restarting from REQUIREMENT_RECEIVED. The log is never mutated;
        it is read-only and produces the exact materialized state snapshot.

        Returns a new StateStore whose in-memory state reflects the last
        recorded transition + evidence. `store.resumed` is True.

        If the run_id has no log file, a fresh (un-resumed) store is returned
        instead of failing, so callers never need to check first.
        """
        log = cls._log_path_for(run_id, log_path)
        store = cls(run_id, log_path=log, resumed=False)
        if not log.exists():
            return store
        state: Dict[str, Any] = {"run_id": run_id, "state": "REQUIREMENT_RECEIVED"}
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            typ = ev.get("type")
            if typ == "transition":
                state["state"] = ev["to"]
            elif typ == "evidence":
                state.update(ev.get("evidence") or {})
            elif typ == "record":
                state[ev["key"]] = ev.get("value")
        with store._lock:
            store._state = state
            store.resumed = True
        return store

    @staticmethod
    def _log_path_for(run_id: str, base: Optional[Path] = None) -> Path:
        base = base or Path("results") / "orchestra"
        if base.suffix.lower() == ".jsonl":
            base.parent.mkdir(parents=True, exist_ok=True)
            return base
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{run_id}.jsonl"


def next_run_id(results_dir: Path = Path("results")) -> str:
    """Produce a monotonically increasing run id (archive-safe)."""
    os.makedirs(results_dir, exist_ok=True)
    seq = 0
    log_dir = Path(results_dir) / "orchestra"
    log_dir.mkdir(parents=True, exist_ok=True)
    for p in log_dir.glob("orchestra-run-*.jsonl"):
        try:
            n = int(p.stem.rsplit("-", 1)[-1])
            seq = max(seq, n)
        except ValueError:
            continue
    while (log_dir / f"orchestra-run-{seq + 1:04d}.jsonl").exists():
        seq += 1
    return f"orchestra-run-{seq + 1:04d}"
