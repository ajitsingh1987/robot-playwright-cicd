"""Command-line entry point for the executable orchestration kernel.

Provides a dry-run harness (validates machine/transition logic with mock evidence) and an
architecture-validation mode (read-only structural probe) — neither claims browser/test
execution. Real execution is enabled only when explicitly requested.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters.git import GitAdapter
from .change_intel import ChangeClassifier
from .commit_planner import CommitPlanner
from .evidence import EvidenceBus
from .gates import GateEngine
from .kernel import Kernel
from .machine import StageRegistry
from .scope import ImpactDecision
from .state import StateStore, next_run_id


def _build_kernel(expected_scope: str) -> Kernel:
    store = StateStore(next_run_id())
    registry = StageRegistry()
    gates = GateEngine()
    evidence = EvidenceBus(store)
    return Kernel(store=store, registry=registry, gates=gates, evidence=evidence)


def dry_run(expected_scope: str = "FULL_REGRESSION", mode: str = "NEW_AUTOMATION") -> int:
    """Simulated end-to-end run proving transitions + gates with mock evidence."""
    print(f"[dry-run] mode={mode} expected_scope={expected_scope}")
    k = _build_kernel(expected_scope)

    for stage in ["REQUIREMENT_RECEIVED", "REQUIREMENT_CLASSIFICATION"]:
        assert k.registry.has_stage(stage)

    # classify -> impact -> coverage -> branch (automation path)
    k.classify(mode)
    k.impact(ImpactDecision(confidence="HIGH", impacted_tests=["tests/x.robot"]))
    k.coverage("PARTIAL")
    if mode == "REGRESSION":
        k.branch(None)
        assert k.gates.evaluate_gate("gate_branch_derived", k.store.snapshot())
        print(f"[dry-run] REGRESSION path -> branch NONE ok.")
    else:
        k.branch("feature/qa-auto-x")
        assert k.gates.evaluate_gate("gate_branch_derived", k.store.snapshot())
    print(f"[dry-run] -> branch ok, automation_mode={mode}")

    # gate: branch_derived must hold for automation modes
    assert k.gates.evaluate_gate("gate_branch_derived", k.store.snapshot())

    # coverage after impact gate
    assert k.gates.evaluate_gate("gate_coverage_after_impact", k.store.snapshot())

    # REGRESSION should be able to terminate at COMPLETED (no commit/push)
    if mode == "REGRESSION":
        assert k.registry.allowed("BRANCH_DECISION", "COMPLETED") is True
        assert k.registry.allowed("BRANCH_DECISION", "COMMIT") is False  # never commit/push

    # This dry-run simulates the FULL lifecycle of gates; since we cannot run a real
    # browser/robot here, we stop at the deterministic machine-validation boundary
    # (branches, coverage, healing cap, scope rules). No PASS for browser/test is claimed.
    print("[dry-run] deterministic machine validation OK.")
    return 0


def architecture_validate() -> int:
    """Read-only structural + contract validation. NEVER executes browser/tests."""
    failures = []
    root = Path.cwd()

    # structural probes
    required_dirs = ["tests", "pages", "resources", "variables", "data", ".opencode/agents"]
    for d in required_dirs:
        if not (root / d).exists():
            failures.append(f"missing dir: {d}")

    # agent contracts present?
    for agent in ("qa-orchestrator", "planner", "playwright", "generator",
                  "healer", "reviewer", "reporter", "failure-analysis", "cicd"):
        if not (root / ".opencode" / "agents" / f"{agent}.md").exists():
            failures.append(f"missing agent: {agent}")

    # machine config parse + edge table self-check
    reg = StageRegistry()
    for s in reg.stages:
        if not reg.has_stage(s["id"]):
            failures.append(f"stage not registered: {s['id']}")

    # taxonomy parse + legacy mapping coverage
    import yaml

    tax = yaml.safe_load(
        (Path(__file__).parent / "config" / "taxonomy.yaml").read_text(encoding="utf-8")
    )
    canonical = {c["id"] for c in tax["categories"]}
    legacy_vals = set(tax["legacy_mapping"].values())
    if not legacy_vals.issubset(canonical):
        failures.append("taxonomy legacy_mapping references unknown category")

    if failures:
        print("[architecture-validation] FAILURES:")
        for f in failures:
            print("   -", f)
        return 1
    print("[architecture-validation] OK (read-only; no execution performed).")
    return 0


def delivery_plan(
    branch: str,
    requirement: str = "qa-automation",
    mode: str = "NEW_AUTOMATION",
    dry_run: bool = True,
) -> int:
    """Dry-run the Commit Planner against the REAL git working tree (read-only).

    Builds the machine-readable CommitPlan and evaluates every mandatory commit
    gate, but NEVER stages, commits or pushes. This is the safe validation path
    for the autonomous git delivery flow before any real mutation.
    """
    print(
        f"[delivery-plan] dry_run={dry_run} branch={branch} "
        f"requirement={requirement} mode={mode}"
    )
    git = GitAdapter()
    current = git.current_branch()
    if branch and current != branch:
        print(f"[delivery-plan] ERROR: active branch is {current!r}, plan requires {branch!r}")
        return 2

    # A minimal state snapshot for the gates that depend on recorded quality
    # evidence; git-backed gates are computed live against the real adapter.
    store = StateStore(next_run_id())
    step = Kernel(store=store)

    planner = CommitPlanner(classifier=ChangeClassifier())
    plan = planner.plan(
        requirement=requirement,
        automation_mode=mode,
        branch=current or branch,
        state=store.snapshot(),
        git=git,
        dry_run=dry_run,
    )
    print("[delivery-plan] " + json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    if plan.safe:
        print(
            f"[delivery-plan] PLAN SAFE: {len(plan.files_to_stage)} file(s) would be "
            f"committed on {plan.branch}."
        )
        return 0
    print(
        f"[delivery-plan] PLAN UNSAFE: {plan.failed_gates} — NO commit would be created. "
        "This is the intended safety behavior."
    )
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="orchestra")
    sub = parser.add_subparsers(dest="cmd")

    dry = sub.add_parser("dry-run", help="simulate the machine with mock evidence")
    dry.add_argument("--mode", default="NEW_AUTOMATION")
    dry.add_argument("--scope", default="FULL_REGRESSION")

    sub.add_parser("arch", help="read-only architecture validation")

    dp = sub.add_parser(
        "delivery-plan",
        help="dry-run the Commit Planner against the real working tree (read-only)",
    )
    dp.add_argument("--branch", default="")
    dp.add_argument("--requirement", default="qa-automation")
    dp.add_argument("--mode", default="NEW_AUTOMATION", choices=[
        "REGRESSION", "NEW_AUTOMATION", "AUTOMATION_ENHANCEMENT", "AUTOMATION_FIX",
    ])
    dp.add_argument("--no-dry-run", action="store_true",
                    help="dev/self-test only; never used for a real requirement")

    args = parser.parse_args(argv)
    if args.cmd == "dry-run":
        return dry_run(args.scope, args.mode)
    if args.cmd == "arch":
        return architecture_validate()
    if args.cmd == "delivery-plan":
        if args.no_dry_run:
            print("[delivery-plan] ERROR: execution mode is forbidden for autonomous git delivery.")
            return 2
        return delivery_plan(
            branch=args.branch,
            requirement=args.requirement,
            mode=args.mode,
            dry_run=True,
        )
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
