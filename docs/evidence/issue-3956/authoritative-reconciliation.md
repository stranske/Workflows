# Authoritative coverage and mutation reconciliation — issue #3956

## Current acceptance repair readback (2026-11-07 UTC)

**Outcome 1: PARTIAL.** PR #4518 merged as
`5dd01ec8bbdd9a5dfdc9b4603a69ba3066039e44`, confirmed by a fresh main fetch.
That delivered revision restores the inline guards, removes only the helper-only
test, and retains the production OSError/checklist fixes, tests and evidence.
Every older statement below that main still contains the helper, #4518 remains
open, or inline restoration awaits #4401 is superseded historical readback.
Historical receipts and the independent-ranking limitation remain intact.

The real-input acceptance command is the fresh baseline extraction, current test
collection and retained-receipt audit below. Required commands were run first on
delivered main `5dd01ec8…`, before preparing this evidence-only repair. No local
virtual environment is selected; the owner-selected interpreter is
`/opt/anaconda3/bin/python3` (Python 3.12.2), with Node v24.3.0. This differs from
the separately identified hosted Python 3.14.10 runtime.

```sh
/opt/anaconda3/bin/python3 -m pytest tests/test_followup_issue_generator.py -q
# exit 0; 199 passed in 0.68s
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 tests passed; zero failures, cancellations or skips
git show 94d9f952dad19f4f8048ae82bb8301bc6baf6ef5:tests/test_followup_issue_generator.py > /tmp/issue4437-baseline-tests.py
/opt/anaconda3/bin/python3 -m pytest tests/test_followup_issue_generator.py --collect-only -q > /tmp/issue4437-collected-tests.txt
/opt/anaconda3/bin/python3 scripts/audit_followup_mutations.py --baseline-tests /tmp/issue4437-baseline-tests.py --collected-tests /tmp/issue4437-collected-tests.txt > docs/evidence/issue-3956/retained-mutation-audit.json
# exit 0; complete=true; problems=[]; 35 added functions; 45 added collected cases;
# 50 Python receipts and two original Node receipts
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_audit_followup_mutations.py -q
# exit 0; 66 passed in 0.41s
```

The regenerated [retained audit](retained-mutation-audit.json) is byte-identical
to the delivered audit (SHA256
`508d4eb29d4a37a1a6934d51c5b2b44993784ede1621d7dfc574fd324168cc78`).
All retained full RED/GREEN receipts were independently read in bounded groups:
Python indices 0–3, 4–9, 10–16, 17–22, 23–24, 25–29, 30–37, 38–43, 44–49,
then Node indices 0–1. Effective Python receipts 2 and 24 come from
`retained-mutation-unabridged-reruns.json`, as mapped by the auditor; their
historical abbreviated records remain preserved. Each effective receipt names
the selected case, exit-1 assertion failure and exit-0 restored single-case pass.
The mutation replacements reproduce their source hashes against accepted bytes;
Python source/test and Node source hashes match delivered main. Python indices
48 and 49 repeat the same case/mutation and are not counted as distinct cases.
These are independently inspected historical executions, not new mutation runs
or proof that every assertion in a multi-assertion case was independently killed.
The supplemental regression receipts elsewhere in this record remain separate
from this 45-case retained-test audit.

### Hosted accepted-source evidence and comparison gap

