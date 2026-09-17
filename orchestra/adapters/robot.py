"""Robot Framework execution adapter with robust result parsing."""
from __future__ import annotations

import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import settings


def _classify_status(exit_code: int) -> str:
    """Map a Robot Framework process exit code to a stable status string.

    Robot returns 0 on a fully clean pass, non-zero on any failure.
    """
    if exit_code == 0:
        return "PASS"
    if exit_code == 252:
        return "INTERRUPTED"
    return "FAIL"


@dataclass
class RobotResult:
    exit_code: int
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    unresolved: int = 0
    output_xml: Optional[str] = None
    duration_seconds: float = 0.0
    status: str = "UNKNOWN"
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "unresolved": self.unresolved,
            "output_xml": self.output_xml,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
        }

    def is_clean(self) -> bool:
        return self.failed == 0 and self.skipped == 0 and self.unresolved == 0


class RobotRunner:
    FULL_REG_SUITE = settings.TEST_SUITE

    def run(
        self,
        target: str,
        results_dir: Path = None,
        allure_dir: Optional[Path] = None,
        python: str = "python",
        timeout: int = None,
    ) -> RobotResult:
        results_dir = results_dir or settings.RESULTS_DIR
        if timeout is None:
            timeout = settings.ROBOT_TIMEOUT_SECONDS
        cmd = [python, "-m", "robot", "--outputdir", str(results_dir)]
        if allure_dir is not None:
            cmd += ["--listener", f"allure_robotframework:{allure_dir}"]
        cmd += [target]
        start = time.monotonic()
        proc = subprocess.run(
            cmd,
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.monotonic() - start
        output_xml = results_dir / "output.xml"
        counts = self._parse(output_xml) if output_xml.exists() else {}
        exit_code = proc.returncode
        return RobotResult(
            exit_code=exit_code,
            output_xml=str(output_xml) if output_xml.exists() else None,
            duration_seconds=round(duration, 3),
            status=_classify_status(exit_code),
            stdout=(proc.stdout or ""),
            stderr=(proc.stderr or ""),
            **counts,
        )

    @staticmethod
    def _parse(output_xml: Path) -> dict:
        """Parse a Robot Framework output.xml total-statistics block.

        Robot output.xml is XML, not YAML. The root is `<robot>` with
        `<statistics><total><stat pass fail skip>`. This parser reads the aggregate
        `<stat>` attributes directly, so a real execution vs the sacred baseline are
        read identically. Any malformed/missing output is treated as unavailable ({}).
        """
        try:
            root = ET.parse(output_xml).getroot()
            total = root.find("statistics/total")
            if total is None:
                return {}
            # Robot 5+ emits a single top-level <stat pass fail skip> under <total>.
            stats = [s for s in total if s.tag == "stat"]
            if not stats:
                return {}
            stat = stats[0].attrib
            passed = int(stat.get("pass", 0) or 0)
            failed = int(stat.get("fail", 0) or 0)
            skipped = int(stat.get("skip", 0) or 0)
        except Exception:
            return {}

        return {
            # Robot omits the "passed" key name here; it is "pass" in output.xml.
            "total": passed + failed + skipped,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            # Robot Framework reports individual test outcomes; there is no aggregate
            # "unresolved" counter separate from failed. Keep unresolved=0 so the clean
            # gate (0/0/0) is never distorted by a fabricated count.
            "unresolved": 0,
        }
