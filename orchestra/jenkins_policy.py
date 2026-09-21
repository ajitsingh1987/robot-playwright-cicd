"""Jenkins QA branch-selection policy guard.

The Jenkins job Robot-Playwright-Sanity MUST consume every autonomous QA branch
through the wildcard patterns:

    */feature/qa-auto-*     (NEW_AUTOMATION / AUTOMATION_ENHANCEMENT)
    */fix/qa-auto-*         (AUTOMATION_FIX)

A BranchSpec that hard-codes ONE QA branch (e.g.
feature/qa-auto-orangehrm-automation, */feature/qa-auto-admin or
*/fix/qa-auto-login) is an ARCHITECTURE violation: GitHub webhook pushes from
feature/qa-auto-admin, feature/qa-auto-leave, fix/qa-auto-login, ... are then
silently ignored. This module is the permanent regression guard against that
violation. It is read-only: it inspects Jenkins config XML and never mutates it.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

# The architecture contract. NEVER replace with a single branch name.
EXPECTED_BRANCH_PATTERN = "*/feature/qa-auto-*"
EXPECTED_BRANCH_PATTERNS = ("*/feature/qa-auto-*", "*/fix/qa-auto-*")

_BRANCH_TOKEN_RE = re.compile(r"feature/qa-auto-[^\s<]+")
_HARD_CODED_QA_BRANCH_RE = re.compile(
    r"(?:^|/|\*/)feature/qa-auto-(?!\*)[^\s<]+"
)
_HARD_CODED_QA_FIX_RE = re.compile(r"(?:^|/|\*/)fix/qa-auto-(?!\*)[^\s<]+")

# Candidate live/repo config locations (read-only discovery, best effort).
LIVE_CONFIG_PATHS = [
    Path(r"C:\ProgramData\Jenkins\.jenkins\jobs\Robot-Playwright-Sanity\config.xml"),
    Path(r"/var/jenkins_home/jobs/Robot-Playwright-Sanity/config.xml"),
]

EXPECTED_REPOSITORY = "https://github.com/ajitsingh1987/robot-playwright-cicd.git"


def branch_specs_from_xml(xml_text: str) -> List[str]:
    """Extract every git BranchSpec <name> value from a Jenkins config.xml."""
    root = ET.fromstring(xml_text)
    specs = []
    for el in root.iter():
        if el.tag.rsplit(".", 1)[-1] != "BranchSpec":
            continue
        for child in el:
            if child.tag.rsplit(".", 1)[-1] == "name":
                value = (child.text or "").strip()
                if value:
                    specs.append(value)
    return specs


def jenkins_triggers_from_xml(xml_text: str) -> List[str]:
    """Return the trigger class names found in the config, e.g. GitHubPushTrigger."""
    root = ET.fromstring(xml_text)
    return [child.tag.rsplit(".", 1)[-1] for child in root.iter()]


def repository_url_from_xml(xml_text: str) -> str | None:
    """Return the SCM remote URL if present."""
    root = ET.fromstring(xml_text)
    for url in root.iter("url"):
        if url.text and url.text.strip():
            return url.text.strip()
    return None


def violations_for_specs(specs: List[str]) -> List[str]:
    """Return a list of violations; an empty list means the specs are compliant.

    Rules enforced (hard contract):
      1. The wildcards */feature/qa-auto-* and */fix/qa-auto-* MUST be present.
      2. No individual feature/qa-auto-<x> or fix/qa-auto-<x> branch may be
         hard-coded.
    """
    violations = []
    missing = [p for p in EXPECTED_BRANCH_PATTERNS if p not in specs]
    if missing:
        violations.append(
            f"Jenkins BranchSpec must include {list(EXPECTED_BRANCH_PATTERNS)!r}, "
            f"found: {specs} (missing: {missing})"
        )
    for spec in specs:
        if _HARD_CODED_QA_BRANCH_RE.search(spec) or _HARD_CODED_QA_FIX_RE.search(spec):
            violations.append(
                f"hard-coded QA branch in Jenkins BranchSpec: {spec!r} "
                f"(must be {list(EXPECTED_BRANCH_PATTERNS)!r})"
            )
    return violations


def validate_config(xml_text: str) -> List[str]:
    """Validate ONE Jenkins config.xml against the branch-pattern contract."""
    violations = []
    roots = {}
    try:
        root = ET.fromstring(xml_text)
        for child in root.iter():
            tag = child.tag.rsplit(".", 1)[-1]
            roots.setdefault(tag, 0)
            roots[tag] += 1
    except ET.ParseError as exc:
        return [f"Jenkins config.xml is not valid XML: {exc}"]

    if "BranchSpec" not in roots:
        violations.append("Jenkins config.xml contains no <BranchSpec> (git branch selection)")

    specs = branch_specs_from_xml(xml_text)
    if specs:
        violations.extend(violations_for_specs(specs))

    if "GitHubPushTrigger" not in roots:
        violations.append("GitHubPushTrigger is not enabled in the Jenkins job")

    if "CpsScmFlowDefinition" in roots or "scm" in roots:
        url = repository_url_from_xml(xml_text)
        if url and url != EXPECTED_REPOSITORY:
            violations.append(
                f"Jenkins SCM repository URL mismatch: {url!r} "
                f"(expected {EXPECTED_REPOSITORY!r})"
            )
    return violations


def discover_config_paths() -> List[Path]:
    """Candidate config.xml paths: env override first, then live locations."""
    candidates = []
    env = os.environ.get("QA_JENKINS_CONFIG_XML")
    if env:
        candidates.append(Path(env))
    candidates.extend(LIVE_CONFIG_PATHS)
    return candidates


def validate_jenkins_branch_policy() -> List[str]:
    """Aggregate branch-pattern violations across all discoverable configs.

    Read-only. Returns an empty list when every discovered config is compliant
    (or when no config is discoverable from this environment — the guard then
    stays silent and is exercised by unit tests / CI).
    """
    all_violations = []
    for path in discover_config_paths():
        if not path.exists():
            continue
        try:
            xml_text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        file_violations = validate_config(xml_text)
        if file_violations:
            all_violations.append(f"{path}: " + "; ".join(file_violations))
    return all_violations