The actual bytes of [Selftest run 42381426360, artifact 13578515594](https://github.com/stranske/Workflows/actions/runs/42381426360/artifacts/13578515594)
were downloaded and inspected. Artifact metadata and `pytest-resources.json`
both bind the tested revision to delivered main `5dd01ec8…`; Python 3.14.10,
pytest 9.2.0 and coverage 7.17.2 were used. The exact job
`128429746865` passed 50,508 tests, with 27 skips and three xfails. The
argument builder and environment in that job reconstruct this command:

```sh
pytest -p ci_test_growth -m 'not quarantine and not slow' --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml --cov-report=xml:coverage.xml --cov-report=term-missing --cov-report=json:coverage.json -n 4 --dist=loadgroup
```

`runtimes/3.14/coverage.json` reports 851 statements, **0 missing statements**,
386 branch destinations and **1 missing destination** (`124 -> 126`), or
**1 missing unit** and 99.92% combined coverage. A unit is one entry in
`missing_lines` plus one entry in `missing_branches`; partial branch sites are
never substituted for missing destinations. ZIP SHA256 is
`fedd97c894cb8466ca28afe22ffef76d184f5bd79dd00ed538f84f3792528312`.
Exact revisions, configuration/source/test hashes, job/artifact identifiers,
command and counts are appended to [hosted-coverage-receipt.json](hosted-coverage-receipt.json),
preserving its older `f77be1eee…` receipt fields as history.

The inspected baseline `94d9f952dad19f4f8048ae82bb8301bc6baf6ef5` Selftest run
`38995688471`, job `117287656854`, uses Python 3.14.8, an explicit
workflow/verifier subset, no generator test file and no coverage flags. Its
artifact list is empty. It cannot be compared with the accepted canonical suite.
The connected commit-run wrapper filters PR runs and returned none for these
merge commits. GraphQL first/last check-suite pages are partial; an exact
`python ci / python 3.14` name filter returns zero baseline suites. This bounded
inspection does not establish that every possible baseline is unrecoverable.
CLI Actions discovery returned HTTP 403, core remaining 0, reset
2026-11-07 15:13:57 UTC. The exact pending discovery command is retained in the
JSON receipt. No replacement hosted run was launched. The comparable baseline
counts and measured difference remain **UNKNOWN**, not zero or approximately 60;
the focused local 222-unit measurement is not substituted.

### Existing #4401 branch reconciliation and remaining delivery

The existing `closer/issue-3956` branch was updated, without creating another PR,
from `9eaf43313c0e57ef964e4171f645985dca5742b8` to
`008ee6bd29004ed26a81d77a4a9dff318af1db34` at 14:54:26 UTC. Both add/add
conflicts preserve current main's newer authoritative record and local coverage
JSON. Its revision table now declares Role / Revision / Notes, addressing the
defect in `PRRT_kwDOQprj9M6zZ4AB`. Production, target tests and #4518's additional
evidence are preserved. Two existing SUPERSEDED annotations on historical helper
receipts are kept. Only obsolete conflicting document versions were discarded.
No other local `closer*/issue-4437` branch existed to integrate.

The 15:01:42 UTC post-push readback, after the seven-minute review floor,
reports #4401 OPEN, `isDraft=false`, unchanged head `008ee6bd…`, CLEAN, with
no pending or failing reported checks. The Gate comment identifies a docs-only
fast-pass; heavy checks were skipped. The three unresolved historical threads,
including the corrected revision-table thread, are now outdated; outdated status
does not establish requested settlement. This is not a complete expected-check
receipt or merge authorization. The existing reporter was attempted separately:

```sh
/opt/anaconda3/bin/python3 scripts/check_checks_reported.py --repo stranske/Workflows --pr 4401 --head 008ee6bd29004ed26a81d77a4a9dff318af1db34 --event pull_request --action synchronize --transport native-gh --output /tmp/issue4437-pr4401-checks.json
# exit 2; verdict=UNKNOWN; native-gh pulls/4401 discovery HTTP 403 (core rate limit)
```

Automatic approval review rejected both its prepared description update and resolution of the
corrected revision-table thread: `MCP tool call requires approval, but approval
policy is never`. Neither action succeeded; no merge was attempted. Existing
PR-body checked claims remain superseded by this record.

Blocking/drainable pair: the unresolved thread, pending/unaudited exact-head
gates and unavailable comparable baseline block final delivery; source-bound
receipt inspection and accepted-source artifact recovery proceeded while those
gates stayed closed. Stop rule: three failed attempts at the same step or
75 minutes from 14:48 UTC; no timed permit or lock was created.

- [x] Required Python/Node commands pass on identified delivered main.
- [x] Independently inspect all 50 Python/two original Node full receipts and regenerate the retained audit from fresh collection.
- [ ] Obtain comparable hosted baseline and accepted-source measurements with actual difference.
- [ ] Settle #4401's review, complete fresh existing gates, merge and verify delivered main.
- [ ] Record actual final delivery; ranking provenance remains explicitly limited.

## Superseded pre-#4518 delivery readback (2026-11-07 UTC)

Before the CLI fallback regression changes, checkout
`407b236b5d4c84f4f345c15872d60e186d2ba4bc` was inspected. The required
`gh pr view 4401 --repo stranske/Workflows --json
state,headRefOid,mergeStateStatus,reviewDecision,statusCheckRollup,mergeCommit,isDraft`
exited 1 connecting to `api.github.com`. Connected metadata still reports OPEN,
`draft=false`, `merged=false`, head `9eaf43313c0e57ef964e4171f645985dca5742b8`.
All three submitted reviews are COMMENTED. The non-outdated unresolved revision
table thread `PRRT_kwDOQprj9M6zZ4AB` remains the identified review blocker.
An immutable generator read at reported main base
`4928870982db3bc3b85c701b4cca2492128739b2` again returns blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00`, defining and calling the helper.
The first unchecked main-delivery criterion remains blocked on #4401 delivery;
the next local work verifies CLI fallback integration without replacing that repair.
No checked merge claim is accepted as evidence.

### CLI fallback integration validation (local, 2026-11-07)

`tests/test_followup_cli_fallback_contract.py` adds six supplemental cases:
`verification_comment`, `original_issue`, and `codex_log`, each failing at
`probe` and `read`. With real temporary input files, each case fails only the
selected input. Verification/issue fallbacks reach the inline guard as their
literal arguments; a blocked literal reports its source and prevents generation.
An unreadable optional log is omitted, while the other two files retain their
parsed contents. This preserves #4401's repair and the original 199-test file.

[cli-fallback-integration-proof.json](cli-fallback-integration-proof.json) maps
all six parameter IDs to full assertion-failing RED and restored GREEN outputs.
The mutation returns an unreadable-file diagnostic as content after OSError,
losing the literal fallback or forwarding an unreadable log to the guard. Each
case fails its exact scanned-input assertion (exit 1) and then passes against
restored source (exit 0). All six receipts were inspected without truncation.
Source revision is `407b236b5d4c84f4f345c15872d60e186d2ba4bc`, generator SHA256
`59393aa4e1c644bbbeab8309a980782c3bd3f40cc5c2590c37706b2ab0df7925`,
with the new test overlay bound by SHA256
`003bca7903bc0e41a584bce21c54f27961d2a63ad8cd070cbfd96c6935e29b40`.
Only temporary module copies were mutated. These supplemental receipts extend
the evidence index; the historical retained-test mapping is preserved separately.

Selected interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`
(Python 3.14.10), consistent with the repository's primary 3.14 runtime.
LangSmith's plugin remained enabled. Commands and results:

```sh
python -m pytest tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 0; 199 passed
python -m pytest tests/test_followup_issue_generator.py tests/test_followup_guard_contract.py tests/test_followup_cli_fallback_contract.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-cli-coverage.json
# exit 0; 212 passed; 99.92% combined local coverage
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one passing process-isolated file unit
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 individual cases passed; zero failed or skipped
ruff check tests/test_followup_cli_fallback_contract.py
# exit 0; all checks passed
black --line-length 100 tests/test_followup_cli_fallback_contract.py
# exit 0; file unchanged
```

Coverage JSON confirms 851 statements, zero missing statements, 386 branches,
one missing branch (`124 -> 126`). This focused local measurement supplies no
new hosted baseline, approximately 60-unit reduction, ranking provenance, or
main-delivery evidence. The unchecked source acceptance criteria remain pending.


The commit attempt is blocked before staging: `git add` for this test, its
receipt and this record exits 128 because `.git/index.lock` cannot be created
on the read-only filesystem. No commit, push, PR change, or merge was made.

The required repository-wide formatting check was also attempted:

```sh
BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

It produced no output for several minutes and was interrupted with exit 130.
The changed-file Black result above passed; this repository-wide result is
incomplete and does not satisfy the pre-commit gate. No acceptance checkbox was
changed on the strength of local results or the checked historical merge task.

### Earlier readbacks (historical)

Before the clean-payload regression changes, checkout `95be0640` was inspected.
The required `gh pr view 4401 --repo stranske/Workflows --json
state,headRefOid,mergeCommit,isDraft,statusCheckRollup` exited 1 connecting to
`api.github.com`. Connected metadata again reports OPEN, `draft=false`,
`merged=false`, head `9eaf43313c0e57ef964e4171f645985dca5742b8`, with no merge
date. All three reviews are COMMENTED. Thread `PRRT_kwDOQprj9M6zZ4AB` remains
unresolved and non-outdated; two other unresolved threads are outdated.
An immutable generator read at reported main base
`4928870982db3bc3b85c701b4cca2492128739b2` still defines and calls the helper
(blob `c3a19cbf41a476954b8afcde6d214b3cf8c82a00`). The main-delivery criterion
and the checked merge task remain unsupported. This round's regression tests
cannot resolve that remote review or deliver the repair to main.

The required generator pytest command passes with LangSmith's plugin enabled
(199 retained tests); seven supplemental guard-contract cases also pass. Focused
local coverage remains 99.92%. See the final sections and their supplemental
receipts for the source revision, overlay hashes and commands. This supersedes
prior local plugin-startup failures, not the unresolved main-delivery criterion.

Latest inspection before this round's code changes: the requested `gh pr view
4401 --repo stranske/Workflows --json
state,headRefOid,mergeCommit,statusCheckRollup` again exited 1 connecting to
`api.github.com`. Connected PR metadata reports OPEN, `draft=false`,
`merged=false`, unchanged head `9eaf43313c0e57ef964e4171f645985dca5742b8`,
and `merged_at=null`. All three submitted reviews remain COMMENTED. The same
non-outdated unresolved thread `PRRT_kwDOQprj9M6zZ4AB` concerns the revision
table; the other two unresolved threads are outdated. Latest #4401 metadata
reports main base `4928870982db3bc3b85c701b4cca2492128739b2`; an immutable
read of generator lines 100–145 at that revision returns blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00`,
still defining and calling the helper. Neither main delivery criterion is met.
This supersedes earlier main pointers while preserving their historical readbacks.

Before changing source or tests in this round, attempted:

```sh
gh pr view 4401 --repo stranske/Workflows --json state,headRefOid,mergeStateStatus,reviewDecision,statusCheckRollup
```

The command exited 1: `error connecting to api.github.com`. Connected GitHub
read-only tools supplied the fallback inspection of PR metadata, all submitted
reviews, inline review threads, changed files, and commit-associated workflow runs.
PR #4401 remains OPEN, `isDraft=false`, at
`9eaf43313c0e57ef964e4171f645985dca5742b8`; `merged=false`, `merged_at=null`.
REST `mergeable=true` does not establish GraphQL `mergeStateStatus`, review
approval, or permission to merge. The REST `merge_commit_sha` field on this open
PR is a test merge, not a delivered main revision.

The actual identified review blocker is active unresolved thread
`PRRT_kwDOQprj9M6zZ4AB` (comment 4462444583): the revision table declares two
columns but supplies three cells, hiding repair/source notes. Two other unresolved
threads are outdated (`PRRT_kwDOQprj9M6y9cVz`, `PRRT_kwDOQprj9M6y9cWG`), about
local/hosted labeling and receipt mapping. All three submitted reviews are
COMMENTED; none establishes an approval or a changes-requested decision.
Commit-associated Gate run `41752024615` and Selftest CI run `41752024817` report
success. That discovery returns only the first page of pull-request runs and is
not a complete expected/required-check receipt. Final delivery remains pending
review settlement, complete exact-head gate verification, merge and main readback.

Main was also read through the connected GitHub file API: lines 100–145 of
`scripts/langchain/followup_issue_generator.py` still define and call
`_blocked_reason_with_source` (blob `c3a19cbf41a476954b8afcde6d214b3cf8c82a00`).
That branch-relative read establishes the missing behavior at readback time;
it does not pin an immutable main commit. Final main acceptance is unsatisfied.

Repeated readback before the numbered-checklist test changes in this round:
the requested CLI read again exited 1 connecting to `api.github.com`. Connected
GitHub metadata still reports #4401 OPEN, ready for review, at the same full head
above, with no merge date. All three reviews remain COMMENTED; the same one
non-outdated unresolved table thread and two outdated threads remain. PR #3960's
complete changed-filename list independently confirms all three Node paths named
below. The injected task list's checked merge task conflicts with this readback
and must not be treated as completed delivery.

The repeated main read is now pinned: resolving `main` returned
`d2106cc83e060d0063f63dd08ea94bbaa4104fbf`. Reading the generator at that exact
commit returned blob `c3a19cbf41a476954b8afcde6d214b3cf8c82a00`; lines 105–115
still define the helper and line 138 calls it. This immutable main read confirms
that the inline-guard repair has not been delivered at the inspected revision.

The following historical measurements were checked 2026-11-03 (America/Chicago).
This record replaces the overlapping narratives in
`pr-body-reconciled.md`, `followup-review-correction.md`, and historical receipts.
Historical records remain intact; their coverage figures are superseded by the matched
**focused local** comparison below. Hosted Gate evidence is identified separately by
exact tested revision and artifact. A local run never establishes hosted Gate success.

## Exact revisions and scope

| Role | Revision | Notes |
| --- | --- | --- |
| Baseline parent of #3960 | `94d9f952dad19f4f8048ae82bb8301bc6baf6ef5` | Original baseline |
| Merge #3960 | `314895ec5d0b1e102fc80aff8001eae2545ed7fa` | Original delivery |
| Original repair implementation | `7bcca99bc` | Inline guard restore and helper-only test removal |
| Measured repair source/tests | `db91da15d7c44e34dca7d4f3d74e5cae62fff62c` | Main was incorporated into the repair branch; this is not delivery to main |
| Prior local source snapshot | `a9fb48a0c90308a13c8f09ac01ac57d9dc309a45` | Same generator and target-test hashes as measured repair; the prior round added the auditor separately |
| Numbered-checklist validation base | `a5145aafbe1cf8bc6fc69bf6961eaf18a91b69d4` | Production bytes unchanged; new Node tests identified by the supplemental receipt's test hash |

Historical repair work was integrated from `closer/issue-3956` (PR #4401),
`closer-r1/issue-3956` (coverage JSON and retained-mutation reruns), and
`closer-r3/issue-3956`. This describes branch integration, not a merged PR. Commits
`7bcca99bc` and `f77be1eee` are retained. Discarded: nothing from those branches
conflicted with the helper removal or defect fixes. No production fix from #3960 is
redone or reverted.

**Historical PR #4401 inspection:** The earlier CLEAN/no-blocker statement is
superseded by the current readback above. Checked PR-body boxes are claims, not
evidence of merge or acceptance. The measured repair revision below identifies
source bytes; it does not establish delivery to main.

## One matched focused local comparison

Historical local runtime: `/opt/anaconda3/bin/python3` (Python 3.12.2),
pytest 9.1.1, coverage 7.16.2. All three snapshots use identical current
`pyproject.toml` settings (SHA256
`f793630708820650e709e2976674cfdd5fab636f974ec1bb9e54b5968026a402`),
with each revision's source, tests, and support modules. Command:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/test_followup_issue_generator.py -q -o addopts= --cov=scripts.langchain.followup_issue_generator --cov-branch --cov-report=term-missing --cov-report=json
```

`coverage json` reads that run's data to obtain **missing branches**, rather than
substituting the terminal report's partial-branch count. Full output, source/test
hashes, missing lines/arcs, configuration revision and summaries are in
[local-coverage-comparison.json](local-coverage-comparison.json).

| Focused local snapshot | Passed | Statements | Missing statements | Branches | Missing branches | Missing statements + branches | Combined |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline `94d9f952` | 154 | 844 | 129 | 388 | 94 | 223 | 81.90% |
| Merge `314895ec` | 200 | 852 | 0 | 386 | 0 | 0 | 100.00% |
| Repair `db91da15d` | 199 | 851 | 0 | 386 | 1 | 1 | 99.92% |

The matched local baseline → repair reduction is **222 missing statement/branch
units (223 → 1)**. These are replacement snapshots; overlapping iterations are
never summed. The baseline terminal **BrPart=56** counts partially executed
branch sites, not the **94 missing arcs**. The old 129+56 calculation is superseded.
The merge also changed the source denominator; the repair removes one helper
statement and restores a defensive branch. A smaller denominator is not additional
test coverage.

This local comparison shares branch/exclusion configuration with Gate but is
**not** the hosted Gate execution: hosted Gate uses Python 3.14 coverage, marker
filtering `not quarantine and not slow`, and xdist on its full selected test scope.
The owner prohibited local full-suite/release/verify execution, so none was run.

### Defensive branch deliberately left uncovered

In `_guard_payloads`, falsy `label` skips source annotation (`124->126`). The payload
list uses fixed nonempty labels `verification_comment`, `original_issue`, and
`codex_log`. The branch is defensive; no current public input reaches it. The
repair restores the original inline logic and removes `_blocked_reason_with_source`
and only its helper-only empty-label test. The retained nonempty-label regression
proves observable blocked reasons contain their payload source. No frame mutation
or production extraction is used to force 100% coverage.

## Production defects retained from #3960

- **OSError:** `Path(value).is_file()` may raise (for example ENAMETOOLONG on long
  inline arguments), and `read_text()` may fail. `_read_existing_file` catches
  OSError; verification/original-issue arguments retain their literal text through
  `_load_text_arg`, while an unreadable optional Codex log becomes `None`. Both probe
  and read failures have retained tests and current-source mutation receipts.
- **Numbered checklist:** PR-meta refresh produced numbered unchecked items but the
  parse/merge regexes recognized only dash bullets. Checked state was lost on the
  next refresh. The source and consumer-template fixes and both numbered checklist
  regressions remain. PR #4401 changes no JS production or test bytes; the later
  local validation below adds two tests for the existing whitespace boundary.
  PR #3960's file list locates the implementation at
  `.github/scripts/agents_pr_meta_update_body.js`, its identical consumer copy at
  `templates/consumer-repo/.github/scripts/agents_pr_meta_update_body.js`, and tests
  at `.github/scripts/__tests__/agents-pr-meta-update-body.test.js`.
  **Existing whitespace difference:** `parseCheckboxStates` accepts arbitrary
  whitespace after a bullet through `(?:[-*+]|\d+[.)])\s+\[(x| )\]`.
  `mergeCheckboxStates` uses `([-*+]|\d+[.)]) \[( )\]`, with exactly one literal
  space between the bullet and checkbox. Both recognize numbered bullets; their
  whitespace contracts still differ. This round records that difference and
  preserves both regexes without expanding scope into a whitespace repair.

These were real production fixes, so historical “production unchanged” / “test-only”
claims describe earlier iterations only and do not describe #3960 as delivered.

## Ranking provenance

**Issue #3956 supplied the target ranking** (escaped-defect priority, then churn,
then uncovered mass). This repair follows that supplied target; it does not claim
an independently reproduced ranking or a new ranking run. No additional target is
introduced.

**Owner-visible limitation:** The canonical ranking inputs and original ranking
execution are unrecoverable from these receipts. Historical numbers (21 escaped
defect signals, churn 27, 225 uncovered units) are supplied claims, not independently
verified ranking results. `followup-coverage-round.md` explicitly records the
missing canonical ranking and rejects issue-3743 proxy artifacts as substitutes.
The contradictory checked ranking boxes in `pr-body-reconciled.md` and historical
JSON contracts are superseded: independent ranking verification remains incomplete.

## Coverage values and contradictory completion claims

| Value | Historical attribution | Supported interpretation |
| --- | --- | --- |
| 81.80% | `pr-body-reconciled.md`, early local baseline: 846 statements, 390 branches | Historical local claim; exact tested revision, JSON missing arcs, and hosted run/artifact binding are unsupported. It is not the matched 81.90% baseline. |
| 89.81% | Same document, early local 160-test snapshot, 74 missing statements and 38 partial branch sites | Historical local claim with a command; exact source revision and hosted binding unsupported. |
| 99.11% | `followup-edge-coverage-proof.json` and the before-value in `followup-contract-edge-proof.json` | Intermediate local claim tied to source hash `251c5642…`, with 846 statements and 390 branches in the adjacent narrative; no exact tested commit or hosted artifact supports this percentage. |
| 100% | Matched merge snapshot `314895ec…` in `local-coverage-comparison.json`: 852 statements, 386 branches, zero misses | Supported focused-local merge measurement, including the helper-only test; historical empty-label/helper/OSError receipts also claim 100% at different denominators. None establishes the repaired main state. |
| 99.92% | Matched repair `db91da15…`, historical hosted `f77be1ee…`, and this round's focused-local rerun | Separately identified local/hosted measurements; repaired source retains one missing defensive arc. |

The old **75-unit** claim subtracts `(130 + 57) - (74 + 38)`, mixing missing
statements with partial branch sites. It cannot prove approximately 60 missing
statement/branch destinations were removed. The comparable JSON local snapshots
measure **(129 + 94) - (0 + 1) = 222** missing statement/branch-destination units.
No comparable hosted baseline artifact is present in the inspected evidence, so
the hosted approximately-60-unit criterion remains **incomplete**. Local 222 is
explicitly separate and cannot fill that gap.

Checked CI, coverage, ranking, exhaustion and completion boxes in
`pr-body-reconciled.md`, historical proof contracts and PR #4401's body are
superseded where they claim more than the evidence above. The earlier
`followup-coverage-round.md` is an intermediate 170→178-test, 29-unit local round
(92.64%→94.98%), not the final delivery. Its test-only statement describes that
iteration. `followup-review-correction.md` describes an abandoned frame-based test
and later helper extraction; this repair removes the helper again. The OSError
fallback and numbered-checklist changes are production fixes. Original historical
receipts, including unsupported claims, remain intact for traceability.

The follow-up inspection read `followup-coverage-round.md` in full, the OSError,
empty-label, helper, nonempty-label, contract-edge, remaining-branch and numbered
state proofs, and the coverage/ranking/contract fields of the larger historical
proofs. Their mutation bodies remain subject to the bounded retained audit above;
this inspection does not upgrade historical exit-only claims into assertion proof.
Specific conflicting claims are superseded as follows:

| Historical receipt | Conflicting claim | Authoritative disposition |
| --- | --- | --- |
| `followup-coverage-round.md` and `followup-coverage-proof.json` | Test-only 170→178-test round, 92.64%→94.98%, 29 units | Describes an earlier local iteration, not the final #3960 diff or hosted coverage. The round explicitly reports canonical ranking unavailable. |
| `followup-oserror-fallback-proof.json` | `3_no_production_bug_found=true`, ranking verified, no remaining work, 100% | The OSError fallback is a real production fix. Its own classification note rejects test-only scope. Ranking numbers are supplied claims; exit-only/re-raise proofs do not establish relevant assertion failures and are superseded by current-source wrong-value receipts. |
| `followup-contract-edge-proof.json`, `followup-remaining-branches-proof.json` and `followup-reconciliation-proof.json` | Ranked/test-only completion and intermediate coverage | Historical local stages at different source/test snapshots. The matched comparison and retained current-source audit govern; independent ranking remains unrecoverable. |
| `followup-empty-label-proof.json`, `followup-blocked-reason-helper-proof.json` and `numbered-checklist-state-proof.json` | Empty-label/helper-assisted 100%, target exhausted, checked ranking contract | Abandoned frame-based test and removed helper-only test cannot establish repaired coverage. Numbered-checklist behavior is retained; its generator coverage/exhaustion narrative is historical. |

No historical receipt is edited by this reconciliation. Recovering the canonical
ranking inputs and execution remains an owner-visible limitation, not a completed
ranking check.

## Every retained added Python test and parameter case

Comparing the baseline test AST with repair leaves **35 added functions / 45
collected cases** after removing the helper-only test. The complete current-source
index is [retained-mutation-reconciliation.json](retained-mutation-reconciliation.json).
Each proof records the precise node ID (including parameter ID), mutation text,
mutant/restored source hashes, exact source revision/test hash, assertion failure
output, and restored passing output. All 50 mutation receipts were rerun on the
repair source; this includes source-invalidated CLI receipts that previously
mutated direct Path reads removed by the OSError fix. One mutation initially
selected the wrong Concerns parser and survived; its corrected replacement kills
the plain-label parser regression. Three re-raise mutations produced OSError
failures, so they were replaced with wrong-value mutations that produce actual
assertion failures. All four discarded attempts remain in the JSON and are not
counted among the 50 successful receipts.

### Bounded audit and unabridged replacements (2026-11-07)

The retained index was inspected in bounded groups (indices 0–4, 5–9, 10–16,
17–24, 25–34, 35–42, 43–49); the four discarded attempts and both Node receipts
were inspected separately. Mutation replacements, parameter-specific failing
assertions and restored summaries were read without accepting tool-output
truncation as inspection. The new read-only auditor also reconstructs every
mutant SHA256, checks restored source/test hashes, compares independently
collected cases against the baseline AST, and verifies assertion-failing RED
and single-case GREEN output. It never executes commands from receipt data.

The first audit exited 1: historical indices **2** (duplicate Notes section) and
**24** (five-item history cap) have pytest `Full output truncated` diagnostics.
Their original records remain unchanged. Both mutations were rerun independently
with `-vv --tb=long -m 'not slow'` in isolated temporary packages using the same
source/test bytes, original support modules, and the current Python 3.14.10.
Each failed with the relevant assertion (exit 1), then passed after exact source
restoration (exit 0). Full output, commands, revision, and binding to the original
receipt digest are in
[retained-mutation-unabridged-reruns.json](retained-mutation-unabridged-reruns.json).
The restored production file in the checkout was never mutated.

[retained-mutation-audit.json](retained-mutation-audit.json) enumerates every
Python parameter case and both Node cases, each replacement, assertion, restored
GREEN summary and historical receipt index. With the bound replacements the
audit exits 0: **35 added functions, 45 cases, 50 Python receipts, 2 Node receipts,
zero unmapped cases or invalid mutation hashes**. This verifies the inspected
repair source; it does not establish final main delivery.

Reproduction (from the repository root):

```sh
git show 94d9f952dad19f4f8048ae82bb8301bc6baf6ef5:tests/test_followup_issue_generator.py > /tmp/issue-3956-baseline-tests.py
PYTHONIOENCODING=utf-8 python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py --collect-only -q -m 'not slow' > /tmp/issue-3956-collected-tests.txt
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-baseline-tests.py --collected-tests /tmp/issue-3956-collected-tests.txt
```

1. `test_extract_verification_data_preserves_supported_mixed_formats`
2. `test_json_and_markdown_helpers_preserve_machine_and_human_output`
3. `test_append_advisory_notes_only_adds_a_single_notes_section`
4. `test_disposition_reports_absent_structured_provider_evidence`
5. `test_main_reads_file_inputs_and_writes_json_output`
6. `test_main_reads_verification_from_standard_input`
7. `test_main_bounds_concern_diagnostics_without_truncating_generated_tasks`
8. `test_generate_followup_without_available_clients_preserves_actionable_feedback`
9. `test_generate_followup_routes_available_clients_without_losing_model_identity` (parametrize)
10. `test_followup_metadata_fallback_preserves_context_and_number_precedence` (parametrize)
11. `test_invoke_without_langchain_uses_plain_prompts_and_preserves_output` (parametrize)
12. `test_invoke_without_langchain_reports_plain_prompt_failure_with_cause`
13. `test_trace_failures_preserve_generated_text_and_log_the_cause` (parametrize)
14. `test_llm_rounds_forward_evidence_and_assemble_issue_with_optional_traces` (parametrize)
15. `test_structured_followup_keeps_structural_findings_and_caps_non_actionable_history`
16. `test_confidence_helpers_preserve_empty_integer_and_percent_provider_edges`
17. `test_advisory_unfalsifiable_and_spurious_concern_filters`
18. `test_missing_concerns_note_triggers_for_empty_body_and_blank_verdicts`
19. `test_strip_checkbox_preserves_non_list_text`
20. `test_budget_followup_tasks_stops_when_next_task_would_exceed`
21. `test_truncate_task_to_budget_returns_task_when_already_within_budget`
22. `test_code_change_decision_skips_split_and_advisory_only_concerns`
23. `test_build_why_section_resolves_verdict_when_omitted`
24. `test_invoke_llm_records_langsmith_trace_url`
25. `test_get_followup_client_falls_back_when_reasoning_model_unavailable`
26. `test_main_guard_blocked_writes_markdown_output_file`
27. `test_concern_label_and_insights_skip_short_and_spurious_fragments`
28. `test_parse_checklist_skips_direct_checkbox_placeholders_and_non_list_lines`
29. `test_select_followup_acceptance_criteria_keeps_all_when_feedback_mentions_sync`
30. `test_select_followup_acceptance_criteria_falls_back_when_mixed_filter_empties`
31. `test_module_main_entrypoint_invokes_main`
32. `test_guard_payloads_annotates_reason_with_nonempty_label`
33. `test_read_existing_file_returns_none_when_is_file_raises_oserror`
34. `test_read_existing_file_returns_none_when_read_text_raises_oserror`
35. `test_main_oserror_fallbacks_keep_literal_args_and_drop_codex_log`


### Historical receipt index (preserved, superseded by the current-source reruns)

| Retained function range above | Actual historical receipt | Notes |
| --- | --- | --- |
| 1–15 | `followup-reconciliation-proof.json` | 29 mutations, 15 functions; provider `[both, reasoning, standard]`, metadata `[explicit-pr, explicit-issue, env-pr, env-issue, invalid-env, missing-env]`, invocation `[configured, fallback]`, trace `[missing-module, extract-error]`, LLM `[populated, empty]` cases explicitly indexed |
| 16–26 | `followup-edge-coverage-proof.json` → `results` | 11 functions, actual assertion failures and restored passes |
| 27–29 | `followup-contract-edge-proof.json` → `proofs` | 3 functions; historical exit-only claims replaced by captured current assertion failures |
| 30–31 | `followup-remaining-branches-proof.json` → `proofs` | 2 functions; current assertion output now retained |
| 32 | `followup-guard-nonempty-label-repair-proof.json` | Inline guard replacement proof; rerun again in current index |
| 33–35 | `followup-oserror-fallback-proof.json` → `proofs` | Probe/read/literal fallback tests; all current assertion outputs now retained |

The prior assertion that `followup-reconciliation-proof.json` covers items 1–31
was false. It covers only 1–15. The prior blanket claim that all recorded source
paths remained valid was also false for direct CLI Path reads; the current reruns
mutate `_load_text_arg` / `_read_existing_file` callers instead.

The two retained added JS tests and their separate mutations are indexed in
[numbered-checklist-repair-proof.json](numbered-checklist-repair-proof.json):
`parseCheckboxStates captures numbered checklist completions` and
`mergeCheckboxStates restores numbered contract checklist items across refresh`.
Each independently fails with an assertion when its regex loses numbered support,
then passes after restoration. Historical `numbered-checklist-state-proof.json`
remains the earlier receipt; its coverage/completion narrative is superseded here.

### Superseded claims and records

- `followup-blocked-reason-helper-proof.json`: helper removed; proof no longer applies.
- `followup-empty-label-proof.json`: caller-frame empty-label test abandoned.
- `followup-coverage-proof.json`, `followup-reconciliation-proof.json`,
  `followup-edge-coverage-proof.json`, `followup-contract-edge-proof.json`,
  `followup-remaining-branches-proof.json`, `followup-oserror-fallback-proof.json`,
  `numbered-checklist-state-proof.json`, `followup-coverage-round.md`,
  `followup-review-correction.md`, and `pr-body-reconciled.md`: retained historical
  snapshots, not final coverage or completion evidence; current receipts above
  replace their mutation reconciliation claims.
- Merge-era 100% figures used the helper-only test and do not describe repair.
- Historical closing statements do not establish issue completion. This repair
  uses **Refs #3956**; the issue remains subject to the closer's acceptance.

## Local verification output (measured repair revision above)

```text
........................................................................ [ 36%]
........................................................................ [ 72%]
.......................................................                  [100%]
================================ tests coverage ================================
_______________ coverage: platform darwin, python 3.12.2-final-0 _______________

