"""Tests for the Jenkinsfile Branch Verification normalization + contract.

Two layers:

  1. A cross-platform STATIC guard that the Jenkinsfile never reintroduces the
     broken cmd wildcard substitution `%EXPECTED_BRANCH:*/=%` (which silently
     turned `feature/qa-auto-admin` into `qa-auto-admin`) and that the explicit,
     deterministic prefix slicing is present.

  2. A BEHAVIORAL test that extracts the real Branch Verification `bat` block from
     the Jenkinsfile and runs it with cmd.exe against an isolated temporary git
     repo, asserting the exact PASS/FAIL contract. It is skipped on non-Windows
     hosts or when git is unavailable (e.g. the Linux Docker framework gate).

No real project git state is touched: the temp repo lives under pytest's tmp_path.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

JENKINSFILE = Path(__file__).resolve().parents[2] / "Jenkinsfile"


def _jenkinsfile_text() -> str:
    return JENKINSFILE.read_text(encoding="utf-8")


def _extract_branch_verification_bat() -> str:
    text = _jenkinsfile_text()
    idx = text.index("stage('Branch Verification')")
    start = text.index("bat '''", idx) + len("bat '''")
    end = text.index("'''", start)
    bat = text[start:end]
    # Groovy single-quoted strings un-escape \\ -> \ ; emulate for a faithful run.
    return bat.replace("\\\\", "\\")


# ── static guard (cross-platform) ─────────────────────────────────────────
def test_jenkinsfile_has_no_wildcard_substitution_bug():
    text = _jenkinsfile_text()
    assert "EXPECTED_BRANCH:*/=" not in text, (
        "cmd wildcard substitution %VAR:*/=% corrupts feature/... into qa-auto-..."
    )


def test_jenkinsfile_uses_explicit_prefix_slicing():
    text = _jenkinsfile_text()
    for probe in ("EXPECTED_BRANCH:~0,2%", "EXPECTED_BRANCH:~0,7%",
                  "EXPECTED_BRANCH:~0,11%", "refs/remotes/origin/", "refs/heads/"):
        assert probe in text, probe


# ── behavioral batch contract (Windows + git) ─────────────────────────────
pytestmark = pytest.mark.skipif(
    os.name != "nt" or shutil.which("git") is None,
    reason="Jenkins Branch Verification batch runs with cmd.exe + git on Windows",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )


@pytest.fixture()
def branch_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    (repo / "f.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "checkout", "-q", "-b", "feature/qa-auto-admin")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    bat = repo / "branch-verify.bat"
    bat.write_text(_extract_branch_verification_bat(), encoding="utf-8")
    return repo, bat, head


def _run(repo: Path, bat: Path, *, branch=None, commit=None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if branch is None:
        env.pop("GIT_BRANCH", None)
    else:
        env["GIT_BRANCH"] = branch
    if commit is None:
        env.pop("GIT_COMMIT", None)
    else:
        env["GIT_COMMIT"] = commit
    return subprocess.run(
        ["cmd", "/c", str(bat)], cwd=repo, capture_output=True, text=True, env=env
    )


@pytest.mark.parametrize("reported", [
    "origin/feature/qa-auto-admin",
    "*/feature/qa-auto-admin",
    "refs/heads/feature/qa-auto-admin",
    "refs/remotes/origin/feature/qa-auto-admin",
    "feature/qa-auto-admin",
])
def test_batch_passes_for_valid_feature_branch(branch_repo, reported):
    repo, bat, head = branch_repo
    proc = _run(repo, bat, branch=reported, commit=head)
    assert proc.returncode == 0, proc.stdout
    assert "Branch commit verification: PASS" in proc.stdout


def test_batch_passes_for_valid_fix_branch(branch_repo):
    repo, bat, _ = branch_repo
    _git(repo, "checkout", "-q", "-b", "fix/qa-auto-login")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    for reported in ("origin/fix/qa-auto-login", "*/fix/qa-auto-login",
                     "refs/heads/fix/qa-auto-login"):
        proc = _run(repo, bat, branch=reported, commit=head)
        assert proc.returncode == 0, proc.stdout
        assert "Branch commit verification: PASS" in proc.stdout


@pytest.mark.parametrize("reported", [
    "origin/main",
    "origin/master",
    "origin/feature/random",
    "origin/fix/random",
    "origin/qa-auto-admin",
])
def test_batch_rejects_invalid_branch_family(branch_repo, reported):
    repo, bat, head = branch_repo
    proc = _run(repo, bat, branch=reported, commit=head)
    assert proc.returncode == 1, proc.stdout


def test_batch_rejects_branch_substitution(branch_repo):
    repo, bat, head = branch_repo
    proc = _run(repo, bat, branch="origin/feature/qa-auto-other", commit=head)
    assert proc.returncode == 1
    assert "branch substitution" in proc.stdout


def test_batch_rejects_commit_mismatch(branch_repo):
    repo, bat, _ = branch_repo
    proc = _run(repo, bat, branch="origin/feature/qa-auto-admin", commit="0" * 40)
    assert proc.returncode == 1
    assert "commit mismatch" in proc.stdout


def test_batch_rejects_missing_branch(branch_repo):
    repo, bat, head = branch_repo
    proc = _run(repo, bat, branch=None, commit=head)
    assert proc.returncode == 1
    assert "GIT_BRANCH not defined" in proc.stdout


def test_batch_rejects_missing_commit(branch_repo):
    repo, bat, _ = branch_repo
    proc = _run(repo, bat, branch="origin/feature/qa-auto-admin", commit=None)
    assert proc.returncode == 1
    assert "GIT_COMMIT not defined" in proc.stdout
