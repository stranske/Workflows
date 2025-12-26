Added coverage to confirm the verifier context renders CI run links using the API `url` fallback when `html_url` is missing, and updated the PR task checklist to reflect completed CI-query work in `codex-prompt.md`.

- Added a new verifier-context test for the run URL fallback in `.github/scripts/__tests__/agents-verifier-context.test.js`.
- Updated task completion/progress in `codex-prompt.md`.

Tests:
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1) Run the verifier workflow against an actual merged PR to confirm live CI results are fetched (requires CI/network access).
2) Verify the verifier no longer produces false negatives once CI-backed validation is exercised.