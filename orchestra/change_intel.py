"""Change Intelligence: deterministic classification of working-tree changes.

Takes the real `git status` output from the Git adapter and classifies every
entry into exactly one category:

  - OWNED:          path belongs to the current requirement's AUTOMATION_CHANGESET.
  - SHARED_SUPPORT: shared page/resource/variable/data file imported (transitively)
                    by the requirement's owned suite(s) AND modified — staged only
                    when the requirement's suites actually depend on it.
  - UNRELATED:      a change that is not part of this requirement. NEVER staged, and
                    its presence BLOCKS an autonomous commit (the ledger must be clean
                    or the plan must explicitly surface it).
  - EXCLUDED:       generated/transient artifact (results/, allure-report/, .venv,
                    node_modules, __pycache__, evidence/, temp). Never committed.

Classification is derived from real on-disk + git evidence only: the working-tree
status and the requirement-to-test-file ownership map. Nothing is inferred from a
file name alone unless that name is part of the declared automation changeset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .dependency import RequirementOwnership
from .config import settings

# Paths that are always generated/transient and must never enter a commit.
EXCLUDED_PREFIXES: tuple = (
    "results/",
    "results\\",
    "allure-report/",
    "allure-results/",
    ".venv/",
    ".venv\\",
    "node_modules/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "evidence/",
    ".opencode/sessions/",
)
_EXCLUDED_SUFFIXES: tuple = (".pyc", ".log", ".tmp", ".cache", ".local")
_EXCLUDED_EXACT: frozenset = frozenset({".DS_Store", "Thumbs.db", ".env.local"})


def classify_excluded(path: str) -> bool:
    """True when `path` is a generated/transient artifact that never belongs in a commit."""
    norm = path.replace("\\", "/")
    if norm in _EXCLUDED_EXACT:
        return True
    for prefix in EXCLUDED_PREFIXES:
        if norm.startswith(prefix):
            return True
    if any(norm.endswith(sfx) for sfx in _EXCLUDED_SUFFIXES):
        return True
    return False


@dataclass
class ChangeEntry:
    path: str
    code: str
    category: str                    # OWNED | SHARED_SUPPORT | UNRELATED | EXCLUDED
    reason: str
    original_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "code": self.code,
            "category": self.category,
            "reason": self.reason,
            "original_path": self.original_path,
        }


@dataclass
class ChangeReport:
    requirement: str
    entries: List[ChangeEntry] = field(default_factory=list)
    owned: List[str] = field(default_factory=list)
    shared_support: List[str] = field(default_factory=list)
    unrelated: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True when there are NO unrelated changes that would be auto-committed.

        Excluded/transient artifacts are fine; accidentally sweeping another
        requirement's files into this commit is not.
        """
        return not self.unrelated

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "clean": self.clean,
            "owned": list(self.owned),
            "shared_support": list(self.shared_support),
            "unrelated": list(self.unrelated),
            "excluded": list(self.excluded),
            "entries": [e.to_dict() for e in self.entries],
        }


class ChangeClassifier:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or settings.PROJECT_ROOT
        self.ownership = RequirementOwnership(self.root)

    def _is_shared_support(self, path: str) -> bool:
        norm = path.replace("\\", "/")
        return (
            norm.startswith("pages/")
            or norm.startswith("pages\\")
            or norm.startswith("resources/")
            or norm.startswith("resources\\")
            or norm.startswith("variables/")
            or norm.startswith("variables\\")
            or norm.startswith("data/")
            or norm.startswith("data\\")
        )

    def classifier(self, requirement: str) -> "ChangeClassifier":
        return self

    def classify(
        self,
        status_entries,
        changeset: Optional[List[str]] = None,
        requirement: Optional[str] = None,
    ) -> ChangeReport:
        """Classify real `GitStatus.entries` against the requirement's changeset.

        `changeset` is the declared AUTOMATION_CHANGESET (intended files). A path
        in the changeset is OWNED. A modified SHARED p/r/v file is OWNED only if
        explicitly declared in the changeset (the requirement owns its dependency
        decision), otherwise it is classified as SHARED_SUPPORT when at least one
        owned suite imports it, and UNRELATED otherwise.
        """
        owned_set: Set[str] = {Path(p).as_posix() for p in (changeset or [])}
        report = ChangeReport(requirement=requirement or "")

        # Determine the requirement's owned suites for shared-support resolution.
        owned_suites: Set[Path] = set()
        for p in owned_set:
            cand = Path(p)
            if cand.suffix == ".robot" and cand.parent.name == "tests":
                owned_suites.add(cand.resolve() if cand.is_absolute() else (self.root / p).resolve())

        imported_by_owned: Set[Path] = set()
        for suite in owned_suites:
            try:
                imported_by_owned.update(self.ownership._imports_of_suite(suite))
            except OSError:
                # Unreadable owned suite -> can NOT prove the shared file is
                # required; the conservative decision is to leave it un-imported
                # (UNRELATED), which blocks the commit. Never guess the dependency.
                continue

        for entry in status_entries:
            path = entry.path or ""
            posix = path.replace("\\", "/")
            if classify_excluded(path):
                report.entries.append(
                    ChangeEntry(path, entry.code, "EXCLUDED", "generated/transient artifact")
                )
                report.excluded.append(path)
                continue

            if posix in owned_set:
                report.entries.append(
                    ChangeEntry(path, entry.code, "OWNED", "declared automation changeset")
                )
                report.owned.append(path)
                continue

            if self._is_shared_support(path):
                resolved = (self.root / posix).resolve()
                if resolved in imported_by_owned:
                    report.entries.append(
                        ChangeEntry(
                            path,
                            entry.code,
                            "SHARED_SUPPORT",
                            "shared support imported by the requirement's suites",
                            entry.original_path,
                        )
                    )
                    report.shared_support.append(path)
                else:
                    report.entries.append(
                        ChangeEntry(
                            path,
                            entry.code,
                            "UNRELATED",
                            "shared file not imported by this requirement (pre-existing work)",
                            entry.original_path,
                        )
                    )
                    report.unrelated.append(path)
                continue

            report.entries.append(
                ChangeEntry(
                    path,
                    entry.code,
                    "UNRELATED",
                    "not part of this requirement",
                    entry.original_path,
                )
            )
            report.unrelated.append(path)

        return report


def build_changeset(
    requirement: str,
    test_file: Optional[str] = None,
    page_objects: Optional[List[str]] = None,
    resources: Optional[List[str]] = None,
    variables: Optional[List[str]] = None,
    data_files: Optional[List[str]] = None,
) -> List[str]:
    """Compose the intended AUTOMATION_CHANGESET file list from declared artifacts."""
    changeset: List[str] = []
    if test_file:
        changeset.append(test_file)
    changeset.extend(page_objects or [])
    changeset.extend(resources or [])
    changeset.extend(variables or [])
    changeset.extend(data_files or [])
    return changeset