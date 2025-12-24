Added coverage for keepalive loop summary behavior in `.github/scripts/__tests__/keepalive-loop.test.js` to exercise iteration advancement, failure reset, and pause/label handling for repeated failures.

**Changes**
- Added tests for `updateKeepaliveLoopSummary` success path (iteration bump, cleared failure, Codex run details).
- Added tests for repeated failure stop behavior, including pause messaging and `needs-human` label call.

**Tests**
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Noticed an untracked `codex-prompt.md` in the repo. Should I leave it as-is or clean it up?