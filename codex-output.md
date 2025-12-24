Added an ASCII iteration progress bar to the keepalive PR summary table so readers can see loop progress at a glance, and updated the keepalive loop tests to assert the new row formatting. This is implemented in ` .github/scripts/keepalive_loop.js` and exercised in ` .github/scripts/__tests__/keepalive-loop.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Next steps you may want:
1) Decide whether to surface autofix attempt/outcome data in PR comments once the workflows expose those values; I can wire that into `scripts/build_autofix_pr_comment.py`.