Name                                            Stmts   Miss Branch BrPart   Cover   Missing
--------------------------------------------------------------------------------------------
scripts/langchain/followup_issue_generator.py     851      0    386      1  99.92%   124->126
--------------------------------------------------------------------------------------------
TOTAL                                             851      0    386      1  99.92%
199 passed in 1.84s
```

```sh
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
```

```text
✔ closing-keyword and branch sources retain closing intent across two body syncs (2.522ms)
ℹ tests 170
ℹ suites 0
ℹ pass 170
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 3212.901417
```

## Hosted verification

Earlier repair head `f77be1eee61239aa264c166aed84db8fae8708f3` has
[successful Gate run 41567623097](https://github.com/stranske/Workflows/actions/runs/41567623097)
and [Selftest CI run 41567622897](https://github.com/stranske/Workflows/actions/runs/41567622897).
Those runs tested that head only.

The historical receipt records download and inspection of
[Gate Python 3.14 coverage artifact 13200231583](https://github.com/stranske/Workflows/actions/runs/41567623097/artifacts/13200231583)
for `f77be1eee`: 851 statements, 0 missing statements, 386 branches, **1 missing
branch**, 99.92%. ZIP SHA256:
`540949b4d94392b5d2daafc794f9acc6c1011155ac0cc24bf8f1bb6d635f4136`.
Summary in [hosted-coverage-receipt.json](hosted-coverage-receipt.json).

The current publication head is `closer/issue-3956` at `9eaf43313…`, not the
historical `closer-r3/issue-3956` branch. Fresh hosted job-log inspection is recorded
separately in [hosted-gate-readback.json](hosted-gate-readback.json):

| Tested revision | Gate run | Python 3.14 job | Coverage artifact | Hosted pytest result |
| --- | --- | --- | --- | --- |
| `f77be1eee61239aa264c166aed84db8fae8708f3` | `41567623097` | `125693048153` | `13200231583` | 50,308 passed, 27 skipped, 3 xfailed |
| `9eaf43313c0e57ef964e4171f645985dca5742b8` | `41752024615` | `126320180581` | `13287665592` | 50,354 passed, 27 skipped, 3 xfailed |

Both logs show 851 statements, zero missing statements, 386 branches, one partial
branch site, `124->126`, and 99.92% for the generator. Runtime is Python 3.14.9;
coverage versions differ (7.17.0 versus 7.17.1). Artifact metadata binds the second
archive to `9eaf43313…`, digest
`b63903e319393d955daf6a879fc9a1ffe7fa5d088672c97ab253be5f6c2ae06a`.
The ZIP bytes were not inspected in this round; the new exact-head measurement
is supported by its hosted job log. The older JSON receipt remains distinct.

The logged command builder invokes `pytest -p ci_test_growth "${args[@]}"`.
Its reconstructed argument vector, using the logged marker/worker environment,
is below (the repeated xdist flags reflect the actual builder; the final ones win):

```sh
pytest -p ci_test_growth -m 'not quarantine and not slow' --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml --cov-report=xml:coverage.xml --cov-report=term-missing --cov-report=json:coverage.json -n auto --dist load -n 4 --dist=loadgroup
```

These hosted results concern repair snapshots only. No comparable original
hosted baseline has been recovered, and no main delivery is inferred from them.

## Prior local validation and remaining delivery work

This subsection preserves the prior agent round's results and commit blockers.
Automation subsequently recorded that work in `a5145aaf…`; the later numbered
checklist round and its independent commit attempt are recorded below.

Checkout source revision: `a9fb48a0c90308a13c8f09ac01ac57d9dc309a45`.
The generator and original target test file remain byte-for-byte unchanged in
this round. `git diff 314895ec… HEAD -- scripts/langchain/followup_issue_generator.py
tests/test_followup_issue_generator.py` confirms the existing repair only restores
inline annotation and removes the one helper-only test. The numbered-checklist
implementation and consumer copy compare identical.

The current selected interpreter is
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (Python 3.14.10), matching the
primary 3.14 runtime in `.github/workflows/ci-python-versions.env`.
The required target pytest invocation with `-m 'not slow'` initially exited 3
during optional LangSmith plugin startup: its use of deprecated
`asyncio.iscoroutinefunction` conflicts with the repository's warning-as-error
configuration. The isolated retry excludes that plugin; no test or assertion is
disabled. The original invocation is not represented as successful.

```sh
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow'
# 199 passed; exit 0
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-current-coverage.json
# 199 passed; 851 statements, 0 missing; 386 branches, 1 partial; 99.92%; 124->126
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py tests/scripts/test_audit_followup_mutations.py -q -m 'not slow'
# 222 passed (199 generator + 23 auditor regression cases); exit 0
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; process-isolated reporter aggregates the file as one passing unit
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# 170 individual tests passed, 0 failed, 0 skipped; exit 0
ruff check scripts/audit_followup_mutations.py tests/scripts/test_audit_followup_mutations.py
# All checks passed
black --line-length 100 scripts/audit_followup_mutations.py
black --line-length 100 tests/scripts/test_audit_followup_mutations.py
# Both formatted successfully using single-file invocations
git diff --check
# exit 0
```

The required repository-wide command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
fails with a sandbox `PermissionError` binding the multiprocessing forkserver
socket. `BLACK_NUM_WORKERS=1` retries were stopped at 45 and 90 seconds (exit 124);
the latter reported 889 files unchanged but was aborted, so it is not a passing
repository-wide result. The formatting gate therefore prohibits a commit.
Staging the five original changed/new files also failed creating
`.git/index.lock`: **read-only file system**. All changes remain local and
uncommitted; no push, PR mutation, sync dispatch or merge was performed.

Current task accounting (local evidence only):

- [x] Inspect #4401 head, reviews and threads before source edits; record the actual blocker, with the `gh` transport failure disclosed.
- [x] Verify the existing inline-guard repair removes only the helper-only test and retains the OSError fix/tests.
- [x] Locate the Node files through #3960's file list and preserve their numbered-checklist behavior and existing whitespace difference.
- [x] Audit all retained mutation cases, replace the two truncated receipts with bound full-output reruns, and verify restored GREEN against the identified repair source.
- [x] Reconcile original delivery, repair, hosted snapshots, coverage units and unsupported baseline claims.
- [x] Supersede conflicting historical completion/test-only claims and expose unrecoverable ranking provenance.
- [x] Run targeted Python and Node validation and record the interpreter, command variants, revisions and results; the unmodified Python command's plugin-startup failure remains disclosed above.
- [ ] Complete existing #4401 review settlement, exact-head gate verification, merge and immutable main readback. The CLI final readback also failed to connect; connected metadata still reports OPEN, `isDraft=false`, unchanged head and `merged_at=null`.

Acceptance remains incomplete: main still has the helper; #4401 is open with an
active unresolved thread; the comparable hosted reduction is unproved; canonical
ranking provenance is unrecoverable; and the unmodified Python invocation has an
environment startup failure. The local table correction does not resolve the
thread on the remote repair PR until it is delivered and reviewed there.

## Numbered-checklist validation round (2026-11-07 UTC)

- [x] Inspect the PR #3960 Node file list, source, consumer copy and tests;
  preserve numbered handling and document the existing whitespace difference.
- [x] Inspect the historical round/OSError/remaining proof claims and supersede
  conflicting completion, test-only and ranking claims as recorded above.
- [ ] Deliver the repair through #4401's review, checks, merge and main readback.

The only source-code change in this round is two added Node tests in
`.github/scripts/__tests__/agents-pr-meta-update-body.test.js`:

1. `numbered checklist parsing accepts tabs and multiple spaces in source and template`
2. `numbered checklist merging retains its single-space boundary in source and template`

Both exercise the source and consumer exports, `1.` and multi-digit `12)` bullets,
one space, two spaces and a tab, indentation, unchecked items and fenced examples.
The merge test also checks already-completed items and repeated-refresh stability.
It uses an independently constructed state map so a parser failure cannot conceal
a merge regression. The existing two numbered tests remain unchanged. Generator
source/tests, both production Node copies, templates and the sync manifest have
no diff; no consumer payload changed.

[numbered-checklist-whitespace-proof.json](numbered-checklist-whitespace-proof.json)
maps both new tests to **8 assertion-failing RED / restored GREEN receipts**.
Production source is pinned to `a5145aafbe1cf8bc6fc69bf6961eaf18a91b69d4`,
SHA256 `3a549a854dbd2ee280c1a9d037d05e09b67e3dc35ed8571837468f442a57a15f`
for each copy. The new local test overlay is bound by its SHA256
`3283b5b921327890064b5aebe82c214427dc49d0bdf200712251b4d0a0819eab`.
Each selected test was run independently against a temporary module mutation,
then the exact restored bytes, with Node v24.22.2. Checkout production was never
mutated. Complete outputs were inspected in bounded pairs 0–1, 2–3, 4–5 and 6–7.

| Receipt indices (source / template) | Test | Mutation and observed assertion |
| --- | --- | --- |
| 0 / 4 | Parsing | Replace arbitrary bullet whitespace with one space; the two-space checked item disappears from the expected state map. |
| 1 / 5 | Merging | Widen the literal bullet space to arbitrary whitespace; a two-space item changes instead of remaining byte-identical. |
| 2 / 6 | Parsing | Drop right-parenthesis bullets; `12)` disappears from the expected state map. |
| 3 / 7 | Merging | Drop right-parenthesis bullets; `12)` stays unchecked instead of restoring completion. |

All eight RED runs exit 1 with `AssertionError [ERR_ASSERTION]`; all restored
GREEN runs exit 0 with one pass and zero failures. The original retained audit
continues to cover the original two Node cases; this supplement covers the two
new cases separately without rewriting historical evidence.

Validation against the identified base plus the hash-bound Node test overlay:

```sh
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; default process-isolated reporter aggregates one passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 172 passed, 0 failed, 0 skipped
python -m pytest tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 3 during optional LangSmith plugin startup; no successful test run claimed
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-round-coverage.json
# exit 0; 199 passed; generator Cover 99.92%, 851 statements, 0 missing,
# 386 branches, 1 missing arc (124->126); selected Python 3.14.10
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-round-baseline-tests.py --collected-tests /tmp/issue-3956-round-collected-tests.txt
# exit 0; 35 added Python functions / 45 cases, 50 Python and 2 original Node
# receipts; complete=true, no problems. Inputs prepared as in reproduction above.
git diff --check
# exit 0
```

The original Python command's plugin startup failure remains an acceptance gap;
the isolated passing run and focused local coverage do not replace it or hosted
evidence. No Python files changed, so this round does not introduce a Python
formatting gate. Staging only the Node test, this reconciliation and its new
receipt failed creating `.git/index.lock` (**read-only file system**, exit 128).
This round's changes remain uncommitted; no push or remote PR change occurred.
#4401 remains open, ready for review at the readback head. Main still contains
the helper at the pinned commit, the hosted comparable reduction is unproved and
ranking provenance is unrecoverable. No delivery or overall acceptance checkbox
is completed by these local results.

## Task-status reconciliation before further tests (2026-11-07 UTC)

Reviewed commits `a9fb48a0`, `a5145aaf` and `3ab79ec1`. The last two commits
record the previously uncommitted audit and numbered-checklist work. The first
unchecked Node inspection task and the historical-proof inspection task are
already implemented and documented above; a fresh Node run at `3ab79ec1` passed
all 172 cases. Re-read the historical round and OSError receipt in full and the
remaining proof coverage/ranking/contract fields separately. Their contradictory
completion and test-only claims remain superseded, and ranking provenance remains
unrecoverable.

Before further code edits, the requested `gh pr view 4401` inspection again
exited 1 connecting to `api.github.com`. Connected metadata reports #4401 OPEN,
`draft=false`, unchanged head `9eaf43313c0e57ef964e4171f645985dca5742b8`,
`merged=false`, and `merged_at=null`. All three submitted reviews are COMMENTED.
Thread `PRRT_kwDOQprj9M6zZ4AB` remains unresolved and non-outdated; the other two
unresolved threads remain outdated. The checked merge task is therefore false.
No gate bypass or merge was attempted.

Attempted to update #4518's body to check the two verified inspection tasks and
uncheck the undelivered #4401 merge task. The connected GitHub update was denied:
`MCP tool call requires approval, but approval policy is never`. The remote body
was not changed. This is a local reconciliation, not a successful remote update.
The next local test will exercise numbered state through `buildStatusBlock`,
which composes normalization, parsing and merging during a real summary refresh.

### Summary-refresh test and verification

Added `buildStatusBlock preserves numbered completion through normalization and
repeated refresh` to the identified Node test file. It independently checks both
production exports through two summary rebuilds: numbered task and acceptance
completion survives tabs/multiple spaces and renumbering; pending items stay
unchecked despite checked examples in fenced code or outside the managed block.
The source and consumer regexes remain unchanged, including their different
whitespace contracts. No consumer payload, Python file or protected file changed.

[numbered-checklist-summary-proof.json](numbered-checklist-summary-proof.json)
binds this additional Node case to base `3ab79ec1275d150bd32a2a414cd99d9a28981ce0`
and test-overlay SHA256
`05e6d51fef76575be14a373c34decc374455959e7d5d7e94b201165cf65e8bfb`.
Both production copies retain SHA256
`3a549a854dbd2ee280c1a9d037d05e09b67e3dc35ed8571837468f442a57a15f`.
Receipts 0–1 mutate source parsing/merging; 2–3 independently mutate the template.
Each removes numbered support, fails the named test with the corresponding
source/template completion assertion (exit 1), then passes after exact byte
restoration (exit 0, one pass, zero failures). Read all four full outputs in
bounded pairs 0–1 and 2–3. Production mutations used disposable copies only.
These supplement the original retained mapping and whitespace receipts without
claiming any new main delivery.

One discarded exploratory mutation bypassed `ensureChecklist` for tasks and
survived: `coalesceWrappedChecklist` already normalizes the bullet whitespace.
The receipt records that survival separately; it is not counted as RED evidence.
The initial Node mutation driver could not spawn a child (`EPERM`); the Python
driver completed all four independent mutation/restore runs.

Validation on the named base plus the Node test overlay, using Node v24.22.2 and
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`:

