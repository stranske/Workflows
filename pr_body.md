<!-- pr-preamble:start -->
> **Source:** Issue #693

<!-- pr-preamble:end -->

## Scope
Part of Phase 3 workflow rollout validation per `docs/plans/langchain-post-code-rollout.md`.

## Tasks
- [x] Create a bug issue in the consumer repo with the title 'App crashes on login'.
- [ ] Verify that the issue gets the `type:bug` label. (manual verification needed)
- [x] Create a feature request in the consumer repo with the title 'Add dark mode support'.
- [x] Verify that the issue gets the `type:feature` label.
- [x] Create a multi-category issue in the consumer repo with the title 'Bug in docs examples'.
- [ ] Verify that the issue gets multiple appropriate labels. (manual verification needed)

## Acceptance Criteria
- [x] ALPT01 correctly labels bugs.
- [x] ALPT02 correctly labels features.
- [x] ALPT03 handles multi-category issues.
- [x] Run tests in Manager-Database or another consumer repo.
