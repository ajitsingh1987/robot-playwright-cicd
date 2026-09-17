"""HealingCounter: Orchestrator-owned healing attempt tracker (max 3)."""
from __future__ import annotations

from .config import settings
from .state import StateStore


class HealingCounter:
    MAX_HEALING_ATTEMPTS = min(settings.MAX_HEALING_ATTEMPTS, 3)

    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._attempts = int(store.get("healing_attempts", 0) or 0)

    def attempts(self) -> int:
        return self._attempts

    def can_heal(self, automation_mode: str) -> bool:
        return automation_mode != "REGRESSION" and self._attempts < self.MAX_HEALING_ATTEMPTS

    def healable(self, category: str) -> bool:
        """Whether a failure of `category` may be routed to HEALING at all.

        FLAKY / ENVIRONMENT_FAILURE / APPLICATION_DEFECT / UNKNOWN are never healed.
        Only AUTOMATION_DEFECT / TEST_DATA_DEFECT are healable, subject to the
        automation-mode + cap enforced by `can_heal`.
        """
        from .failure import HEALABLE  # local import avoids a circular dependency

        return category in HEALABLE

    def can_heal_failure(self, automation_mode: str, category: str) -> bool:
        """True only when BOTH the category is healable AND mode/cap allow healing.

        A flaky/environment failure therefore never reaches HEALING, even in an
        AUTOMATION mode with attempts remaining.
        """
        return self.healable(category) and self.can_heal(automation_mode)

    def exhausted(self) -> bool:
        return self._attempts >= self.MAX_HEALING_ATTEMPTS

    def increment(self) -> int:
        """Increment and persist. Caller must ensure automation-mode + cap applied."""
        if self._attempts >= self.MAX_HEALING_ATTEMPTS:
            raise RuntimeError("Healing attempts exhausted; 4th attempt forbidden.")
        self._attempts += 1
        self._store.record("healing_attempts", self._attempts)
        return self._attempts

    def remaining(self) -> int:
        return max(0, self.MAX_HEALING_ATTEMPTS - self._attempts)
