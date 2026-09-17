"""Executable orchestration kernel (Phase 2).

Converts the prose orchestration contract (AGENTS.md, qa-orchestrator.md) into a
deterministic, state-machine-driven layer. The kernel owns workflow truth, state
transitions, gates and the healing counter; LLM agents are delegated for cognitive
sub-stages and their recorded evidence is verified by the kernel.
"""
