Added a fallback so keepalive comments still include Scope/Tasks/Acceptance with placeholders even when the source issue omits those sections, and covered it with a new fixture-based test.

- `scripts/keepalive-runner.js` now prefers real sections but falls back to placeholder extraction when none are found, preventing the keepalive comment from being skipped.
- `tests/workflows/fixtures/keepalive/missing_sections.json` simulates an unstructured PR body.
- `tests/workflows/test_keepalive_workflow.py` asserts the placeholder headings and checklist lines are present and dispatch occurs.

Tests:
- `python -m pytest tests/workflows/test_keepalive_workflow.py -k "sections_missing"`

Note: `codex-prompt.md` was already modified in the working tree and was left untouched.

If you want a broader check, you can run:
1) `python -m pytest tests/workflows/test_keepalive_workflow.py`