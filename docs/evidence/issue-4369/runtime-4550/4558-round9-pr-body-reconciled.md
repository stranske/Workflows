Closes #4557

**Acceptance remains incomplete.** Both exact full-suite commands now pass on one immutable published main revision, and the final subscription payload is merged with byte equality. The retained Maint 68 producer's automation origin is still unproved, and #4551's upstream verifier remains non-PASS.

This PR retains acceptance evidence and adds read-only inventory replay for the exact Maint 68 and Maint 71 workflow paths. The observer validates pagination, workflow identity and bounds while keeping dispatch origin unknown and chain acceptance false. Regression tests bind salvaged-fix receipts to native Git inventories and reject incomplete or substituted producer/merger inventories. The temporary Selftest executor is absent from the final diff.

## Validation

GitHub-hosted `ubuntu-latest`, runner `GitHub Actions 1004686100`, tested published main **`0a06f1976db1dd7eb12853f493a3371ee4736bcf`**. That revision contains required ancestor `b21fae85fe4f79e72c4133c29a3814b9d5950c3a` and merged #4551 head `154858c48424d7aa30c9edaf22ee3edb90066c5d`.

| Issue-named command | Exit | Bound | Wall time |
| --- | --- | --- | --- |
| `node --test .github/scripts/__tests__/*.test.js` | 0 | 600s | 27.735s |
| `python3 -m pytest -q tests/` | 0 | 1800s | 1299.060s |

