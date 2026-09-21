# Jenkins Webhook Acceptance Test Marker

This file exists only to produce one harmless commit on `feature/qa-auto-admin`
so the real GitHub push -> webhook -> Jenkins path can be validated.

- Purpose: prove Jenkins selects the pushed branch/SHA (`feature/qa-auto-admin`),
  not the stale `feature/qa-auto-orangehrm-automation`.
- Impact: none. No test, Docker stage, or pipeline stage depends on this file.
- Safe to delete after verification.
