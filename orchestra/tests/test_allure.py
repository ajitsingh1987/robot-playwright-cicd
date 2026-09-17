"""Unit tests for the Allure artifact adapter (parity, presence, credential scan).

These tests mock the robot/allure subprocess; they do not require a real execution.
The Windows launcher resolution and relative-posix listener path are covered directly.
"""
from __future__ import annotations

from pathlib import Path

from orchestra.adapters.allure import AllureRunner, _relposix


def test_relposix_yields_relative_forward_slash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "results" / "allure-results"
    assert _relposix(p) == "results/allure-results"


def test_credential_scan_detects_secret(tmp_path):
    runner = AllureRunner()
    d = tmp_path / "ar"
    d.mkdir()
    (d / "x.json").write_text('{"desc":"password": "sup3rsecretvalue123"}', encoding="utf-8")
    assert runner.scan_for_credentials(d) is True


def test_credential_scan_clean_for_benign(tmp_path):
    runner = AllureRunner()
    d = tmp_path / "ar"
    d.mkdir()
    (d / "x.json").write_text('{"desc":"login ok, no secrets"}', encoding="utf-8")
    assert runner.scan_for_credentials(d) is False


class _FakeProc:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def test_run_computes_status_parity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = AllureRunner(results_dir=tmp_path)

    # fake output.xml with total=3 (2 pass, 1 fail)
    out_xml = tmp_path / "output.xml"
    out_xml.write_text(
        '<robot><statistics><total><stat pass="2" fail="1" skip="0"/></total>'
        "</statistics></robot>",
        encoding="utf-8",
    )
    ar = tmp_path / "allure-results"
    ar.mkdir()
    for i in range(3):
        (ar / f"r{i}-result.json").write_text("{}", encoding="utf-8")

    import orchestra.adapters.allure as ada

    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr(ada.subprocess, "run", fake_run)
    res = runner.run(target=str(tmp_path), allure_dir=ar, output_dir=tmp_path,
                     timeout=10, clean=False)
    assert res.total == 3
    assert res.result_count == 3
    assert res.results_present is True
    assert res.status_parity is True
    assert res.credential_leak is False
    # listener path is relative posix (no absolute Windows drive colon)
    listener = next(a for a in captured["cmd"] if a.startswith("allure_robotframework:"))
    assert ":" in listener  # the arg separator
    assert not listener.split(":", 1)[1].startswith("C")


def test_run_status_parity_false_on_mismatch(tmp_path, monkeypatch):
    runner = AllureRunner(results_dir=tmp_path)
    out_xml = tmp_path / "output.xml"
    out_xml.write_text(
        '<robot><statistics><total><stat pass="5" fail="0" skip="0"/></total>'
        "</statistics></robot>",
        encoding="utf-8",
    )
    ar = tmp_path / "allure-results"
    ar.mkdir()
    (ar / "r0-result.json").write_text("{}", encoding="utf-8")

    import orchestra.adapters.allure as ada

    monkeypatch.setattr(ada.subprocess, "run", lambda *a, **k: _FakeProc())
    res = runner.run(target=str(tmp_path), allure_dir=ar, output_dir=tmp_path,
                     timeout=10, clean=False)
    assert res.total == 5
    assert res.result_count == 1
    assert res.results_present is True
    assert res.status_parity is False