[Run 42523162606](https://github.com/stranske/Workflows/actions/runs/42523162606): Node 3,789 passed / 1 skipped; Python 50,842 passed / 25 skipped / 3 xfailed. Both downloaded complete raw-log hashes match their receipts. Node 24.22.2 and repository-selected Python 3.14.10 executable paths are retained.

The retained `cmp` command exits 0 for source `bbfc6ae604c8e8c4021138c5efe964a368482957` and consumer main at actual PR 2486 merge **`1ff9e11cd51a456333c626cb354543b63202bef6`**. Both files have blob `71a4c84cf9ba590d1686f3a5bca80d1cf318a8f2`; the tested main revision has that same source blob.

Focused keepalive validation: direct Node observer tests **32 passed**; Python lifecycle tests **71 passed**; both retained-inventory CLI replays exit **0**. The complete 182-run inventory through **2026-11-09T01:23:40Z** has no Maint 68 producer and one Maint 71 dispatch, which supplies no qualifying causal chain. See the round-9 validation record and receipts. No protected file was edited.

## Acceptance tracking

- [x] Record check date, exact commands, bounds, and the original three-attempt/60-minute stop rule before implementation.
- [x] Prove published-main ancestry and salvaged #4551 fix inclusion.
- [x] Retain both exact suite passes on that same revision with complete logs and execution receipts.
- [x] Read historical restricted-runner logs as diagnostic leads; no source symbol was repaired from them.
- [x] Retain source → plan → candidate → Maint 71 → actual PR 2486 merge lineage and matching payload receipts.
- [x] Retain exit-0 merged-byte comparison and exact-head Maint 71 disposition: zero active findings, excluding discussion 4434491702.
- [x] Retain all 49 issue-4369 comments through **2026-11-08T21:30:03.551859Z**, with an explicit empty second page.
- [ ] Authenticate the producer's automation origin and observe the qualifying next automation-started Maint 68 → Maint 71 chain. No Maint 68 run occurred in the retained 20:46:00–21:31:19Z task interval. No Maint 68 or Maint 71 dispatch was performed by this work.
- [ ] Clear the existing upstream verification disposition. [Run 42522535899](https://github.com/stranske/Workflows/actions/runs/42522535899) completed as an Actions job but retained OpenAI `UNVERIFIABLE_INPUT` (`ValidationError` parsing the response), Anthropic `CONCERNS`, and a terminal `needs-human` disposition. That result is preserved without claiming a passing gate.

The source issue remains incomplete; no merge/promotion gate, writer lock, or automation schedule was bypassed. Full details and linked receipts are in the validation record's final operational section.

<!-- pr-preamble:start -->
<!-- meta:issue:4557 -->
> **Source:** Issue #4557

Closes #4557

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
This follow-up was split from #4550 after PR #4551 was reduced to its finished fixture repairs, Maint 71 subject-refusal diagnostics, and partial evidence. Full-suite acceptance and final subscription payload delivery remain unproved. At assessment, #4550 and PR #4551 are open.

The original narrative and full-suite logs remain readable at commit `b2949e496e18a5194d70cde14a01ca3781ca132e` under `docs/evidence/issue-4369/runtime-4550/`; they were removed from the reduced PR. Examples include `supported-exact-node-02fbe3f74.log` (CI Selftest run 42486833507; full Node suite exit 0 at 02fbe3f74), `coding-stdin-node-full.log`, and `coding-stdin-python-full.log` (restricted-runner diagnostics: 9 failing Node files and Python timing out at 180 seconds). These do not establish acceptance on the final revision.

<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent

### Related Issues/PRs
- [#4550](https://github.com/stranske/Workflows/issues/4550)
- [#4551](https://github.com/stranske/Workflows/issues/4551)
<!-- Updated WORKFLOW_OUTPUTS.md context:end -->

#### Tasks
- [x] Inspect #4550, PR #4551, and main to identify one immutable published main descendant containing `b21fae85fe4f79e72c4133c29a3814b9d5950c3a` and the salvaged PR #4551 fixes. Record the ancestry and fix-inclusion evidence under `docs/evidence/issue-4369/runtime-4550/`; if those fixes are not on main, complete their delivery through the existing review, merge, and verification gates before choosing the acceptance revision.
- [x] Inspect the CI Selftest workflow and run 42486833507 to identify a supported non-local runner. Before changing code, record the check date, acceptance commands, explicit execution bounds, and stop rule in `docs/evidence/issue-4369/2026-11-08-validation.md`: stop at the first unresolved step after three failed attempts at that step or 60 minutes, whichever occurs first.
- [x] On that supported non-local runner, check out the selected immutable revision and run `node --test .github/scripts/__tests__/*.test.js` and `python3 -m pytest -q tests/`. Retain complete logs, checkout SHA, runner identity, interpreter paths, explicit bounds, timings, and exit codes under `docs/evidence/issue-4369/runtime-4550/`. Resolve `python3` to the repository-selected environment when applicable and record its executable path.
- [x] Read `coding-stdin-node-full.log` and `coding-stdin-python-full.log` at `b2949e496e18a5194d70cde14a01ca3781ca132e` as diagnostic leads only. Reproduce the first remaining failure on the supported runner before changing its named file or symbol; rerun the affected command after a repair. Record the first unresolved step when the stop rule trips. If code changes, select a published main revision containing the repair and rerun both full suites on that same revision.
- [ ] Read, without dispatching, the next automation-started `.github/workflows/maint-68-sync-consumer-repos.yml` run and the `.github/workflows/maint-71-merge-sync-prs.yml` run that causally follows it. For Portable-Alpha-Extension-Model PR 2486 or its causal successor, retain run identifiers and the source, plan, candidate, actual merge SHA, and `tools/subscription_llm.py` blob receipts under `docs/evidence/issue-4369/runtime-4550/`. Establish causality from the recorded artifacts rather than timing alone.
- [x] Compare the final `templates/consumer-repo/tools/subscription_llm.py` bytes at the recorded source revision with `tools/subscription_llm.py` on Portable-Alpha-Extension-Model consumer main at the recorded merge SHA. Retain both revision identities, blob receipts, the comparison command, and its exit code under `docs/evidence/issue-4369/runtime-4550/`.
- [x] Update `docs/evidence/issue-4369/2026-11-08-validation.md` with the exact merged-byte comparison, the disposition of applicable exact-head Maint 71 findings excluding discussion 4434491702, and a fresh, complete issue-4369 comment observation through an explicit UTC boundary. Record pagination completeness and link the underlying receipts.

#### Acceptance criteria
- [x] `node --test .github/scripts/__tests__/*.test.js` and `python3 -m pytest -q tests/` both exit 0 on the same recorded immutable published main revision containing the required ancestor and salvaged PR #4551 fixes; complete logs and runner, interpreter, bound, timing, and exit-code receipts exist under `docs/evidence/issue-4369/runtime-4550/`.
- [x] A retained byte-comparison command exits 0 for the final source `templates/consumer-repo/tools/subscription_llm.py` and Portable-Alpha-Extension-Model consumer-main `tools/subscription_llm.py` at the recorded merge SHA, with both source and consumer blob receipts retained.
- [ ] The retained automation-started Maint 68 → Maint 71 receipt chain identifies the source, plan, candidate, Portable-Alpha-Extension-Model PR 2486 or its causal successor, and actual merge SHA; no manual Maint 68 or Maint 71 dispatch was used.
- [x] `docs/evidence/issue-4369/2026-11-08-validation.md` records the byte comparison, applicable exact-head Maint 71 finding dispositions excluding discussion 4434491702, and complete issue-4369 comment observation through a stated UTC boundary.

<!-- auto-status-summary:end -->

## Post-push review

At 2026-11-08T21:39Z, the unchanged head `ff8ff901efee7f3c5eecc41b42b615210f1db2c5` had a passing required `summary` check. Review-thread pagination was complete. Four active comments rated Trivial remain unresolved and deferred under the owner instruction against review-nit work during an acceptance push:

- Writer-release local-path metadata: discussion 4507873384.
- Archive-level retained-copy/hash-manifest metadata for the supplementary artifact inventory: discussion 4507873387.
- Per-page IDs in the supplementary 4558 comment snapshot: discussion 4507873390. The final primary 4557 snapshot already retains page IDs and an empty second page.
- MD041 on the retained verbatim rejected-comment draft: discussion 4507873393.

The required complete suite logs and their independently verified hashes are retained. No merge was attempted, and these comments were not marked resolved or waived.
