Added a focused Node test to enforce required Scope/Tasks/Acceptance sections in the agent issue templates, then marked the PR task checkboxes complete after verifying the templates. Updates are in `.github/scripts/__tests__/issue_template_sections.test.js` and `codex-prompt.md`.

Tests:
- `node --test .github/scripts/__tests__/issue_template_sections.test.js`

Next steps:
1. Run the broader JS test suite: `node --test .github/scripts/__tests__/*.test.js`