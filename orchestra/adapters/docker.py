"""Real Docker validation adapter: build the image, run the suite in a container.

This adapter performs REAL `docker build` + `docker run`. It NEVER treats CLI
availability as a pass. The Docker gate may only pass when:

    - the image build succeeded,
    - a container actually ran (run exit captured),
    - Robot executed INSIDE the container and produced an output.xml,
    - the parsed Robot result is clean (0 / 0 / 0),
    - the output artifact exists on disk and is newer than before the run.

Every field exposed on DockerResult is backed by a real subprocess or on-disk artifact.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..config import settings

try:  # subprocess.run(..., timeout=) is only used when exec support is available
    import subprocess
except Exception:  # pragma: no cover
    subprocess = None  # type: ignore


@dataclass
class DockerEvidence:
    built: bool = False
    ran: bool = False
    build_exit_code: Optional[int] = None
    image_id: Optional[str] = None
    container_id: Optional[str] = None
    run_exit_code: Optional[int] = None
    output_xml: Optional[str] = None
    output_xml_before: Optional[float] = None
    output_xml_after: Optional[float] = None
    allure_results_count: int = 0
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    artifacts: List[str] = field(default_factory=list)

    @property
    def output_xml_exists(self) -> bool:
        return bool(self.output_xml) and Path(self.output_xml).exists()

    @property
    def evidence_log_touched(self) -> bool:
        """True when output.xml exists and its mtime is newer than before the run."""
        if not self.output_xml_exists:
            return False
        after = self.output_xml_after or Path(self.output_xml).stat().st_mtime
        if self.output_xml_before is None:
            return True
        return after > self.output_xml_before

    @property
    def clean(self) -> bool:
        return self.failed == 0 and self.skipped == 0

    def to_dict(self) -> dict:
        return {
            "built": self.built,
            "ran": self.ran,
            "build_exit_code": self.build_exit_code,
            "image_id": self.image_id,
            "container_id": self.container_id,
            "run_exit_code": self.run_exit_code,
            "output_xml": self.output_xml,
            "output_xml_exists": self.output_xml_exists,
            "evidence_log_touched": self.evidence_log_touched,
            "allure_results_count": self.allure_results_count,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "artifacts": self.artifacts,
        }


class DockerRunner:
    def __init__(self, docker_bin: str = "docker", workdir: str = ".") -> None:
        self.docker_bin = docker_bin
        self.workdir = workdir

    def _run(self, args: List[str], timeout: int = None) -> "subprocess.CompletedProcess":
        if timeout is None:
            timeout = settings.DOCKER_TIMEOUT_SECONDS
        return subprocess.run(
            [self.docker_bin] + args,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def _image_id(self, image: str) -> Optional[str]:
        try:
            proc = self._run(["image", "inspect", "--format", "{{.Id}}", image], timeout=120)
        except Exception:
            return None
        return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None

    def run(
        self,
        image: str = "qa-orchestrator",
        tag: str = "latest",
        context: str = ".",
        target: str = "tests",
        results_dir: Path = Path("results"),
        allure_dir: Optional[Path] = Path("results") / "run" / "allure-results",
        mount_dest: str = "/app/results",
        workdir_container: str = "/app",
        cmd_inside: Optional[str] = None,
        timeout: int = None,
    ) -> DockerEvidence:
        """Build the image and run Robot inside a container, collecting evidence.

        By default it mirrors the Jenkins contract exactly: `docker run --rm -v
        <results>:/app/results <image>` using the image's DEFAULT CMD (which executes
        `python -m robot --outputdir results --listener allure_robotframework:results/
        allure-results tests`). If `cmd_inside` is provided it is run via bash -lc
        inside the container instead.
        """
        if subprocess is None:  # pragma: no cover
            raise RuntimeError("subprocess unavailable; Docker validation cannot run.")

        full_image = f"{image}:{tag}"
        results_dir = Path(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        if allure_dir is not None:
            Path(allure_dir).mkdir(parents=True, exist_ok=True)

        evidence = DockerEvidence()
        out_xml = results_dir / "run" / "output.xml"
        evidence.output_xml_before = out_xml.stat().st_mtime if out_xml.exists() else None

        # 1. Build (mirrors Jenkins `docker build -t %IMAGE_NAME% .`)
        build = self._run(["build", "-t", full_image, context], timeout=timeout)
        evidence.built = build.returncode == 0
        evidence.build_exit_code = build.returncode
        if not evidence.built:
            return evidence
        evidence.image_id = self._image_id(full_image)

        # 2. Run the suite in a container via the image default CMD (Jenkins contract),
        #    or via an explicit override command when provided.
        mount_arg = f"{results_dir.resolve()}:{mount_dest}"
        if cmd_inside is not None:
            run_args = ["run", "--rm", "-v", mount_arg, "-w", workdir_container,
                        full_image, "bash", "-lc", cmd_inside]
        else:
            run_args = ["run", "--rm", "-v", mount_arg, full_image]
        run = self._run(run_args, timeout=timeout)
        evidence.ran = True
        evidence.run_exit_code = run.returncode
        evidence.container_id = None  # --rm removes the container; id not persisted

        # 3. Collect on-disk artifacts.
        if out_xml.exists():
            evidence.output_xml = str(out_xml.resolve())
            evidence.output_xml_after = out_xml.stat().st_mtime
            evidence.artifacts.append(str(out_xml.resolve()))
            counts = self._parse_output_xml(out_xml)
            evidence.total = counts.get("total", 0)
            evidence.passed = counts.get("passed", 0)
            evidence.failed = counts.get("failed", 0)
            evidence.skipped = counts.get("skipped", 0)
        else:
            evidence.output_xml = None

        if allure_dir is not None and Path(allure_dir).exists():
            evidence.allure_results_count = len(list(Path(allure_dir).glob("*-result.json")))

        return evidence

    @staticmethod
    def _parse_output_xml(path: Path) -> dict:
        try:
            root = ET.parse(path).getroot()
            total = root.find("statistics/total")
            if total is None:
                return {}
            stats = [s for s in total if s.tag == "stat"]
            if not stats:
                return {}
            stat = stats[0].attrib
            passed = int(stat.get("pass", 0) or 0)
            failed = int(stat.get("fail", 0) or 0)
            skipped = int(stat.get("skip", 0) or 0)
            return {"total": passed + failed + skipped, "passed": passed,
                    "failed": failed, "skipped": skipped}
        except Exception:
            return {}
