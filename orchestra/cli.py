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
from .ci_quality import CIQualityGate
from .commit_planner import CommitPlanner
from .evidence import EvidenceBus
from .gates import GateEngine
from .jenkins_policy import validate_jenkins_branch_policy
from .kernel import Kernel
from .local_gate import load_verdict, run_local_gate, export_verdict
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

    # Jenkins QA branch-selection contract: the job MUST target the wildcard
    # */feature/qa-auto-* and MUST NEVER hard-code a single QA feature branch.
    # Read-only; checks every discoverable Jenkins config.xml (env override or
    # live job path). No config on this host -> passes silently (unit-tested).
    jenkins_violations = validate_jenkins_branch_policy()
    for violation in jenkins_violations:
        failures.append(violation)

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

    # Hydrate the recorded LOCAL QUALITY GATE verdict (if present) so the read-only
    # plan reflects the executable local gate evidence. Never fabricated: loaded
    # from the machine-written results/run/local-quality-gate.json artifact.
    recorded_local = load_verdict()
    if recorded_local is not None:
        store.record("local_gate", recorded_local.to_dict())

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


def deliver(
    run_id: str,
    requirement: str = "qa-automation",
    mode: str = "NEW_AUTOMATION",
    execute: bool = False,
    remote: str = "origin",
    test_file: str = "",
) -> int:
    """PRODUCTION commit/push: CommitPlanner -> local_gate_fresh -> GitDelivery.

    Resumes the named run's state (from its append-only log), hydrates the recorded
    LOCAL QUALITY GATE verdict, and invokes the kernel delivery path. Without
    `--execute` this is a dry-run (no git mutation). With `--execute`, a real
    commit + push happen ONLY when the plan is safe (LOCAL GREEN + fresh evidence +
    valid feature/fix branch + matching fingerprint). Any RED/stale/missing gate
    refuses the delivery.
    """
    store = StateStore.resume(run_id)
    if not store.resumed:
        print(f"[deliver] ERROR: no run log for run_id={run_id!r}; nothing to deliver.")
        return 2
    recorded = load_verdict()
    if recorded is not None and not store.get("local_gate"):
        store.record("local_gate", recorded.to_dict())

    plan_kwargs = {"test_file": test_file} if test_file else {}
    kernel = Kernel(store=store)
    attempt = kernel.deliver(
        requirement=requirement,
        automation_mode=mode,
        push=True,
        dry_run=not execute,
        remote=remote,
        **plan_kwargs,
    )
    print("[deliver] " + json.dumps(attempt.to_dict(), indent=2, sort_keys=True))
    if attempt.delivered:
        print(f"[deliver] DELIVERED: {attempt.commit_hash} pushed to {remote}.")
        return 0
    if attempt.dry_run and not any(r.startswith("unsafe_plan") for r in attempt.reasons):
        print("[deliver] DRY-RUN: plan safe; commit/push validated, not executed.")
        return 0
    print("[deliver] REFUSED: " + "; ".join(attempt.reasons or ["plan unsafe"]))
    return 1


def local_gate(
    out: str = "results/run/local-quality-gate.json",
) -> int:
    """Execute the LOCAL QUALITY GATE (deterministic, read-only git-wise).

    Runs pytest, architecture validation, the deterministic machine dry-run and
    a branch-policy check; also validates executed Robot+Allure artifacts with
    the CI gate when they exist. Writes local-quality-gate.json and exits
    0 = GREEN / 1 = RED. GREEN is the ONLY authorizer of COMMIT/PUSH and its
    evidence (worktree fingerprint + branch + HEAD) is bound to the CURRENT
    change set — a stale GREEN can never authorize new changes.
    """
    verdict = run_local_gate()
    artifact = export_verdict(verdict, Path(out))
    print("[local-gate] " + json.dumps(verdict.to_dict(), indent=2, sort_keys=True))
    if verdict.green:
        print(
            f"[local-gate] GREEN: local quality gate satisfied for {verdict.branch} "
            f"@{verdict.head[:12]}. Evidence artifact: {artifact}"
        )
        return 0
    print(
        f"[local-gate] RED: local quality gate FAILED for {verdict.branch!r}. "
        "NO commit/push is authorized.",
    )
    for reason in verdict.reasons:
        print(f"[local-gate]   - {reason}")
    return 1