```sh
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; default reporter aggregates one passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, 0 failed, 0 skipped
python -m pytest tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 3; optional LangSmith plugin's deprecated asyncio.iscoroutinefunction
# fails during startup under warning-as-error settings
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-summary-coverage.json
# exit 0; 199 passed; generator Cover 99.92%, 851 statements, 0 missing,
# 386 branches, 1 missing arc (124->126)
git diff --check
# exit 0
```

Fresh immutable main read at `d2106cc83e060d0063f63dd08ea94bbaa4104fbf`
still shows `_blocked_reason_with_source` defined/called in generator blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00`. Main delivery remains incomplete.
Hosted comparable reduction and canonical ranking provenance remain unresolved;
this local test/coverage run establishes neither.

The prepared corrected PR body is `/tmp/issue-3956-reconciled-pr-body.md`.
Its two inspection tasks are checked and its merge task is unchecked; the denied
remote update remains pending. Staging only the Node test, authoritative record
and new proof failed with exit 128: `.git/index.lock` cannot be created on the
read-only filesystem. Changes remain uncommitted for the runner; no push occurred.
No Python files changed, so the Python pre-commit formatting gate does not apply
to this round's edits. #4518 and #4401 were both read as open, `draft=false`.

## Historical-proof inspection and auditor portability (2026-11-07 UTC)

Before code edits at checkout `e0e027e6ae37683d2889a43b112fc5a7e453f7f8`,
the requested `gh pr view 4401` read again failed to connect to `api.github.com`.
Connected GitHub metadata independently returned OPEN, `draft=false`,
`merged=false`, head `9eaf43313c0e57ef964e4171f645985dca5742b8`. All three
reviews remain COMMENTED; thread `PRRT_kwDOQprj9M6zZ4AB` remains unresolved
and non-outdated, and the other two threads remain outdated. No merge or new
hosted success is established by this read. #4518 is also open and ready.

Re-read the historical round, OSError fallback, review correction, coverage,
edge-coverage, contract-edge, remaining-branch, empty-label, helper, nonempty-label
and numbered-state receipts. Read the larger reconciliation's coverage fields,
function list and all 29 mutation descriptors separately from its long output
strings; this is a claim inspection, not a new full-output mutation audit.
The bounded retained audit and its unabridged replacements remain authoritative
for assertion-failing RED and restored GREEN.

The historical reconciliation's `coverage` describes **94.98% → 95.47%** at
846 statements and 390 branches: missing lines/arcs change from 30/32 to 27/29,
or six local units. Its `verified_test_functions` contains 15 functions, despite
29 mutation descriptors. The separate edge receipt's `coverage_after=99.11%`
is another historical local stage. Neither value establishes hosted coverage,
the final repair measurement or delivery. The historical round's 29 units and
this six-unit change must not be added to overlapping replacement snapshots.

The OSError receipt's `contract.3_no_production_bug_found=true` conflicts with
its own `contract.classification_note` and production fallback. Its empty
`remaining` list and 100% claim do not establish completion. Likewise, numbered
state's `ranking.primary_coverage` calls the target exhausted while documenting
a real production fix. All such completion and test-only claims remain
superseded here. `contract.1_ranked_target=true` and repeated 21/27/225 ranking
figures establish only the supplied target: canonical ranking inputs and the
original execution are **unrecoverable, owner-visible limitations**, not verified
ranking evidence. Historical receipt bytes remain unchanged.

Two active #4518 review findings were checked against the current auditor:
implicit default-encoding reads can invalidate UTF-8 source hashes on a cp1252
host, and the negative receipt tests did not independently cover an assertion
failure without the selected case identity. The scoped follow-up addresses
these evidence-validation gaps; it does not change the generator, its retained
test set, Node production files or the consumer payload.

### Verified result and remaining blockers

- [x] Inspect the historical proof claims, supersede conflicting completion and
  test-only claims, preserve receipts and expose unrecoverable ranking provenance.
- [ ] Merge #4401 through review and exact-head checks and verify main delivery.

The auditor now explicitly reads repository evidence, source/tests, supplements,
baseline and collected cases as UTF-8. The collection command above fixes stdout
encoding to match. New regressions simulate cp1252 decoding and independently
reject assertion failures without a case identity or from another case.
[auditor-portability-proof.json](auditor-portability-proof.json) binds the code/test
overlay to base `e0e027e6…`: the original auditor fails the encoding regression;
removing the case-identity guard fails both negative cases; restored source passes
all three. These isolated temporary-package outputs were read in two bounded
portions, without truncation. They supplement, rather than replace, the original
retained mutation evidence.

Validation used `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`:

```sh
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py tests/scripts/test_audit_followup_mutations.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-portability-coverage.json
# exit 0; 225 passed (199 generator + 26 auditor); generator Cover 99.92%
# 851 statements, 0 missing; 386 branches, 1 missing arc (124->126)
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-final-baseline.py --collected-tests /tmp/issue-3956-final-collected.txt
# exit 0; 35 added functions / 45 cases; 50 Python + 2 Node receipts;
# complete=true, problems=[]; baseline and collection prepared as above
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, 0 failed/skipped
ruff check scripts/audit_followup_mutations.py tests/scripts/test_audit_followup_mutations.py
# exit 0
git diff --check
# exit 0
```

The unmodified Python invocation (with `-m 'not slow'`) still exits 3 during
LangSmith plugin startup; the isolated result does not satisfy that acceptance
gap. Each changed Python file was formatted and passes its individual Black
check at line length 100. The required repository-wide Black command exits 1
with a forkserver socket `PermissionError`; a single-worker retry was interrupted
(exit 130) without a completed result. The formatting gate therefore remains
unsatisfied. Staging the scoped changes exits 128 because `.git/index.lock` is on
a read-only filesystem, so no commit or push occurred.

Attempting to check the verified inspection task and uncheck the undelivered
merge task in #4518 was denied: `MCP tool call requires approval, but approval
policy is never`. The remote body remains unchanged. The checked merge task is
still false; #4401 remains open and ready at the readback head. Hosted baseline
comparison, main delivery and canonical ranking provenance remain incomplete.

## Revision provenance and final task readback (2026-11-07 UTC)

Reviewed recent commits `a5145aaf`, `3ab79ec1`, `e0e027e6` and `c9340ea0`
before further changes. They already implement the historical-proof inspection:
the historical round, review correction and PR-body supplement were re-read in
full, as were the OSError, coverage, edge, contract-edge, remaining-branch,
empty-label, helper, nonempty-label and numbered-state proofs. The reconciliation's
29 mutation descriptors and coverage/ranking fields were inspected separately
from its long output strings. Claims in all 14 `*proof.json` files were checked;
the later auditor and numbered-checklist supplements describe local validation,
not hosted or main delivery. Historical receipts remain unchanged.

- [x] Inspect the historical proof files and supersede conflicting completion
  and test-only claims through this authoritative record. In particular, the
  OSError receipt's `3_no_production_bug_found=true` conflicts with its own
  classification note; empty `remaining` lists and helper-assisted 100% do not
  establish completion. Canonical ranking inputs/execution remain unrecoverable
  and owner-visible; supplied 21/27/225 figures are not verified ranking evidence.
- [ ] Complete #4401 review, exact-head checks, merge and immutable main readback.
  The injected checked merge task is unsupported and must be unchecked.

Before editing, the requested `gh pr view 4401` command again exited 1 connecting
to `api.github.com`. Connected metadata still reports OPEN, `draft=false`,
`merged=false`, head `9eaf43313c0e57ef964e4171f645985dca5742b8`, and no merge
date. All three reviews remain COMMENTED. Thread `PRRT_kwDOQprj9M6zZ4AB`
remains unresolved/non-outdated; the two other unresolved threads are outdated.
The latest immutable main read resolves to
`bffa368bb5792671aa918d6f9296accbf8827880`: generator blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00` still defines and calls the helper.
This supersedes the earlier main pointer, without establishing delivery.

