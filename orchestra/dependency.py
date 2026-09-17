"""Deterministic file-based impact analysis for Robot Framework suites.

Maps changed artifacts (a changed resource, page object, variable, or data file)
to the test suites that (transitively) import them, and enforces the project's
ONE REQUIREMENT -> ONE TEST FILE ownership rule so a changed shared component
never silently drops a requirement's suite out of regression scope.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set

from .config import settings

# A consumable line like `Resource    ../pages/orangehrm_login_page.robot`
# or `Variables    ../variables/urls.py` or `Library    Browser`.
_IMPORT_RE = re.compile(r"^\s*(Resource|Variables)\s+([\w./\\-]+\.(?:robot|resource|py))", re.I)
_SUITE_RE = re.compile(r"^.*?\.robot$", re.I)


class RequirementOwnership:
    """Discovers the requirement->test-file ownership map from the repo.

    Each test file under `tests/` owns its requirement (AGENTS.md rule 5). A
    shared page/resource/variable may be imported by several suites; a changed
    shared artifact therefore affects every importing owner.
    """

    def __init__(self, root: Path = None) -> None:
        self.root = root or settings.PROJECT_ROOT
        self.test_dir = self.root / "tests"
        self.page_dir = self.root / "pages"
        self.resource_dir = self.root / "resources"
        self.variable_dir = self.root / "variables"
        self.data_dir = self.root / "data"

    def owner_suites(self) -> List[Path]:
        """Every requirement-owned suite under tests/ (sorted, stable order)."""
        if not self.test_dir.exists():
            return []
        return sorted(p for p in self.test_dir.glob("*.robot"))

    def _imports_of_suite(self, suite: Path) -> Set[Path]:
        """All page/resource/variable files a suite imports (resolved to real paths)."""
        dirs = [self.page_dir, self.resource_dir, self.variable_dir, self.data_dir]
        imported: Set[Path] = set()
        for line in suite.read_text(encoding="utf-8").splitlines():
            m = _IMPORT_RE.match(line)
            if not m:
                continue
            raw = m.group(2).replace("\\", "/")
            for d in dirs:
                cand = (d / Path(raw).name).resolve()
                if cand.exists():
                    imported.add(cand)
                    break
        return imported

    def _build_reverse_map(self) -> Dict[Path, Set[Path]]:
        """Reverse import map: artifact path -> every file (suite/page/resource)
        that imports it, built from the whole project's import statements."""
        reverse: Dict[Path, Set[Path]] = {}
        sources = self.owner_suites()
        # Page/resource files can themselves import other page/resource files.
        sources += [
            p for p in (self.page_dir.glob("*.robot") if self.page_dir.exists() else [])
        ]
        sources += [
            p for p in (self.resource_dir.glob("*.resource") if self.resource_dir.exists() else [])
        ]
        for src in sources:
            for imported in self._imports_of_suite(src):
                reverse.setdefault(imported, set()).add(src)
        return reverse

    def suites_importing(self, changed: Path) -> List[Path]:
        """Return the owner suites that (transitively) import `changed`.

        A changed artifact is any file - a page object, a shared resource, a
        variable set, a data module, or even another suite (own requirement).
        Changed X affects exactly the set of suites that become reachable from X via
        the reverse-import graph (suites importing X, plus suites importing -- or
        pages importing, which suites then import -- anything that imports X).
        If the path is a test suite itself, it is its own owner.
        """
        changed = changed.resolve()
        if changed.name.endswith(".robot") and changed.parent == self.test_dir:
            return [changed]

        reverse = self._build_reverse_map()
        seen: Set[Path] = set()
        frontier = [changed]
        affected: Set[Path] = set()
        while frontier:
            node = frontier.pop()
            if node in seen:
                continue
            seen.add(node)
            for importer in reverse.get(node, set()):
                if importer in seen:
                    continue
                affected.add(importer)
                frontier.append(importer)
        owners = sorted(
            {p for p in affected if p.parent == self.test_dir and p.suffix == ".robot"}
        )
        return owners


class FileImpactAnalyzer:
    """Resolve the affected owner suites for a set of changed artifacts.

    Safety: if a changed file maps to NO owner suite (unknown/unowned artifact)
    or the mapping is ambiguous, fall back to ALL owner suites so no requirement
    silently loses coverage (mirrors ScopeEngine's FULL_REGRESSION safety net).
    """

    def __init__(self, root: Path = None) -> None:
        self.owners = RequirementOwnership(root)

    def affected_suites(self, changed_files: List[Path], *, strict: bool = False) -> List[Path]:
        owned = self.owners.owner_suites()
        if not changed_files:
            return owned  # no evidence -> full regression (rule mirrors scope.py)
        affected: Set[Path] = set()
        for cf in changed_files:
            p = Path(cf)
            if not p.exists() and not p.is_absolute():
                p = settings.PROJECT_ROOT / p
            if not p.exists():
                return owned
            if p.resolve().parent in {
                self.owners.resource_dir.resolve(),
                self.owners.variable_dir.resolve(),
                self.owners.data_dir.resolve(),
            }:
                return owned
            hit = self.owners.suites_importing(p)
            if not hit:
                # Changed artifact maps to NO requirement-owned suite: safety -> full.
                if strict:
                    return owned
                affected |= set(owned)
            else:
                affected |= set(hit)
        result = sorted(affected)
        return result


def build_impact_metadata(changed_files: List[Path]) -> Dict:
    """Produce the deterministic impact evidence block for changed artifacts."""
    analyzer = FileImpactAnalyzer()
    suites = analyzer.affected_suites(changed_files)
    return {
        "changed_artifacts": [str(p) for p in changed_files],
        "affected_suites": [str(p) for p in suites],
        "impact_type": "TARGETED" if 0 < len(suites) <= 3 else "FULL_REGRESSION",
    }