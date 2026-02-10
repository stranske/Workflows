<!--
needs-human:
Label: needs-human
Blocked by workflow protection: update .github/workflows/keepalive.yml and .github/workflows/autofix.yml to add explicit `if:` guards on every step/job that posts a PR comment or PR review so they cannot run when suppression is active. Use the suppression output key `should_post_review` (from .github/scripts/should-post-review.js) to gate the posting steps.

Workflow: .github/workflows/keepalive.yml
- Workflow file not found in repository.

Workflow: .github/workflows/autofix.yml
- No unguarded PR comment/review posting steps detected (or posting steps are already guarded).
-->
