"""Unit tests for the Jenkins branch-selection policy guard.

Verifies the permanent contract: Jenkins job Robot-Playwright-Sanity MUST target
*/feature/qa-auto-* AND */fix/qa-auto-* and MUST NEVER hard-code a single QA
feature/fix branch. These tests use synthetic config.xml text only; they never
read the live Jenkins config.
"""
from __future__ import annotations

import pytest

from orchestra.jenkins_policy import (
    EXPECTED_BRANCH_PATTERN,
    EXPECTED_BRANCH_PATTERNS,
    branch_specs_from_xml,
    validate_config,
    validate_jenkins_branch_policy,
    violations_for_specs,
)

FEATURE_WILDCARD = "*/feature/qa-auto-*"
FIX_WILDCARD = "*/fix/qa-auto-*"

GOOD_CONFIG = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <properties>
    <org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty>
      <triggers>
        <com.cloudbees.jenkins.GitHubPushTrigger plugin="github">
          <spec></spec>
        </com.cloudbees.jenkins.GitHubPushTrigger>
      </triggers>
    </org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty>
  </properties>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition">
    <scm class="hudson.plugins.git.GitSCM">
      <userRemoteConfigs>
        <hudson.plugins.git.UserRemoteConfig>
          <url>https://github.com/ajitsingh1987/robot-playwright-cicd.git</url>
        </hudson.plugins.git.UserRemoteConfig>
      </userRemoteConfigs>
      <branches>
        <hudson.plugins.git.BranchSpec>
          <name>*/feature/qa-auto-*</name>
        </hudson.plugins.git.BranchSpec>
        <hudson.plugins.git.BranchSpec>
          <name>*/fix/qa-auto-*</name>
        </hudson.plugins.git.BranchSpec>
      </branches>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
  </definition>
