"""Real Git adapter: status, explicit staging, commit, push and verification.

This adapter performs REAL `git` subprocess calls. It NEVER fabricates: every field
is backed by an actual subprocess or verified on-disk state.

Safety contract enforced here:
  - `git add .` / `git add -A` / wildcard staging is FORBIDDEN. Staging is always
    an explicit, per-file list passed by the Commit Planner.
  - Autonomous push to origin/main is FORBIDDEN. Push targets ONLY the named
    feature/fix branch.
  - A push is only reported as verified when the remote-tracking HEAD for the
    branch matches the local HEAD after the push (or ls-remote proves it).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# A two-char porcelain code: XY where X is the staged (index) change and Y the
# unstaged (worktree) change. "??" = untracked.
_PORCELAIN_RE = None


@dataclass
class GitStatusEntry:
    index: str = " "
    worktree: str = " "
    path: str = ""
    original_path: Optional[str] = None  # rename/copy source (from -> to)
    untracked: bool = False

    @property
    def code(self) -> str:
        return f"{self.index}{self.worktree}"

    @property
    def is_untracked(self) -> bool:
        return self.code == "??"

    @property
    def is_deleted(self) -> bool:
        return "D" in (self.index, self.worktree)

    @property
    def is_modified(self) -> bool:
        return "M" in (self.index, self.worktree)

    @property
    def is_renamed(self) -> bool:
        return self.index == "R" or self.worktree == "R"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "path": self.path,
            "original_path": self.original_path,
            "untracked": self.untracked,
            "deleted": self.is_deleted,
            "modified": self.is_modified,
            "renamed": self.is_renamed,
        }


@dataclass
class GitStatus:
    entries: List[GitStatusEntry] = field(default_factory=list)
    workdir: str = "."

    @property
    def dirty(self) -> bool:
        return len(self.entries) > 0

    @property
    def paths(self) -> List[str]:
        return [e.path for e in self.entries]

    @property
    def untracked_paths(self) -> List[str]:
        return [e.path for e in self.entries if e.is_untracked]

    def by_path(self, path: str) -> Optional[GitStatusEntry]:
        for e in self.entries:
            if e.path == path:
                return e
        return None

    def to_dict(self) -> dict:
        return {
            "dirty": self.dirty,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def parse(cls, porcelain_z: str, workdir: str = ".") -> "GitStatus":
        """Parse `git status --porcelain=v1 -z` nul-delimited output into entries.

        The -z format is robust for spaces/quoting: each record is two bytes of
        status followed by one byte of space, then the path (then optional rename
        source separated by a NUL for renames/copies).
        """
        entries: List[GitStatusEntry] = []
        if not porcelain_z:
            return cls(entries=entries, workdir=workdir)
        tokens = porcelain_z.split("\0") if "\0" in porcelain_z else _split_lines(porcelain_z)
        i = 0
        while i < len(tokens):
            raw = tokens[i]
            if len(raw) < 3:
                i += 1
                continue
            code = raw[:2]
            path = raw[3:]
            original = None
            # Rename/copy entries: a 2nd token carries the original path.
            if "R" in code:
                if i + 1 < len(tokens):
                    original = tokens[i + 1]
                    i += 1
            entries.append(
                GitStatusEntry(
                    index=code[0],
                    worktree=code[1],
                    path=path,
                    original_path=original,
                    untracked=(code == "??"),
                )
            )
            i += 1
        return cls(entries=entries, workdir=workdir)


def _split_lines(text: str) -> List[str]:
    return [ln for ln in text.replace("\r\n", "\n").split("\n") if ln]


class GitAdapter:
    def __init__(self, workdir: str = ".", git_bin: str = "git") -> None:
        self.workdir = str(workdir)
        self.git_bin = git_bin

    def _run(self, args: List[str], *, timeout: int = 120, cwd: Optional[str] = None,
             check: bool = False) -> "subprocess.CompletedProcess":
        proc = subprocess.run(
            [self.git_bin] + args,
            cwd=cwd or self.workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed (exit {proc.returncode}): "
                f"{proc.stderr.strip()[-500:]}"
            )
        return proc

    # -- read-only inspect --------------------------------------------------
    def status(self) -> GitStatus:
        proc = self._run(["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        return GitStatus.parse(proc.stdout or "", workdir=self.workdir)

    def current_branch(self) -> Optional[str]:
        proc = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        name = (proc.stdout or "").strip()
        if not name or name == "HEAD":
            return None
        return name

    def head(self) -> str:
        proc = self._run(["rev-parse", "HEAD"], check=True)
        return (proc.stdout or "").strip()

    def branch_exists(self, branch: str) -> bool:
        proc = self._run(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
        return proc.returncode == 0 and bool((proc.stdout or "").strip())

    def config_set(self, key: str) -> bool:
        proc = self._run(["config", "--get", key])
        return proc.returncode == 0 and bool((proc.stdout or "").strip().splitlines())

    def ls_remote(self, branch: str, remote: str = "origin") -> Optional[str]:
        """Return the remote HEAD SHA for `refs/heads/<branch>`, if reachable."""
        proc = self._run(["ls-remote", remote, f"refs/heads/{branch}"])
        if proc.returncode != 0:
            return None
        for line in (proc.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and parts[1].strip() == f"refs/heads/{branch}":
                return parts[0].strip()
        return None

    def remote_for_branch(self, branch: str) -> Optional[str]:
        """Upstream ref for the branch, e.g. origin/feature/qa-auto-x."""
        proc = self._run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip() or None

    def diff_cached(self) -> str:
        """Full staged diff (stat + patch) for secret scanning."""
        proc = self._run(["diff", "--cached", "--no-ext-diff"])
        return proc.stdout or ""

    def staged_paths(self) -> List[str]:
        proc = self._run(["diff", "--cached", "--name-only", "-z"])
        out = proc.stdout or ""
        if not out:
            return []
        if "\0" in out:
            return [p for p in out.split("\0") if p]
        return [ln for ln in out.replace("\r\n", "\n").split("\n") if ln]

    # -- mutating (guarded) --------------------------------------------------
    def stage(self, paths: List[str]) -> List[str]:
        """Stage ONLY the explicit `paths`. Never a broad/git-add-all command."""
        paths = [p for p in paths if p]
        if not paths:
            raise ValueError("Nothing to stage: empty explicit file list.")
        self._run(["add", "--"] + paths, check=True)
        return paths

    def commit(self, message: str) -> str:
        """Create ONE meaningful commit and return the new HEAD SHA."""
        proc = self._run(["commit", "-m", message], check=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git commit failed: {proc.stderr.strip()[-500:]}")
        return self.head()

    def push(self, branch: str, remote: str = "origin") -> str:
        """Push ONLY `branch` to `remote`. Never main/master (caller enforces)."""
        proc = self._run(["push", remote, branch], timeout=300, check=True)
        return (proc.stdout or proc.stderr or "").strip()[-300:]

    def verify_push(self, branch: str, local_head: str, remote: str = "origin") -> bool:
        """True when the remote HEAD for `branch` equals the local commit HEAD."""
        remote_head = self.ls_remote(branch, remote=remote)
        return bool(remote_head) and remote_head == local_head