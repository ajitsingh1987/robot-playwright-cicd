"""Unit tests for the Agent CLI adapter (delegation boundary, mocked subprocess).

These tests do NOT invoke real agents; they mock the subprocess to validate JSON-event
parsing, evidence recording, and the "no evidence -> refuse to advance" safety rule.
"""
from __future__ import annotations

import json
import pytest

from orchestra.adapters.agent_cli import AgentCLI, AgentResult
from orchestra.kernel import Kernel
from orchestra.state import StateStore

SAMPLE_STREAM = "\n".join(
    [
        json.dumps({"type": "step_start", "sessionID": "ses_abc123", "part": {}}) + "\n",
        json.dumps({"type": "text", "sessionID": "ses_abc123", "part": {"id": "p1", "type": "text", "text": "line one"}}) + "\n",
        json.dumps({"type": "text", "sessionID": "ses_abc123", "part": {"id": "p2", "type": "text", "text": "line two"}}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": "ses_abc123", "part": {"id": "p3", "type": "step-finish", "reason": "stop"}}) + "\n",
    ]
)


def fake_proc(stdout: str, returncode: int = 0):
    class _P:
        def __init__(self, out, code):
            self.stdout = out
            self.returncode = code

    return _P(stdout, returncode)


def test_text_extraction_from_stream():
    assert AgentCLI._extract_text(SAMPLE_STREAM) == "line one\nline two"
    assert AgentCLI._extract_session_id(SAMPLE_STREAM) == "ses_abc123"


def test_unknown_agent_rejected():
    cli = AgentCLI()
    with pytest.raises(ValueError):
        cli.run_agent("not-a-real-agent", "hi")


def test_parse_into_agent_result(monkeypatch):
    cli = AgentCLI()
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: fake_proc(SAMPLE_STREAM, 0)
    )
    res = cli.run_agent("reviewer", "mock message", timeout=5)
    assert res.exit_code == 0
    assert res.session_id == "ses_abc123"
    assert res.text == "line one\nline two"


def test_invoke_agent_records_evidence_and_advances(monkeypatch, tmp_path):
    class FakeCLI:
        def run_agent(self, agent, message, timeout=900, output_file=None):
            if output_file is not None:
                output_file.write_text(SAMPLE_STREAM, encoding="utf-8")
            return AgentResult(
                agent=agent,
                exit_code=0,
                session_id="ses_xyz",
                text="verdict APPROVED",
                artifacts=[str(output_file)] if output_file else [],
            )

    store = StateStore("test-agent-0001")
    k = Kernel(store=store, agent_cli=FakeCLI())  # type: ignore[arg-type]
    k.classify("NEW_AUTOMATION")
    k.impact(
        __import__("orchestra.scope", fromlist=["ImpactDecision"]).ImpactDecision(
            confidence="HIGH", impacted_tests=["tests/x.robot"], scope_evidence=["e"]
        )
    )
    k.coverage("PARTIAL")
    k.branch("feature/qa-auto-x")
    # branch -> planning(agent)
    res = k.invoke_agent("planner", "PLANNING", "make plan")
    assert res.session_id == "ses_xyz"
    assert store.current_state() == "PLANNING"
    assert store.get("PLANNING.agent")["text"] == "verdict APPROVED"


def test_invoke_agent_refuses_without_evidence(monkeypatch):
    class FakeEmptyCLI:
        def run_agent(self, agent, message, timeout=900, output_file=None):
            return AgentResult(agent=agent, exit_code=0, session_id="", text="")

    store = StateStore("test-agent-0002")
    k = Kernel(store=store, agent_cli=FakeEmptyCLI())  # type: ignore[arg-type]
    k.classify("NEW_AUTOMATION")
    k.impact(
        __import__("orchestra.scope", fromlist=["ImpactDecision"]).ImpactDecision(
            confidence="HIGH", impacted_tests=["tests/x.robot"], scope_evidence=["e"]
        )
    )
    k.coverage("PARTIAL")
    k.branch("feature/qa-auto-x")
    with pytest.raises(RuntimeError, match="no evidence"):
        k.invoke_agent("planner", "PLANNING", "not enough")
    # stage must NOT have advanced
    assert store.current_state() != "PLANNING"