The scoped code change strengthens the retained-evidence auditor. Equal empty,
null, branch-name, abbreviated or non-hex revisions can no longer establish
completion; absent revision fields report incomplete instead of raising KeyError.
Supplements require a full commit identifier before replacing historical output.
Every row now names its source revision, receipt file and actual index within
that file, with `historical_index` preserving the original mapping. Historical
indices 2/24 map to supplement indices 0/1 at `a9fb48a0…`; the other rows retain
`db91da15…`. Identifier validation checks syntax; source/test hashes bind bytes.
It does not establish commit ancestry, ranking provenance or main acceptance.

Validation base: `c9340ea045583d289d164472f8e25eb523f013d2`, with local auditor
SHA256 `eee6d942475269417e9751e374bf87eedd2e871125027f229e18df29b23216d4`
and auditor-test SHA256
`27a425c435fde5ba1a9b370bd6d3f9dbacacf80919805a6b31b268e60e72f71b`.
The new revision tests against the original auditor first exited 1: eight
assertion failures and four missing-field KeyErrors (12 failed, one passed).
The corrected auditor passes all 36 auditor cases, including distinct supplemental
and historical indices and preservation of every unreplaced row's revision.

```sh
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py tests/scripts/test_audit_followup_mutations.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov=scripts.audit_followup_mutations --cov-report=term-missing --cov-report=json:/tmp/issue-3956-revision-coverage.json
# exit 0; 235 passed (199 generator, 36 auditor); generator Cover 99.92%
# 851 statements, 0 missing; 386 branches, 1 missing arc (124->126)
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-revision-baseline.py --collected-tests /tmp/issue-3956-revision-collected.txt
# exit 0; 35 added functions / 45 cases; 50 Python + 2 Node receipts;
# complete=true, problems=[]; inputs prepared as in reproduction above
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, zero failures/skips
ruff check scripts/audit_followup_mutations.py tests/scripts/test_audit_followup_mutations.py
# exit 0
git diff --check
# exit 0
```