</flow-definition>"""

HARD_CODED_CONFIG = GOOD_CONFIG.replace(
    "<name>*/feature/qa-auto-*</name>",
    "<name>feature/qa-auto-orangehrm-automation</name>",
)


def make_config(branch: str = "*/feature/qa-auto-*",
                trigger: bool = True,
                url: str = "https://github.com/ajitsingh1987/robot-playwright-cicd.git",
                extra_branch: str = "*/fix/qa-auto-*"):
    trigger_xml = (
        '<org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty>\n'
        '      <triggers>\n'
        '        <com.cloudbees.jenkins.GitHubPushTrigger plugin="github">\n'
        '          <spec></spec>\n'
        '        </com.cloudbees.jenkins.GitHubPushTrigger>\n'
        '      </triggers>\n'
        '    </org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty>'
        if trigger else
        '<org.jenkinsci.plugins.workflow.job.properties.DisableConcurrentBuildsJobProperty>'
        '<abortPrevious>false</abortPrevious>'
        '</org.jenkinsci.plugins.workflow.job.properties.DisableConcurrentBuildsJobProperty>'
    )
    extra_spec = (
        f'\n        <hudson.plugins.git.BranchSpec>\n'
        f'          <name>{extra_branch}</name>\n'
        f'        </hudson.plugins.git.BranchSpec>' if extra_branch else ""
    )
    return f'''<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <properties>
    {trigger_xml}
  </properties>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition">
    <scm class="hudson.plugins.git.GitSCM">
      <userRemoteConfigs>
        <hudson.plugins.git.UserRemoteConfig>
          <url>{url}</url>
        </hudson.plugins.git.UserRemoteConfig>
      </userRemoteConfigs>
      <branches>
        <hudson.plugins.git.BranchSpec>
          <name>{branch}</name>
        </hudson.plugins.git.BranchSpec>{extra_spec}
      </branches>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
  </definition>
</flow-definition>'''


def test_expected_patterns_are_the_dual_wildcard_contract():
    assert EXPECTED_BRANCH_PATTERN == FEATURE_WILDCARD
    assert set(EXPECTED_BRANCH_PATTERNS) == {FEATURE_WILDCARD, FIX_WILDCARD}


def test_branch_specs_extracted_only_from_branchspec():
    specs = branch_specs_from_xml(GOOD_CONFIG)
    assert set(specs) == {FEATURE_WILDCARD, FIX_WILDCARD}


def test_dual_wildcard_patterns_are_compliant():
    assert violations_for_specs([FEATURE_WILDCARD, FIX_WILDCARD]) == []


def test_missing_fix_wildcard_is_a_violation():
    violations = violations_for_specs([FEATURE_WILDCARD])
    assert any("must include" in v and "fix/qa-auto-*" in v for v in violations)


def test_no_branch_spec_at_all_is_a_violation():
    violations = violations_for_specs([])
    assert any("must include" in v for v in violations)


def test_hard_coded_legacy_branch_is_rejected():
    violations = violations_for_specs(["feature/qa-auto-orangehrm-automation"])
    assert any("hard-coded QA branch" in v for v in violations)
    assert any("feature/qa-auto-orangehrm-automation" in v for v in violations)


def test_hard_coded_with_leading_wildcard_slash_is_rejected():
    violations = violations_for_specs(["*/feature/qa-auto-admin", FIX_WILDCARD])
    assert any("hard-coded QA branch" in v for v in violations)
    assert any("*/feature/qa-auto-admin" in v for v in violations)


def test_hard_coded_fix_branch_is_rejected_even_with_wildcards():
    violations = violations_for_specs(["fix/qa-auto-login", FEATURE_WILDCARD, FIX_WILDCARD])
    assert any("hard-coded QA branch" in v for v in violations)


def test_extra_non_qa_branch_is_fine_when_wildcards_present():
    assert violations_for_specs([FEATURE_WILDCARD, FIX_WILDCARD, "*/main"]) == []


def test_good_config_xml_passes():
    assert validate_config(GOOD_CONFIG) == []


def test_config_missing_fix_wildcard_fails():
    cfg = GOOD_CONFIG.replace(FIX_WILDCARD, "*/old-qa-branch")
    violations = validate_config(cfg)
    assert any("must include" in v for v in violations)


def test_hard_coded_config_xml_fails():
    violations = validate_config(HARD_CODED_CONFIG)
    assert any("hard-coded QA branch" in v for v in violations)
    assert any("feature/qa-auto-orangehrm-automation" in v for v in violations)


def test_config_without_wildcards_fails_but_no_hard_coding():
    cfg = GOOD_CONFIG.replace(FEATURE_WILDCARD, "*/main").replace(FIX_WILDCARD, "*/main")
    violations = validate_config(cfg)
    assert any("must include" in v for v in violations)
    assert not any("hard-coded QA branch" in v for v in violations)


def test_config_without_github_push_trigger_fails():
    cfg = make_config(trigger=False)
    violations = validate_config(cfg)
    assert any("GitHubPushTrigger is not enabled" in v for v in violations)


def test_config_with_wrong_repository_url_fails():
    cfg = make_config(url="https://github.com/other/repo.git")
    violations = validate_config(cfg)
    assert any("repository URL mismatch" in v for v in violations)


def test_malformed_xml_fails():
    violations = validate_config("<flow-definition>")
    assert any("not valid XML" in v for v in violations)


def test_validate_policy_respects_env_override(monkeypatch, tmp_path):
    import orchestra.jenkins_policy as pol

    monkeypatch.setattr(pol, "LIVE_CONFIG_PATHS", [tmp_path / "no-live.xml"])
    cfg = tmp_path / "config.xml"
    cfg.write_text(HARD_CODED_CONFIG, encoding="utf-8")
    monkeypatch.setenv("QA_JENKINS_CONFIG_XML", str(cfg))
    violations = validate_jenkins_branch_policy()
    assert any("config.xml" in v and "hard-coded QA branch" in v for v in violations)

    cfg.write_text(GOOD_CONFIG, encoding="utf-8")
    assert validate_jenkins_branch_policy() == []


def test_validate_policy_silent_when_no_config_discoverable(monkeypatch):
    import orchestra.jenkins_policy as pol

    monkeypatch.setattr(pol, "LIVE_CONFIG_PATHS", [])
    monkeypatch.delenv("QA_JENKINS_CONFIG_XML", raising=False)
    assert validate_jenkins_branch_policy() == []