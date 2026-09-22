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


def branch_filter_includes_from_xml(xml_text: str) -> List[str]:
    """Extract branch-discovery wildcard includes from a Jenkins config.xml.

    Multibranch Pipeline (GitHub Branch Source) jobs select branches through a
    WildcardSCMHeadFilterTrait <includes> token list (e.g.
    "feature/qa-auto-* fix/qa-auto-*"). A hard-coded token such as
    "feature/qa-auto-admin" is the multibranch equivalent of a narrowed
    BranchSpec and MUST be rejected by the branch-pattern contract.
    """
    root = ET.fromstring(xml_text)
    includes = []
    for el in root.iter():
        if el.tag.rsplit(".", 1)[-1] != "WildcardSCMHeadFilterTrait":
            continue
        for child in el:
            if child.tag.rsplit(".", 1)[-1] == "includes":
                for token in (child.text or "").split():
                    token = token.strip()
                    if token:
                        includes.append(token)
    return includes


def jenkins_triggers_from_xml(xml_text: str) -> List[str]:
    """Return the trigger class names found in the config, e.g. GitHubPushTrigger."""
    root = ET.fromstring(xml_text)
    return [child.tag.rsplit(".", 1)[-1] for child in root.iter()]


def repository_url_from_xml(xml_text: str) -> str | None:
    """Return the SCM remote URL if present.

    Supports git-plugin <url>, GitHubSCMSource <repositoryUrl>, and derives the
    URL from repoOwner/repository when those are the only source elements.
    """
    root = ET.fromstring(xml_text)
    for repo_url in root.iter("repositoryUrl"):
        if repo_url.text and repo_url.text.strip():
            return repo_url.text.strip()
    for url in root.iter("url"):
        if url.text and url.text.strip():
            return url.text.strip()
    owner = repository = None
    for el in root.iter():
        tag = el.tag.rsplit(".", 1)[-1]
        if tag == "repoOwner":
            owner = (el.text or "").strip()
        elif tag == "repository":
            repository = (el.text or "").strip()
    if owner and repository:
        return f"https://github.com/{owner}/{repository}.git"
    return None


def _strip_ref_prefix(spec: str) -> str:
    """Normalize */feature/qa-auto-* and feature/qa-auto-* to the same token."""
    return spec[2:] if spec.startswith("*/") else spec


def violations_for_specs(specs: List[str]) -> List[str]:
    """Return a list of violations; an empty list means the specs are compliant.

    Rules enforced (hard contract):
      1. The wildcards */feature/qa-auto-* and */fix/qa-auto-* MUST be present
         (a Multibranch WildcardSCMHeadFilterTrait token of the same branch is
         compared with the leading */ already consumed by branch discovery).
      2. No individual feature/qa-auto-<x> or fix/qa-auto-<x> branch may be
         hard-coded.
    """
    violations = []
    normalized = [_strip_ref_prefix(s) for s in specs]
    expected = {_strip_ref_prefix(p) for p in EXPECTED_BRANCH_PATTERNS}
    missing = sorted(expected - set(normalized))
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


def _is_multibranch(root: ET.Element) -> bool:
    return root.tag.rsplit(".", 1)[-1] == "WorkflowMultiBranchProject"


def validate_multibranch_config(root: ET.Element, xml_text: str) -> List[str]:
    """Validate a Multibranch Pipeline config (GitHub Branch Source).

    The branch contract maps to the discovery wildcard filter: BOTH
    feature/qa-auto-* and fix/qa-auto-* must be discovered and no single QA
    branch may be pinned. Triggering must stay webhook-only: periodic or timed
    scan triggers are architecture violations (the GitHub webhook is the ONLY
    allowed mechanism to start the job).
    """
    violations = []
    classes = {el.get("class", "") for el in root.iter() if el.get("class")}
    spec_text = [el.text for el in root.iter() if el.tag.rsplit(".", 1)[-1] == "WildcardSCMHeadFilterTrait"]
    if not any("GitHubSCMSource" in c for c in classes):
        violations.append("Multibranch job has no GitHubSCMSource (GitHub Branch Source)")
    specs = branch_filter_includes_from_xml(xml_text)
    if not specs:
        violations.append(
            "Multibranch job has no wildcard branch filter "
            "(must discover feature/qa-auto-* and fix/qa-auto-*)"
        )
    elif violations_for_specs(specs):
        violations.extend(violations_for_specs(specs))
    url = repository_url_from_xml(xml_text)
    if url and url != EXPECTED_REPOSITORY:
        violations.append(
            f"Jenkins SCM repository URL mismatch: {url!r} "
            f"(expected {EXPECTED_REPOSITORY!r})"
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

    if _is_multibranch(root):
        violations.extend(validate_multibranch_config(root, xml_text))
        for trigger in ("PeriodicFolderTrigger", "TimerTrigger"):
            if trigger in roots:
                violations.append(
                    f"webhook-only contract violated: schedule trigger {trigger} present"
                )
        return violations

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