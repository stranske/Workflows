Improved placeholder handling so placeholder-only Scope/Tasks/Acceptance sections no longer count as real content, and added coverage to lock in missing-section detection. This keeps missing sections visible to the system while avoiding false “present” signals in `.github/scripts/issue_scope_parser.js` and ensures `buildIssueContext` surfaces warnings when placeholders are used.

Details
- Updated `.github/scripts/issue_scope_parser.js` to treat placeholder-only content as not present for `analyzeSectionPresence`.
- Added placeholder-specific tests in `.github/scripts/__tests__/issue_scope_parser.test.js`.
- Added placeholder-missing coverage in `.github/scripts/__tests__/issue_context_utils.test.js`.

Tests
- `node --test .github/scripts/__tests__/issue_scope_parser.test.js .github/scripts/__tests__/issue_context_utils.test.js`

Notes
- `codex-prompt.md` has existing uncommitted changes (progress/checkbox resets). I didn’t modify it this round; let me know if you want me to update/commit it.

Next steps
1) Update the source issue to add `Scope`, `Tasks`, and `Acceptance Criteria` sections, then re-run the PR body sync/keepalive.