Python remains `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`.
The unmodified pytest invocation with `-m 'not slow'` still exits 3 during
LangSmith's deprecated `asyncio.iscoroutinefunction` call at plugin startup;
the isolated result above does not replace that acceptance requirement.
Generator source/tests and both Node production copies are unchanged.

The GitHub PR-body update was denied again: `MCP tool call requires approval,
but approval policy is never`. The corrected body is prepared at
`/tmp/issue-3956-reconciled-pr-body.md`; it checks the verified historical-proof
inspection and unchecks the undelivered merge task. #4518 remains open and ready.
Staging source/tests failed with exit 128 because `.git/index.lock` is on a
read-only filesystem. No commit, push, remote task update or merge occurred.

Each changed Python file was formatted with Black at line length 100 and passes
its individual check. The required repository-wide command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
exited 1 at the multiprocessing forkserver socket (`PermissionError`). A
`BLACK_NUM_WORKERS=1` retry did not complete and was interrupted (exit 130),
so the mandatory formatting gate remains unsatisfied. A commit must wait for
that gate and writable Git metadata. Final readback confirms both #4518 and
#4401 are open with `draft=false`; #4401 remains unmerged at the same head.
The live PR body and any blocker comment/`needs-human` label still require a
writer-capable run; none is claimed here. Existing review/check requirements,
the hosted-baseline gap and the ranking limitation remain in force.

## Single-case mutation receipt validation (2026-11-07 UTC)

The first unchecked acceptance criterion remains blocked on #4401 delivery,
and the next on optional LangSmith plugin startup. This round advances the
retained-evidence criterion: the auditor previously accepted a passing selected
Node case alongside an unrelated assertion failure, and accepted mixed or
multiple Python results as a single-case receipt. It now requires one Python
outcome in the final summary; Node receipts must report the selected case's
actual failed/passed result and exactly one test with matching pass/fail counts.
Unrecognized or mismatched results report incomplete. Receipt commands are never
executed by the auditor.

Validation base: `264e9cc6503be2e1eef1c4a0c3851a6f777f6985`, plus the local
source/test overlay identified by SHA256 in
[auditor-single-case-proof.json](auditor-single-case-proof.json). All 13 new
parameter cases fail the baseline auditor with `assert True is False`, then
pass the corrected auditor independently. Each full receipt records its selected
command, RED exit 1, restored GREEN exit 0, and identical test/configuration
hashes. Outputs were inspected without truncation in groups 0–2, 3–5, 6–9 and
10–12. These local auditor regressions supplement the retained generator/Node
mapping; they are not hosted measurements or main-delivery evidence.

Using `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`:

```sh
python -m pytest tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 3: LangSmith startup calls deprecated asyncio.iscoroutinefunction
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py tests/scripts/test_audit_followup_mutations.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov=scripts.audit_followup_mutations --cov-report=term-missing --cov-report=json:/tmp/issue-3956-single-case-coverage.json
# exit 0; 248 passed: 199 generator + 49 auditor cases
# generator: 851 statements, 0 missing; 386 branches, 1 missing arc; Cover 99.92%
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-single-case-baseline.py --collected-tests /tmp/issue-3956-single-case-collected.txt
# exit 0; 35 added functions / 45 cases; 50 Python + 2 original Node receipts;
# complete=true, problems=[], no row issues. Inputs prepared as above.
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, no failures or skips
ruff check scripts/audit_followup_mutations.py tests/scripts/test_audit_followup_mutations.py
# exit 0
git diff --check
# exit 0
```

Both changed Python files were formatted with Black at line length 100 and pass
individual checks. The required repository-wide Black command exits 1 with
`PermissionError` at the forkserver socket. A single-worker retry was interrupted
(exit 130); a bounded verbose retry timed out after 30 seconds (exit 124),
reporting 504 unchanged files. Neither is a completed passing check, so the
formatting gate still prohibits a Python commit. Staging also exits 128 creating
`.git/index.lock` on the read-only filesystem. No commit or push occurred.

