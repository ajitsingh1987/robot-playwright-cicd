# Jenkins Webhook Acceptance Test Marker

This file exists only to produce one harmless commit on `feature/qa-auto-admin`
so the real GitHub push -> webhook -> Jenkins path can be validated.

- Purpose: prove Jenkins selects the pushed branch/SHA (`feature/qa-auto-admin`),
  not the stale `feature/qa-auto-orangehrm-automation`.
- Impact: none. No test, Docker stage, or pipeline stage depends on this file.
- Safe to delete after verification.

## Verification run 2 (polling fix)

- Marker commit for the acceptance run after the polling fix. The last
  successful build (#35) recorded the wildcard SCM `*/feature/qa-auto-*` +
  `*/fix/qa-auto-*`, so `WorkflowJob.poll` must now detect this push.
- Expected: this push triggers `Robot-Playwright-Sanity` on
  `feature/qa-auto-admin` at this commit's SHA.
