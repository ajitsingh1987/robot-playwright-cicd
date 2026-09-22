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