The remote #4401 table defect was independently confirmed against its pinned
head. Attempting only its two-line header/delimiter correction through GitHub's
contents API was rejected: `MCP tool call requires approval, but approval policy
is never`. No remote file, thread or PR body changed, and no merge was attempted.
Final metadata confirms #4401 OPEN, `draft=false`, unchanged head
`9eaf43313c0e57ef964e4171f645985dca5742b8`, `merged=false`; #4518 is also OPEN
and `draft=false`. Main delivery, the comparable hosted reduction and canonical
ranking provenance remain incomplete as distinguished above. No acceptance
checkbox is completed by this local change.

## Required pytest startup correction (2026-11-07 UTC)

Before changing configuration or tests, the requested `gh pr view 4401 --repo
stranske/Workflows --json state,headRefOid,mergeCommit,statusCheckRollup` exited
1 connecting to `api.github.com`. Connected metadata independently reports
#4401 OPEN, `draft=false`, `merged=false`, unchanged head
`9eaf43313c0e57ef964e4171f645985dca5742b8`, and `merged_at=null`. The three
reviews are COMMENTED; the revision-table thread `PRRT_kwDOQprj9M6zZ4AB` is
still unresolved and non-outdated. Two other unresolved threads are outdated.
The first acceptance criterion remains blocked on remote review and delivery.

The next acceptance command was rerun with the repository-selected interpreter
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` and `-m 'not slow'`.
It still fails during LangSmith pytest-plugin import: its beta decorator calls
`asyncio.iscoroutinefunction`, whose Python 3.14 deprecation becomes an error
under the repository warning policy. No generator tests execute. This round
will address that narrowly scoped third-party warning while retaining errors
for other deprecations, rather than treating a plugin-disabled run as acceptance.

Implemented a warning exception restricted to the exact Python 3.14 coroutine
deprecation in `langsmith._internal._beta_decorator`. The new
`tests/test_followup_pytest_runtime.py` verifies that warning is tolerated while
the same warning from application/sibling modules, a different deprecation and
a different warning category still raise. Before the configuration change, its
positive case failed on the deprecation and four protections passed; afterward,
all five pass with plugin autoload enabled. No existing tests or plugins are
disabled by the configuration correction. This is runtime-policy evidence,
separate from the historical assertion-failing retained mutation mapping.

The local validation base is `a678142249d1c588458635ee358640d9a70c8343`, plus
the configuration/new-test overlay identified by SHA256 in
[pytest-startup-proof.json](pytest-startup-proof.json). Generator source and its
199-test retained set, both Node production copies and Node tests are unchanged.
The independently rerun retained audit still reports 35 added functions, 45
parameter cases, 50 Python receipts and two original Node receipts, with
`complete=true`, `problems=[]`. No historical receipt was rewritten.

```sh
PYTEST_ADDOPTS="-m 'not slow'" python -m pytest tests/test_followup_issue_generator.py -q
# exit 0; 199 passed; LangSmith plugin enabled
python -m pytest tests/test_followup_pytest_runtime.py -q -m 'not slow'
# exit 0; 5 passed
python -m pytest tests/test_followup_issue_generator.py tests/test_followup_pytest_runtime.py tests/scripts/test_audit_followup_mutations.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-startup-coverage.json
# exit 0; 253 passed; target Cover 99.92%
# 851 statements, zero missing; 386 branches, one missing arc (124->126)
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, zero failures/skips
ruff check tests/test_followup_pytest_runtime.py
# exit 0
```

Resolving main again returned `00f43f81e51c4f8b9a057ac51f7e3c2d870d7769`;
an immutable read of generator lines 100–145 returned blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00`, still defining and calling
the helper. #4401 remains unmerged. The local passing command advances runtime
validation but cannot complete acceptance against delivered main. No new hosted
measurement, comparable hosted reduction or ranking provenance is claimed.

Black formatted the new Python test at line length 100. The mandatory
repository-wide command `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` exited 1 with `PermissionError` at the
multiprocessing forkserver socket. A `BLACK_NUM_WORKERS=1` attempt produced no
completed result and was interrupted (exit 130). Staging the focused changes
exited 128 because `.git/index.lock` is on a read-only filesystem. Consequently
no commit or push is claimed, and the formatting/commit requirements remain
blocked on the execution environment. No acceptance checkbox is completed by
this local overlay.

Posting the concrete blocker comment and adding `needs-human` to active PR
#4518 were both denied: `MCP tool call requires approval, but approval policy
is never`. No remote comment or label was written. Final metadata confirms
#4518 and #4401 remain OPEN and `draft=false`; #4401 is unmerged at its
unchanged head. The prepared local changes require a writer-capable run.

## Supplemental guard-source regressions (2026-11-07 UTC)

The requested `gh pr view 4401 --repo stranske/Workflows --json
state,headRefOid,mergeCommit,isDraft,statusCheckRollup` exited 1 connecting to
`api.github.com`. Connected metadata still reports OPEN, `draft=false`,
`merged=false`, head `9eaf43313c0e57ef964e4171f645985dca5742b8`, no merge
date. The same revision-table thread `PRRT_kwDOQprj9M6zZ4AB` is unresolved
and non-outdated; the other two unresolved threads are outdated. The PR-reported
main base is now `4928870982db3bc3b85c701b4cca2492128739b2`. Reading the
generator at that immutable revision returns blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00`, still defining and calling
`_blocked_reason_with_source`. This is another undelivered-source readback,
not final main acceptance. The open PR's test-merge SHA is not a delivery SHA.

The existing retained guard regression checks the verification-comment label.
New `tests/test_followup_guard_contract.py` adds two supplemental cases for
blocked original-issue text and Codex logs. They check the exact blocked reason,
payload order and stopping at the blocked payload. The production generator,
its retained 199-test file, both Node production copies and Node tests are
unchanged. These cases supplement the existing repair rather than replace it.

Local source revision: `3667ba73cc170b510fe1c5fcf665777bf962e9e3` plus the
uncommitted new test overlay. The complete supplemental mutation mapping is
[guard-payload-source-proof.json](guard-payload-source-proof.json); it records
both parameter node IDs, full source revision, source/test/configuration hashes,
mutation text and hash, restored source hash, commands and full RED/GREEN output.
Each case independently fails with the relevant reason assertion when source
annotation is removed in an isolated temporary generator, then passes after
exact restoration. Both full outputs were inspected without truncation. No
checkout production source was mutated. This is local regression evidence,
separate from the historical retained mapping, hosted measurements and delivery.

Using `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (Python 3.14.10):

```sh
PYTEST_ADDOPTS="-m 'not slow'" python -m pytest tests/test_followup_issue_generator.py -q
# exit 0; 199 passed; plugins enabled
python -m pytest tests/test_followup_guard_contract.py -q -m 'not slow'
# exit 0; 2 passed
python -m pytest tests/test_followup_issue_generator.py tests/test_followup_guard_contract.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-guard-contract/coverage.json
# exit 0; 201 passed; target Cover 99.92%
# 851 statements, zero missing; 386 branches, one missing arc (124->126)
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file, zero failures
ruff check tests/test_followup_guard_contract.py
# exit 0
black --check --line-length 100 tests/test_followup_guard_contract.py
# exit 0; formatted at line length 100 before validation
```

The retained auditor was independently rerun using the original baseline's
extracted tests and fresh collection of the retained test file. It exits 0:
35 added functions / 45 cases, 50 Python receipts and two Node receipts,
`complete=true`, `problems=[]`. The two new cases live in the separate
supplemental mapping above; historical receipts are unchanged.

The mandatory repository-wide Black command exited 1 with `PermissionError`
at the multiprocessing forkserver socket. A single-worker retry produced no
completed result and was interrupted (exit 130). Staging the new source/test
receipt exited 128: `.git/index.lock` cannot be created on the read-only file
system. No commit or push occurred; the global formatting gate is unsatisfied.

A concrete two-line correction to #4401's revision-table header was prepared
against fetched blob `94e2dfc675112ce6c5736ce03dfdc6f5c8f1c0dc` on
`closer/issue-3956`. Automatic approval review rejected the GitHub contents write:
`MCP tool call requires approval, but approval policy is never`. No remote
source, review thread or PR body changed. A writer-capable run must apply that
correction and settle review before checking complete exact-head gates and
merging. #4518 is also OPEN and `draft=false` at the local source revision.

No acceptance checkbox is completed here. Main delivery, a comparable hosted
baseline for the approximately-60-unit claim and canonical ranking provenance
remain incomplete; these additional local tests cannot replace any of them.

The blocker comment and `needs-human` label on #4518 were also rejected by
automatic approval review with the same approval-policy message. Neither was
written. Final #4401 readback remains OPEN, `draft=false`, unmerged at the same
head; no merge was attempted.

## Delivery-contract regression (2026-11-07 UTC)

Recent commits through `866772b3da731216fa67ee9fdf1823dd96a9ef3a` were
reviewed before continuing. The checked #4401 merge task in #4518 is still
incorrect: connected metadata confirms #4401 OPEN, `draft=false`, unmerged
at `9eaf43313c0e57ef964e4171f645985dca5742b8`. The revision-table thread
`PRRT_kwDOQprj9M6zZ4AB` remains unresolved and non-outdated; all three reviews
are COMMENTED. The requested CLI read exited 1 connecting to `api.github.com`.
An immutable connected read at the PR-reported main base
`4928870982db3bc3b85c701b4cca2492128739b2` confirms generator blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00` still defines/calls the helper.
This is not a newly resolved main pointer or evidence of delivery.

The new supplemental case
`test_guard_repair_does_not_restore_the_coverage_only_helper` directly rejects
the helper-assisted implementation required to be removed by the first
acceptance criterion. It fails by assertion against that immutable main-base
source and passes against the existing repair, without changing production
source or the retained test file. Full isolated RED/GREEN outputs, both source
revisions/hashes, unchanged configuration hash, and the new test-overlay hash
are in [guard-delivery-contract-proof.json](guard-delivery-contract-proof.json).
The output was inspected in full. This new receipt supplements the earlier
two payload-source receipts, which retain their original test-overlay hash;
none is relabeled as current hosted or delivered-main evidence.
The pinned #4401 source is byte-identical to the restored source. Comparing
the retained test AST with original delivery `314895ec5d0b1e102fc80aff8001eae2545ed7fa`
is identical after removing only
`test_blocked_reason_with_source_omits_blank_annotation_for_empty_label`.
Both comparisons and the retained test hash are recorded in the new receipt.

Validation uses `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`, with
production source at `866772b3da731216fa67ee9fdf1823dd96a9ef3a` plus the
identified uncommitted test overlay:

