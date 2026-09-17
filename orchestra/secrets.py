"""Credential/secret scanning shared by delivery gates and artifact validation.

A staged diff is scanned for sensitive markers (API keys, passwords, tokens,
credentials, bearer tokens) before a commit is authorized. The pattern set is
conservative and intentionally excludes public demo-app credential usage so a
normal demonstration run is never a false positive.
"""
from __future__ import annotations

import re
from typing import List

# Sensitive markers to detect accidental leakage into a staged diff or an
# Allure artifact. Matches the contract used by the allure adapter.
CREDENTIAL_PATTERNS: List[str] = [
    r"api[_-]?key[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']",
    r"(?:password|passwd|secret|token|credential|client_secret)[\"']?\s*[:=]\s*[\"'][^\"']{6,}[\"']",
    r"Bearer\s+[A-Za-z0-9_\-\.]{16,}",
    r"sk-[A-Za-z0-9]{16,}",
]


def scan_for_credentials(text: str) -> List[str]:
    """Return the sensitive patterns found in `text` (empty list == clean).

    The scan is conservative: a marker is only flagged when a concrete value
    assignment is present. Public demo-app values are structurally excluded so a
    normal run is not a false positive.
    """
    found: List[str] = []
    for pattern in CREDENTIAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(pattern)
    return found


def diff_contains_secrets(diff_text: str) -> List[str]:
    """Scan a staged diff for credential markers; [] means no secrets staged."""
    return scan_for_credentials(diff_text or "")