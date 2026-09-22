"""Unit tests for the CI quality gate (Robot + Allure + branch evidence).

These tests use synthetic output.xml / allure files only; no browser or execution
is required. They cover the GREEN / RED / UNVERIFIED verdicts, status parity,
credential scan propagation, the SCM evidence contract (feature/fix branches and
valid SHA) and the JSON export used by Jenkins CI_VALIDATION.
"""
from __future__ import annotations

from pathlib import Path

from orchestra.ci_quality import CIQualityGate, QA_BRANCH_PATTERNS


def _clean_output_xml(path: Path, total: int = 4) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<robot><statistics><total><stat pass="{total}" fail="0" skip="0"/></total>'
        f"</statistics></robot>",
        encoding="utf-8",
    )
    return path


def _failing_output_xml(path: Path, failed: int = 2, total: int = 5) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<robot><statistics><total><stat pass="{total - failed}" fail="{failed}" skip="0"/></total>'
        f"</statistics></robot>",
        encoding="utf-8",
    )
    return path


def _allure_dir(path: Path, count: int) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (path / f"r{i}-result.json").write_text("{}", encoding="utf-8")
    return path


def test_missing_output_xml_is_unverified(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(output_xml=tmp_path / "missing.xml",
                        allure_dir=_allure_dir(tmp_path / "ar", 1))
    assert res.status == "UNVERIFIED"
    assert any("missing robot output.xml" in r for r in res.reasons)


def test_clean_run_with_parity_is_green(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
    )
    assert res.status == "GREEN"
    assert res.robot["total"] == 4
    assert res.robot["failed"] == 0
    assert res.allure["status_parity"] is True
    assert res.allure["credential_leak"] is False


def test_failing_run_is_red(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_failing_output_xml(tmp_path / "out" / "output.xml", failed=2),
        allure_dir=_allure_dir(tmp_path / "ar", 5),
    )
    assert res.status == "RED"
    assert any("failed=2" in r for r in res.reasons)


def test_allure_parity_mismatch_is_red(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 2),
    )
    assert res.status == "RED"
    assert any("allure parity mismatch" in r for r in res.reasons)


def test_missing_allure_results_is_red(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(output_xml=_clean_output_xml(tmp_path / "out" / "output.xml"))
    assert res.status == "RED"


def test_credential_leak_is_red(tmp_path):
    ar = _allure_dir(tmp_path / "ar", 4)
    (ar / "leak-0-result.json").write_text(
        '{"desc":"apikey": "sk-abcdefghijklmnopqrst"}', encoding="utf-8"
    )
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=ar,
    )
    assert res.status == "RED"
    assert res.allure["credential_leak"] is True


def test_feature_branch_evidence_is_accepted(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="feature/qa-auto-admin",
        commit="e1d406b",
    )
    assert res.status == "GREEN"


def test_fix_branch_evidence_is_accepted(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="fix/qa-auto-login-assertion",
        commit="e1d406babc123",
    )
    assert res.status == "GREEN"


def test_main_branch_evidence_is_red(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="main",
        commit="e1d406b",
    )
    assert res.status == "RED"
    assert any("not in" in r for r in res.reasons)


def test_jenkins_origin_prefixed_branch_is_accepted(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="origin/feature/qa-auto-leave-application-approval",
        commit="7dfe64fabc",
    )
    assert res.status == "GREEN"


def test_multibranch_refs_remotes_branch_is_accepted(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="refs/remotes/origin/feature/qa-auto-admin",
        commit="e44767eabc",
    )
    assert res.status == "GREEN"


def test_multibranch_star_prefixed_branch_is_accepted(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="*/feature/qa-auto-recruitment",
        commit="e44767eabc",
    )
    assert res.status == "GREEN"


def test_invalid_sha_is_red(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="feature/qa-auto-x",
        commit="not-a-sha!",
    )
    assert res.status == "RED"


def test_qa_branch_patterns_cover_feature_and_fix():
    assert "feature/qa-auto-" in QA_BRANCH_PATTERNS
    assert "fix/qa-auto-" in QA_BRANCH_PATTERNS


def test_export_writes_machine_readable_json(tmp_path):
    gate = CIQualityGate()
    res = gate.evaluate(
        output_xml=_clean_output_xml(tmp_path / "out" / "output.xml", total=4),
        allure_dir=_allure_dir(tmp_path / "ar", 4),
        branch="feature/qa-auto-admin",
        commit="e1d406b",
    )
    out = gate.export(res, tmp_path / "run" / "ci-quality-gate.json")
    assert out.exists()
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "GREEN"
    assert data["branch"] == "feature/qa-auto-admin"
    assert data["commit"] == "e1d406b"
    assert data["allure"]["status_parity"] is True