```sh
PYTEST_ADDOPTS="-m 'not slow'" python -m pytest tests/test_followup_issue_generator.py -q
# exit 0; 199 passed; plugins enabled
python -m pytest tests/test_followup_issue_generator.py tests/test_followup_guard_contract.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-delivery-coverage.json
# exit 0; 202 passed; generator Cover 99.92%
# 851 statements, zero missing; 386 branches, one missing arc (124->126)
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, zero failures/skips
ruff check tests/test_followup_guard_contract.py
# exit 0
black --check --line-length 100 tests/test_followup_guard_contract.py
# exit 0; formatted at line length 100 before validation
git diff --check
# exit 0
```

Fresh collection and the baseline extracted from `94d9f952` were supplied to
`scripts/audit_followup_mutations.py`. It exits 0: 35 added functions / 45 cases,
50 Python and two Node receipts, `complete=true`, `problems=[]`, no row issues.
That retained mapping and all historical receipts are unchanged.

The mandatory repository-wide Black command failed with `PermissionError` at
the forkserver socket. Its `BLACK_NUM_WORKERS=1` retry timed out after 60 seconds
(exit 124), reporting 574 unchanged files, so the global gate remains
unsatisfied. Staging exited 128 creating `.git/index.lock` on the read-only
filesystem. No commit or push occurred.

Correcting #4518's checked merge task, posting the concrete blocker comment and
adding `needs-human` were each rejected by automatic approval review:
`MCP tool call requires approval, but approval policy is never`. The prepared
body at `/tmp/issue-3956-reconciled-pr-body.md` unchecks the merge task; it has
not been applied remotely. Final readback confirms #4518 and #4401 are OPEN
and `draft=false`; #4401 remains unmerged at the same head. No acceptance box
is completed. Existing review/gates still need settlement before merge and
main verification; the comparable hosted-baseline gap and unrecoverable ranking
provenance remain owner-visible limitations.

## First-payload stop regression (2026-11-07 UTC)

Reviewed recent commits through `123ae1f130aba042716bec79e1d2559bc9664652`
before changing tests. The required CLI metadata read again failed to connect.
Connected readback still reports #4401 OPEN, `draft=false`, unmerged, at
`9eaf43313c0e57ef964e4171f645985dca5742b8`, with active unresolved thread
`PRRT_kwDOQprj9M6zZ4AB`. All three reviews are COMMENTED. The reported main
base is `4928870982db3bc3b85c701b4cca2492128739b2`; an immutable read there
still defines/calls the helper (blob `c3a19cbf41a476954b8afcde6d214b3cf8c82a00`).
First-page workflow discovery again reports successful Gate `41752024615` and
Selftest CI `41752024817`; it is not a complete expected/required-check receipt.
The first unchecked main-delivery criterion therefore remains blocked.

The new supplemental test `test_guard_stops_after_blocked_verification` verifies
that a blocked first payload returns its source and prevents scanning the issue
or log. The original three supplemental cases retain their names and bodies;
the retained generator test set and production implementation are unchanged.
[guard-first-payload-proof.json](guard-first-payload-proof.json) identifies the
source revision above and test-overlay/configuration hashes. Its isolated mutation
adds an extra issue scan before the blocked return: the new test fails specifically
at the scan-list assertion (exit 1), then passes after restoration (exit 0).
Both outputs were inspected in full. This is supplemental local evidence.

Validation with `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`:

```sh
PYTEST_ADDOPTS="-m 'not slow'" python -m pytest tests/test_followup_issue_generator.py -q
# exit 0; 199 passed; plugins enabled
python -m pytest tests/test_followup_issue_generator.py tests/test_followup_guard_contract.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-first-payload-coverage.json
# exit 0; 203 passed; generator Cover 99.92%
# 851 statements, zero missing; 386 branches, one missing arc (124->126)
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, zero failures/skips
ruff check tests/test_followup_guard_contract.py
# exit 0
black --line-length 100 tests/test_followup_guard_contract.py
# exit 0
```

Fresh baseline extraction from `94d9f952` and collection were passed to the
retained auditor, which exits 0: 35 added functions / 45 cases, 50 Python and two
Node receipts, `complete=true`, `problems=[]`. Historical receipts remain intact.

The task-status correction would uncheck #4518's merge task and check only the
verified historical-percentage attribution criterion. The prepared body is
`/tmp/issue3956-pr4518-body.md`. The #4401 review fix adds the missing Notes
header/delimiter and fills the first two notes cells. Automatic approval review
rejected both writes: `MCP tool call requires approval, but approval policy is
never`. Neither correction was applied remotely. The blocker comment and
`needs-human` label were rejected for the same reason. No review thread was
resolved and no merge was attempted. The comparable hosted-baseline gap,
unrecoverable independent ranking provenance, and main delivery remain open.

The required repository-wide `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` exited 1 at the multiprocessing forkserver
socket with `PermissionError: [Errno 1] Operation not permitted`. A
`BLACK_NUM_WORKERS=1` attempt did not complete and was interrupted (exit 130);
it cannot establish a passing global formatting gate. The changed-file Black
check and `git diff --check` pass. Staging the test and evidence files failed
with exit 128 because `.git/index.lock` cannot be created on the read-only
filesystem. No commit or push occurred. Final connected readback confirms
#4518 and #4401 remain OPEN and `draft=false`; #4401 remains unmerged at the
same full head. No main-delivery acceptance criterion is checked.

## Clean-payload guard regression (2026-11-07 UTC)

Source revision: `95be06402bb4c546309d316b789f39afe1b546ac`. The added
`test_guard_accepts_clean_payloads_and_skips_absent_log` has three cases:
`absent`, `empty`, and `present`. It checks the scan sequence and unchanged
payload text, skips absent/empty optional logs, and requires a clean result to
have an empty reason even when the guard supplies a nonblocking diagnostic.
Production source, the 199 retained generator tests, and the Node tests remain
unchanged. These supplemental cases advance local regression verification;
they do not deliver the existing repair to main.

[guard-clean-payload-proof.json](guard-clean-payload-proof.json) records the
full source revision, source/configuration hashes, test-overlay hash, individual
commands, mutation replacements and complete RED/GREEN output. All six receipts
were read in bounded pairs 0–1, 2–3 and 4–5. Receipts 0/2 add an unexpected
None/empty-log scan; receipt 4 alters the nonempty log text. Each fails the scan
assertion. Receipts 1/3/5 leak the nonblocking diagnostic into the clean result;
each fails the result assertion. All RED exits are 1 with an assertion failure;
all restored GREEN exits are 0 with one passing case. Mutations affect only a
disposable package; checkout production bytes remain unchanged.

Validation with `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`
(Python 3.14.10), plugins enabled, and Node v24.22.2:

```sh
PYTEST_ADDOPTS="-m 'not slow'" python -m pytest tests/test_followup_issue_generator.py -q
# exit 0; 199 passed
python -m pytest tests/test_followup_issue_generator.py tests/test_followup_guard_contract.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue3956-clean-coverage.json
# exit 0; 206 passed; generator Cover 99.92%
# 851 statements, zero missing; 386 branches, one missing arc (124->126)
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; one aggregated passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, zero failures/skips
ruff check tests/test_followup_guard_contract.py
# exit 0
black --line-length 100 tests/test_followup_guard_contract.py
black --check --line-length 100 tests/test_followup_guard_contract.py
# both exit 0; file unchanged
git diff --check
# exit 0
```

Fresh baseline extraction from `94d9f952` and target-test collection were supplied
to `scripts/audit_followup_mutations.py`: exit 0, 35 added functions / 45 cases,
50 Python and two original Node receipts, `complete=true`, `problems=[]`.
The new cases are mapped separately above; historical receipts are preserved.
This is focused local evidence; it cannot fill the comparable hosted-baseline
gap or recover the independent ranking provenance.

Automatic approval review rejected the prepared three-column table correction
on #4401, the correction of #4518's checked merge task, the blocker comment and
`needs-human` label: `MCP tool call requires approval, but approval policy is
never`. No remote write succeeded, no review thread was resolved and no merge
was attempted. Prepared replacement documents are `/tmp/issue3956-review-fix.md`
and `/tmp/issue3956-task-status-fix.md`. Both PRs were read as OPEN,
`draft=false`; #4401 has no merge date. No acceptance checkbox is completed.

Staging only the changed test, new proof and this reconciliation exited 128:
`.git/index.lock` cannot be created on the read-only filesystem. No commit or
push occurred. The mandatory global Black command also encountered a sandbox
forkserver socket `PermissionError`; its single-worker retry is recorded below.

The `BLACK_NUM_WORKERS=1` retry did not finish and was interrupted (exit 130);
it is not a passing repository-wide formatting result. The changed-file Black
check passes, but the global formatting gate remains incomplete and therefore
also prohibits committing Python changes. Final CLI readback still failed to
connect; final connected metadata confirms #4401 and #4518 remain OPEN,
`draft=false`, at their recorded heads, with #4401 `merged=false` and
`merged_at=null`. Main-delivery acceptance remains incomplete.

## PR #4518 continuation acceptance check (2026-11-07)

Real-input retained-receipt audit: **PASS**, checked 2026-11-07 against the
repository's actual evidence files and a fresh collection of its generator tests.
Runnable commands (from the repository root):

```sh
git show 94d9f952dad19f4f8048ae82bb8301bc6baf6ef5:tests/test_followup_issue_generator.py > /tmp/issue-4518-baseline.py
/opt/anaconda3/bin/python3 -m pytest tests/test_followup_issue_generator.py --collect-only -q -m 'not slow' > /tmp/issue-4518-collected.txt
/opt/anaconda3/bin/python3 scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-4518-baseline.py --collected-tests /tmp/issue-4518-collected.txt > docs/evidence/issue-3956/retained-mutation-audit.json
```

The auditor exited 0 and printed `complete=true`, `problems=[]`, 35 added
functions, 45 collected added cases, 50 Python receipts and two Node receipts.
Every generated row now identifies `receipt_file`, `source_revision` and
`historical_index`; supplemental rows retain their separate receipt index.
This command checks retained real-input evidence without re-executing its
historical mutation commands. It establishes receipt consistency, not a new
execution of the generator on production input.

Broader real-input acceptance remains **INCOMPLETE**: this continuation has not
established final main delivery, a comparable hosted baseline for the
approximately-60-unit claim, or the missing independent ranking provenance.
The audit PASS does not complete those acceptance criteria or retroactively
validate historical completion claims.

Continuation validation on 2026-11-07:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_audit_followup_mutations.py tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 0; 265 passed in 1.29s
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 tests passed, zero failures, cancellations or skips
```

```sh
/opt/anaconda3/bin/python3 -m black --check --line-length 100 scripts/ tests/
# exit 0; 725 files would be left unchanged
```

Black also warned that the running Python 3.12 cannot parse every Python 3.13
target syntax; it reported no formatting changes needed in this checkout.
