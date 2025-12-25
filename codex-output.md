Added a keepalive loop test that validates attention comment formatting for codex-type failures, including run link and truncated agent output, covering the “various error types” PR comment formatting task. Updated test is in `.github/scripts/__tests__/keepalive-loop.test.js`.

Tests run: `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Commit: `test: cover keepalive attention comment formatting`

Note: `codex-prompt.md` was already modified and remains untouched.