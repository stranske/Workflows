Normalized keepalive loop checklist parsing so bullet-only Tasks/Acceptance lines are treated as checkboxes, then used the normalized content for counting and the task appendix to avoid false “no-checklists” stops. Added a regression test that covers the bullet-list scenario to confirm we now proceed when Gate is green. Changes are in `.github/scripts/keepalive_loop.js` and `.github/scripts/__tests__/keepalive-loop.test.js`.

Tests: `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Suggestions:
1) Run the full Node test suite if you want broader coverage.