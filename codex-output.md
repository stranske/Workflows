Extended agents guard coverage with rename blocking and pull_request_target safety validation tests in `.github/scripts/__tests__/agents-guard.test.js`. Added a new negative test for unsafe checkout/secrets usage and a fatal-rename case to strengthen immutable surface checks.

Tests run: `node --test .github/scripts/__tests__/agents-guard.test.js`

Note: `codex-prompt.md` is still modified but unstaged.

Next steps:
1. Run the full suite: `node --test .github/scripts/__tests__/*.test.js`
2. Continue with the next Round 1 task (keepalive guard utils coverage) if needed