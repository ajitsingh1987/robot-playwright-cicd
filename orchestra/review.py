"""Deterministic reviewer-verdict parsing from the REAL agent result text.

A verdict is NEVER hardcoded. It is parsed from the text the reviewer agent actually
produced. The parser is intentionally conservative: a REJECT (or the presence of any
reject marker) wins over a pass so that a rejected review can never be mis-read as an
approval. Only an explicit approve/pass verdict marker yields APPROVED; anything
ambiguous is UNKNOWN (which is not a pass).
"""
from __future__ import annotations

import re

_REJECT_RE = re.compile(r"\bREJECT(?:ED)?\b", re.IGNORECASE)
_APPROVE_RE = re.compile(r"\bAPPROVE[DH]?\b", re.IGNORECASE)
_VERDICT_RE = re.compile(
    r"(?:\b[Vv]erdict\b\s*[:*-]*\s*)(APPROVE[DH]?|PASS|REJECT(?:ED)?)",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"(?:\b(?:Decision|Status|Outcome)\b\s*[:*-]*\s*)(APPROVE[DH]?|PASS|REJECT(?:ED)?)",
    re.IGNORECASE,
)

_PASS_MARKERS = ("PASS", "APPROVED", "APPROVE")


def _verdict_from_word(word: str) -> str:
    w = (word or "").upper()
    if w.startswith("REJECT"):
        return "REJECT"
    if w in _PASS_MARKERS:
        return "APPROVED"
    return "UNKNOWN"


def parse_review_verdict(text: str) -> str:
    """Return one of: APPROVED, REJECT, UNKNOWN (never raises)."""
    if not text or not text.strip():
        return "UNKNOWN"

    # 1. Explicit structured verdict/decision markers are authoritative.
    for pattern in (_VERDICT_RE, _DECISION_RE):
        m = pattern.search(text)
        if m:
            return _verdict_from_word(m.group(1))

    # 2. Conservative fallback: any reject marker wins over a passing marker.
    if _REJECT_RE.search(text):
        return "REJECT"
    # 3. An explicit approve marker without any reject marker.
    if _APPROVE_RE.search(text):
        return "APPROVED"
    # 4. Ambiguous -> UNKNOWN (never assume a pass).
    return "UNKNOWN"
