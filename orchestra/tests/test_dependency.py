"""Impact/dependency analysis tests: deterministic owner-suite resolution.

Verifies the ONE REQUIREMENT -> ONE TEST FILE mapping, transitive resource
imports, and the safety fallback to FULL_REGRESSION when a changed artifact
maps to NO owner suite.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.config import settings
from orchestra.dependency import FileImpactAnalyzer, build_impact_metadata


@pytest.fixture(scope="module")
def analyzer() -> FileImpactAnalyzer:
    return FileImpactAnalyzer()


def test_owner_suites_are_all_discovered(analyzer: FileImpactAnalyzer):
    names = {p.name for p in analyzer.owners.owner_suites()}
    assert "orangehrm_employee_creation.robot" in names
    assert "orangehrm_login.robot" in names
    assert "orangehrm_qa_e2e_login_logout.robot" in names


def test_suite_own_requirement(analyzer: FileImpactAnalyzer):
    own = analyzer.owners.suites_importing(settings.PROJECT_ROOT / "tests" / "orangehrm_logout.robot")
    assert [p.name for p in own] == ["orangehrm_logout.robot"]


def test_page_object_maps_to_importing_suites(analyzer: FileImpactAnalyzer):
    page = settings.PROJECT_ROOT / "pages" / "orangehrm_login_page.robot"
    affected = analyzer.affected_suites([page])
    assert "orangehrm_login.robot" in {p.name for p in affected}


def test_shared_resource_transitive(analyzer: FileImpactAnalyzer):
    resource = settings.PROJECT_ROOT / "resources" / "browser.resource"
    affected = analyzer.affected_suites([resource])
    # every suite imports the shared browser resource
    assert {p.name for p in affected} == {
        p.name for p in analyzer.owners.owner_suites()
    }


def test_variable_data_dependency(analyzer: FileImpactAnalyzer):
    creds = settings.PROJECT_ROOT / "variables" / "credentials.py"
    affected = analyzer.affected_suites([creds])
    assert {p.name for p in affected} == {p.name for p in analyzer.owners.owner_suites()}


def test_changed_unknown_artifact_falls_back_to_full(analyzer: FileImpactAnalyzer):
    # a pseudo "unowned" artifact (a rob file that no suite imports)
    orphan = settings.PROJECT_ROOT / "pages" / "nobody_imports_me.page.robot"
    orphan.touch()
    try:
        affected = analyzer.affected_suites([orphan])
        assert {p.name for p in affected} == {p.name for p in analyzer.owners.owner_suites()}
    finally:
        orphan.unlink()


def test_empty_change_list_falls_back_full(analyzer: FileImpactAnalyzer):
    affected = analyzer.affected_suites([])
    assert {p.name for p in affected} == {p.name for p in analyzer.owners.owner_suites()}


def test_root_owner_suite_local(analyzer: FileImpactAnalyzer):
    suite = settings.PROJECT_ROOT / "tests" / "orangehrm_employee_creation.robot"
    assert [p.name for p in analyzer.owners.suites_importing(suite)] == ["orangehrm_employee_creation.robot"]


def test_impact_metadata_fixture(analyzer: FileImpactAnalyzer):
    meta = build_impact_metadata([settings.PROJECT_ROOT / "variables" / "urls.py"])
    assert meta["impact_type"] == "FULL_REGRESSION"
    assert len(meta["affected_suites"]) == len(analyzer.owners.owner_suites())


def test_affected_suites_respects_absolute_and_relative(analyzer: FileImpactAnalyzer):
    rel = Path("pages") / "orangehrm_login_page.robot"
    affected = analyzer.affected_suites([rel])
    assert "orangehrm_login.robot" in {p.name for p in affected}


def test_page_change_only_affects_its_importers(analyzer: FileImpactAnalyzer):
    logout_page = settings.PROJECT_ROOT / "pages" / "orangehrm_logout_page.robot"
    affected = analyzer.affected_suites([logout_page])
    names = {p.name for p in affected}
    # Only suites that actually import the logout page object.
    assert names == {"orangehrm_logout.robot", "orangehrm_qa_e2e_login_logout.robot"}
    assert "orangehrm_login.robot" not in names


def test_login_page_shared_surface_affects_all_login_suites(analyzer: FileImpactAnalyzer):
    login_page = settings.PROJECT_ROOT / "pages" / "orangehrm_login_page.robot"
    affected = analyzer.affected_suites([login_page])
    names = {p.name for p in affected}
    for suite in ("orangehrm_login.robot", "orangehrm_logout.robot", "orangehrm_forgot_password.robot",
                  "orangehrm_employee_creation.robot", "orangehrm_qa_e2e_login_logout.robot"):
        assert suite in names