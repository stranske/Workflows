# Keepalive progress-review comment guard

The [Workflows keepalive loop](../.github/workflows/agents-keepalive-loop.yml)
runs `progress-review` when `evaluate` selects `action=review`. The
`review_guard` step runs
[`should-post-review.js`](../.github/scripts/should-post-review.js) against
`review_result.json` and writes `should_post_review` to `GITHUB_OUTPUT`.

The PR comment step checks
`steps.review_guard.outputs.should_post_review == 'true'`. The
[result evaluator](../.github/scripts/keepalive_review_guard.js) suppresses
comments for invalid, empty or suppressed review results. A posted
`STOP` recommendation also attempts to remove the concrete agent label.
Inspect the review and guard steps when a comment is absent.
The consumer [Gate Followups](../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml)
uses its own keepalive finish path.

The original implementation recipe used `id: review_gate` and
`steps.review_gate.outputs.should_post_review == 'true'`. In the active
workflow the step ID is `review_guard`.
