"""Allure artifact adapter: Robot + allure listener -> output.xml + allure-results -> report.

Local-only validation. This adapter performs REAL execution and REAL report generation;
it never fabricates an "allure generated" claim. The Allure validation contract
(ARCHITECTURE.md 4.7) requires:

    - `results/allure-results/` presence AND status parity vs the Robot output.
    - a generated Allure report (via `allure generate`).
    - no credential leakage in the generated artifacts.

Status parity: the number of allure `*-result.json` files must equal the Robot test
total parsed from output.xml. Credential leak: scan result + attachment artifacts for
sensitive markers. This is local-only; Jenkins publication is out of scope here.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .robot import RobotRunner

# A conservative set of sensitive markers to detect accidental leakage into Allure
# artifacts (result.json descriptions, steps, attachments). Demo-app credentials are
# public and intentionally excluded so a normal run is not a false positive.
_CREDENTIAL_PATTERNS: List[str] = [
    r"api[_-]?key[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']",
    r"(?:password|passwd|secret|token|credential|client_secret)[\"']?\s*[:=]\s*[\"'][^\"']{6,}[\"']",
    r"Bearer\s+[A-Za-z0-9_\-\.]{16,}",
    r"sk-[A-Za-z0-9]{16,}",
]


@dataclass
class AllureResult:
    exit_code: int
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    result_count: int = 0
    results_present: bool = False
    status_parity: bool = False
    credential_leak: bool = False
    output_xml: Optional[str] = None
    results_dir: Optional[str] = None
    report_dir: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "result_count": self.result_count,
            "results_present": self.results_present,
            "status_parity": self.status_parity,
            "credential_leak": self.credential_leak,
            "output_xml": self.output_xml,
            "results_dir": self.results_dir,
            "report_dir": self.report_dir,
        }


class AllureRunner:
    def __init__(self, results_dir: Path = Path("results")) -> None:
        self.results_dir = results_dir
        self.robot = RobotRunner()

    def run(
        self,
        target: str = "tests",
        allure_dir: Path = Path("results") / "run" / "allure-results",
        output_dir: Path = Path("results") / "run",
        python: str = "python",
        timeout: int = 900,
        clean: bool = True,
    ) -> AllureResult:
        """Run Robot with the allure listener and validate the produced artifacts.

        `clean=True` removes a pre-existing allure-results dir so status parity is
        computed against THIS run only (stale accumulated artifacts must not count).
        """
        if clean:
            if allure_dir.exists():
                for child in allure_dir.iterdir():
                    if child.is_file():
                        child.unlink()
                    else:
                        _rmtree(child)

        cmd = [
            python, "-m", "robot",
            "--outputdir", str(output_dir),
            "--listener", f"allure_robotframework:{_relposix(allure_dir)}",
            target,
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output_xml = output_dir / "output.xml"
        counts = self.robot._parse(output_xml) if output_xml.exists() else {}

        result_files = list(allure_dir.glob("*-result.json")) if allure_dir.exists() else []
        result_count = len(result_files)
        total = counts.get("total", 0)
        results_present = (total > 0) and (result_count > 0)
        status_parity = (total > 0) and (result_count == total)
        credential_leak = self.scan_for_credentials(allure_dir)

        return AllureResult(
            exit_code=proc.returncode,
            total=total,
            passed=counts.get("passed", 0),
            failed=counts.get("failed", 0),
            skipped=counts.get("skipped", 0),
            result_count=result_count,
            results_present=results_present,
            status_parity=status_parity,
            credential_leak=credential_leak,
            output_xml=str(output_xml) if output_xml.exists() else None,
            results_dir=str(allure_dir) if results_present else None,
        )

    def generate(
        self,
        allure_dir: Path = Path("results") / "run" / "allure-results",
        report_dir: Path = Path("results") / "run" / "allure-report",
        allure_bin: str = "allure",
    ) -> Path:
        """Generate (or regenerate) the Allure report from the results directory."""
        launcher = self._resolve_allure_bin(allure_bin)
        cmd = [
            launcher, "generate",
            str(allure_dir),
            "-o", str(report_dir),
            "--clean",
        ]
        # On Windows the allure launcher is a .bat/.cmd shim; run it via cmd /c so
        # subprocess does not fail with FileNotFoundError (CreateProcess cannot exec
        # a batch file directly).
        if os.name == "nt" and launcher.lower().endswith((".bat", ".cmd")):
            cmd = ["cmd", "/c"] + cmd
        proc = subprocess.run(
            cmd, cwd=str(Path.cwd()), capture_output=True, text=True, timeout=300
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Allure generate failed (exit {proc.returncode}): {proc.stderr[-500:]}"
            )
        return report_dir

    def _resolve_allure_bin(self, allure_bin: str) -> str:
        """Resolve the allure launcher path (Windows .bat/.cmd shim aware)."""
        if os.name == "nt" and not Path(allure_bin).suffix:
            for cand in ("allure.bat", "allure.cmd", "allure.exe", "allure"):
                found = shutil.which(cand)
                if found:
                    return found
        resolved = shutil.which(allure_bin)
        if resolved is None:
            raise RuntimeError(f"Allure launcher not found on PATH: {allure_bin!r}")
        return resolved

    def validate(self, res: AllureResult) -> AllureResult:
        """Validate that report generation is consistent with the AllureResult."""
        if res.results_present and res.report_dir is not None:
            index = Path(res.report_dir) / "index.html"
            res.report_dir = str(res.report_dir) if index.exists() else None
        return res

    def scan_for_credentials(self, allure_dir: Path) -> bool:
        """Return True if any Allure artifact contains a sensitive pattern."""
        if not allure_dir.exists():
            return False
        for path in allure_dir.iterdir():
            if path.is_file() and path.suffix in (".json", ".html", ".txt", ".xml", ".png"):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for pattern in _CREDENTIAL_PATTERNS:
                    if re.search(pattern, text, re.IGNORECASE):
                        return True
        return False


def _rmtree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink()
    path.rmdir()


def _relposix(path: Path) -> str:
    """Return `path` relative to cwd in posix form, else its absolute posix form.

    Robot resolves listener dirs relative to its cwd (the project root). A relative
    posix path avoids parsing issues with absolute Windows paths containing a colon.
    """
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()
