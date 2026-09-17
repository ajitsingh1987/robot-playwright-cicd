"""Actual Agent CLI adapter: invokes real opencode agents via `opencode run`.

This is the delegation boundary. The kernel shells out to
    opencode run --agent <name> --format json <message>
for cognitive sub-stages (planner, playwright, generator, healer, reviewer,
failure-analysis). It captures the JSON event stream, extracts the final text result
(the agent's structured verdict/evidence), and records the session id as evidence.

The adapter NEVER fabricates: outcome is derived from the actual subprocess + artifacts
produced by the agent as recorded in `artifacts` paths (verified on disk).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..config import settings

# Agent names registered in .opencode/agents/ as selectable via `opencode run --agent`.
AGENT_NAMES = {
    "planner",
    "playwright",
    "generator",
    "healer",
    "reviewer",
    "reporter",
    "failure-analysis",
    "cicd",
}


@dataclass
class AgentResult:
    agent: str
    exit_code: int
    session_id: Optional[str] = None
    text: str = ""                 # concatenated text parts from the JSON stream
    raw_json: str = ""             # full JSON event stream (for audit)
    artifacts: List[str] = field(default_factory=list)  # files written, verified on disk

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "exit_code": self.exit_code,
            "session_id": self.session_id,
            "text": self.text,
            "artifacts": self.artifacts,
        }


class AgentCLI:
    """Shells out to the opencode CLI to run a registered agent.

    A depth guard prevents recursive agent dispatch: the kernel runs agents at
    depth 1, and any agent that tries to re-dispatch another agent recursively is
    rejected, breaking a potential agent->agent->agent infinite loop.
    """

    def __init__(self, opencode: Optional[str] = None, workdir: str = ".",
                 max_depth: int = None) -> None:
        self.opencode = opencode or self._resolve_opencode()
        self.workdir = workdir
        self.max_depth = max_depth if max_depth is not None else settings.MAX_AGENT_DEPTH

    @staticmethod
    def _resolve_opencode() -> str:
        """Resolve the opencode executable.

        On Windows the `opencode` entry point is often a PowerShell shim (.ps1) that
        Python's subprocess cannot execute directly. Prefer the npm-installed .exe and
        verify it exists; fall back to the bare command name.
        """
        import os

        bn = os.environ.get("APPDATA", "")
        if bn:
            exe = (
                Path(bn)
                / "npm"
                / "node_modules"
                / "opencode-ai"
                / "bin"
                / "opencode.exe"
            )
            if exe.exists():
                return str(exe)
        return "opencode"


    def run_agent(
        self,
        agent: str,
        message: str,
        *,
        timeout: int = None,
        depth: int = 1,
        output_file: Optional[Path] = None,
    ) -> AgentResult:
        if agent not in AGENT_NAMES:
            raise ValueError(f"Unknown agent: {agent}; expected one of {sorted(AGENT_NAMES)}")
        if depth > self.max_depth:
            raise RecursionError(
                f"Agent dispatch depth {depth} exceeds MAX_AGENT_DEPTH={self.max_depth}; "
                f"refusing recursive agent->agent dispatch of '{agent}'."
            )
        if timeout is None:
            timeout = settings.AGENT_TIMEOUT_SECONDS

        cmd = [self.opencode, "run", "--agent", agent, "--format", "json", message]
        proc = subprocess.run(
            cmd,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        raw = proc.stdout or ""
        session_id = self._extract_session_id(raw)
        text = self._extract_text(raw)

        # If an output file was requested, persist the raw JSON stream as evidence.
        if output_file is not None:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(raw, encoding="utf-8")
            artifacts = [str(output_file)]
        else:
            artifacts = []

        return AgentResult(
            agent=agent,
            exit_code=proc.returncode,
            session_id=session_id,
            text=text,
            raw_json=raw,
            artifacts=artifacts,
        )

    @staticmethod
    def _extract_session_id(raw: str) -> Optional[str]:
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            sid = ev.get("sessionID") or (
                ev.get("part", {}) or {}
            ).get("sessionID")
            if sid:
                return str(sid)
        return None

    @staticmethod
    def _extract_text(raw: str) -> str:
        """Concatenate top-level `text` events (agent narrative / verdict)."""
        parts = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if ev.get("type") == "text":
                txt = (ev.get("part", {}) or {}).get("text", "")
                parts.append(txt)
        return "\n".join(parts)
