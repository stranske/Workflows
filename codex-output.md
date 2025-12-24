Added fixture-backed PR/issue bodies to make the keepalive loop and verifier context tests more realistic, and wired the tests to consume those fixtures for better coverage of real-world markdown. Changes are in `.github/scripts/__tests__/keepalive-loop.test.js`, `.github/scripts/__tests__/agents-verifier-context.test.js`, `.github/scripts/__tests__/fixtures/pr-body.md`, `.github/scripts/__tests__/fixtures/issue-body-open.md`, and `.github/scripts/__tests__/fixtures/issue-body-closed.md`.

AGENTS.md note: I didn’t find `AGENTS.md` under `/home/runner/work/Workflows/Workflows`. The closest docs are the `agents/*.md` files.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-loop.test.js .github/scripts/__tests__/agents-verifier-context.test.js`

If you want broader validation, you could:
1) Run the full Node test set: `node --test .github/scripts/__tests__/*.test.js`
2) Run the overall test suite via your usual CI entrypoint (`npm test` or repo standard)