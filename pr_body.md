<!-- pr-preamble:start -->
> **Source:** Issue #582

<!-- pr-preamble:end -->

## Scope
The new label-triggered verifier workflow needs to be documented and rolled out to all consumer repositories for consistent behavior across the ecosystem.

## Tasks
- [x] Create `verify:checkbox` label in all 6 consumer repos
- [x] Create `verify:evaluate` label in all 6 consumer repos (for future use)
- [x] Create `verify:compare` label in all 6 consumer repos (for future use)
- [ ] Sync updated `agents-verifier.yml` to consumer repos via sync workflow
- [x] Update `docs/WORKFLOW_GUIDE.md` with verifier usage section
- [x] Add verifier troubleshooting guide
- [x] Update consumer repo READMEs to mention verify labels

## Acceptance Criteria
- [x] All 6 consumer repos have verify labels created
- [ ] Updated workflow synced to all consumer repos
- [x] WORKFLOW_GUIDE.md includes:
- [x] - How to trigger verification
- [x] - What each mode does
- [x] - Expected outputs
- [x] - When to use each mode
- [x] Troubleshooting guide covers common issues
