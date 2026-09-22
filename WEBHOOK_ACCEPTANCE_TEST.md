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

## Verification run 3 (Multibranch conversion)

- Marker commit for the acceptance run after converting `Robot-Playwright-Sanity`
  from a single Pipeline-from-SCM job to a GitHub Multibranch Pipeline. The root
  cause of the "no build" deltas was the git-plugin SCM polling decision on a
  `CpsScmFlowDefinition` (SCMRevisionState$None -> "No changes" -> no evaluation).
- Now the job discovers every `feature/qa-auto-*` / `fix/qa-auto-*` branch via the
  GitHub Branch Source and is triggered ONLY by the repository webhook.
- Expected: this push makes the GitHub webhook deliver the event and
  `Robot-Playwright-Sanity` auto-builds `feature/qa-auto-admin` at this commit's SHA.

## Verification run 3b (Multibranch re-verify)

- Re-verification marker for the Multibranch path. Run 3 build #2 was RED only
  because the public OrangeHRM demo server timed out rendering one login page
  (41/42 passed); the webhook match and correct-SHA checkout were confirmed.
- Expected: this push is matched by branch discovery and auto-builds
  `feature/qa-auto-admin` at this commit's SHA, targeting a GREEN ci-gate.

## Verification run 4 (guard commit)

- Commit `9fb9782` landed the multibranch regression-guard changes
  (`orchestra/ci_quality.py`, `orchestra/jenkins_policy.py` and their tests).
  The webhook matched and Build #4 checked out exactly `9fb9782`, proving the
  trigger path again for a code (non-marker) commit.
- Build #4 result: RED only because the public OrangeHRM demo server timed out
  rendering one login page again (41/42 passed); ci-gate deterministically RED.
- Turnaround marker for the final re-verification: this push must match and
  auto-build `feature/qa-auto-admin` at this commit's SHA, targeting a GREEN ci-gate.
