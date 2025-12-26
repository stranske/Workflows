Added a prompt-focused unit test to lock in the “use CI results, no local test runs” guidance and reconciled the PR task checklist to reflect the completed CI-query integration. Updated the checklist in `codex-prompt.md` after running the relevant tests.

Tests:
```
node --test .github/scripts/__tests__/verifier-ci-query.test.js .github/scripts/__tests__/agents-verifier-context.test.js .github/scripts/__tests__/verifier-acceptance-prompt.test.js
```

Next steps:
1) Run the verifier workflow on an actual merged PR to confirm live CI results are fetched.
2) Confirm no post-merge false negatives appear once CI-backed verification runs in the workflow.