def ci_gate(
    output_xml: str,
    allure_dir: str,
    branch: str = "",
    commit: str = "",
    out: str = "results/run/ci-quality-gate.json",
) -> int:
    """Evaluate the REAL executed artifacts and emit a deterministic CI verdict.

    Parses the Robot output.xml + Allure results produced by an execution (local
    or inside the Jenkins container) and writes ci-quality-gate.json. Exit codes:
    0 = GREEN, 1 = RED (unusable/non-clean artifacts), 2 = missing evidence.
    The optional branch/commit cross-check enforces the autonomous QA branch
    contract when the Jenkins checkout evidence is supplied.
    """
    gate = CIQualityGate()
    result = gate.evaluate(
        output_xml=output_xml,
        allure_dir=allure_dir,
        branch=branch or None,
        commit=commit or None,
    )
    gate.export(result, Path(out))
    print("[ci-gate] " + json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.status == "GREEN":
        print("[ci-gate] GREEN: executed artifacts are clean and parity-verified.")
        return 0
    if result.status == "UNVERIFIED":
        print("[ci-gate] UNVERIFIED: no executed evidence to judge.")
        return 2
    print("[ci-gate] RED: non-clean run or unusable artifacts — CI gate FAILED.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="orchestra")
    sub = parser.add_subparsers(dest="cmd")

    dry = sub.add_parser("dry-run", help="simulate the machine with mock evidence")
    dry.add_argument("--mode", default="NEW_AUTOMATION")
    dry.add_argument("--scope", default="FULL_REGRESSION")

    sub.add_parser("arch", help="read-only architecture validation")

    lg = sub.add_parser(
        "local-gate",
        help="run the executable LOCAL QUALITY GATE; exit 0 GREEN / 1 RED "
        "(GREEN is the only commit/push authorizer, bound to the current change set)",
    )
    lg.add_argument("--out", default="results/run/local-quality-gate.json")

    cg = sub.add_parser(
        "ci-gate",
        help="evaluate Robot + Allure artifacts and emit the CI quality verdict (exit 0 GREEN / 1 RED / 2 UNVERIFIED)",
    )
    cg.add_argument("--output-xml", default="results/run/output.xml")
    cg.add_argument("--allure-dir", default="results/run/allure-results")
    cg.add_argument("--branch", default="", help="Jenkins checked-out branch (evidence cross-check)")
    cg.add_argument("--commit", default="", help="Jenkins checked-out commit SHA (evidence cross-check)")
    cg.add_argument("--out", default="results/run/ci-quality-gate.json")

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

    dl = sub.add_parser(
        "deliver",
        help="PRODUCTION commit/push: CommitPlanner -> local_gate_fresh -> "
        "GitDelivery (dry-run unless --execute and the plan is safe)",
    )
    dl.add_argument("--run-id", required=True, help="run whose state log is resumed")
    dl.add_argument("--requirement", default="qa-automation")
    dl.add_argument("--mode", default="NEW_AUTOMATION", choices=[
        "REGRESSION", "NEW_AUTOMATION", "AUTOMATION_ENHANCEMENT", "AUTOMATION_FIX",
    ])
    dl.add_argument("--test-file", default="", help="requirement-owned test file")
    dl.add_argument("--remote", default="origin")
    dl.add_argument("--execute", action="store_true",
                    help="perform a REAL commit + push when the plan is safe")

    args = parser.parse_args(argv)
    if args.cmd == "dry-run":
        return dry_run(args.scope, args.mode)
    if args.cmd == "arch":
        return architecture_validate()
    if args.cmd == "local-gate":
        return local_gate(out=args.out)
    if args.cmd == "ci-gate":
        return ci_gate(
            output_xml=args.output_xml,
            allure_dir=args.allure_dir,
            branch=args.branch,
            commit=args.commit,
            out=args.out,
        )
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
    if args.cmd == "deliver":
        return deliver(
            run_id=args.run_id,
            requirement=args.requirement,
            mode=args.mode,
            execute=args.execute,
            remote=args.remote,
            test_file=args.test_file,
        )
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
