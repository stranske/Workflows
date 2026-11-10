# PR #4470 continuation evidence

Checked 2026-11-10. Existing productive changes on `cursor/issue-3901` are preserved.
The previous summary overstated completion: green old-head CI and local linkage
fixtures did not establish final-head review, required ancestry execution, merge,
or post-merge verification. Those remain separate delivery gates.

## Acceptance and stop rule (recorded before edits)

Outcome: `report_delivery_failures=0`; check started 2026-11-10T18:32:44Z.
Focused command:
```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_report_sentence_delivery.py -q -s -p no:cacheprovider --override-ini=addopts=
```
Printed `required_channels=['comments'] comments_absent_verdict=CONCERNS
comments_unavailable_verdict=UNVERIFIABLE_INPUT comments_present_verdict=PASS
report_delivery_failures=0`; `1 passed in 1.09s`.
The unmodified invocation first hit a globally installed pytest-asyncio deprecation
configured as an error before collection. Plugin autoload was disabled explicitly;
no repository dependency pins were changed.
Stop after three repair attempts or 2026-11-10T19:02:44Z. Attempt 1 addresses the
required ancestry skip only. Other findings stay outside this acceptance push.
No preserved holder for this branch was listed by `git worktree list --porcelain`;
local and remote branch heads matched `41c1516a2d2d6496c29a40b4bb4d03d5329c160f`.

## Independently re-read historical FULL delivery

These exact commands retrieved full logs, not just workflow conclusions:
```sh
gh run view 41128486728 --repo stranske/Workflows --log
gh run view 41128622575 --repo stranske/Workflows --log
gh run view 41132061438 --repo stranske/Workflows --log
gh pr view 3900 --repo stranske/Workflows --json state,mergedAt,mergeCommit
git merge-base --is-ancestor 8ec052a1fdc32319165011a7e465d6710c7ef4b5 306fc9e79d891030395211fdae8ae1387f2b37c3
```
All three runs concluded success on source `306fc9e79d891030395211fdae8ae1387f2b37c3`.
Plan: `sha256:1a22f551228736c4279b2b5434baffbb0e6d5b697dc43727bf5d7f808209dc0b`, scope `full`.
#3900 is MERGED at `2026-10-15T01:32:54Z`, merge `8ec052a1fdc32319165011a7e465d6710c7ef4b5`.
The ancestry command returned **0**, independently of the fixture validator.

- [Qualification 41128486728](https://github.com/stranske/Workflows/actions/runs/41128486728): notice at 2026-10-30T21:07:36Z says canaries green 3/3, blocked none, promotion dispatched with the exact plan/source. Its three `campaign_prepared` rows match the canary heads below.
- [Promotion 41128622575](https://github.com/stranske/Workflows/actions/runs/41128622575): `REQUESTED_PHASE: promote`; exact plan/source; notice at 21:09:48.565Z dispatched Maint 71 campaign reconciliation. [41128913051](https://github.com/stranske/Workflows/actions/runs/41128913051) was created at 21:09:48Z on the same source. The dispatch log does not print its resulting run ID; the time/source association supports that linkage, rather than a direct parent-ID receipt.
- [Continuation 41130701739](https://github.com/stranske/Workflows/actions/runs/41130701739) also concluded success on the source. It and 41128913051 are intermediate reconciliation runs, not separate FULL plans; the three requested logs do not independently prove a causal parent edge for every continuation.
- [Terminal reconciliation 41132061438](https://github.com/stranske/Workflows/actions/runs/41132061438): the campaign commit authorization at 21:36:59.017Z has `authorized:true`, the exact plan/source, and the 16 exact head rows. This differs from the separate `Candidate evidence authorized: false` log field; do not conflate the two authorization types. Terminal totals at 21:40:29Z: **Merged: 16; Failed: 0; Pending: 0**. Every table head occurs in a `status: merged` row with the exact plan/source.

The run also printed **13 branch cleanup failures**; these are not delivery failures.
The raw refresh notice includes `delivery report has no stable base refresh request`,
three `missing_canary_evidence` diagnostics, `missing_or_mixed_canary_plan`, and
`missing_or_mixed_canary_plan_scope`. The fixture's single refresh error is a
normalized interpretation after the kept empty-request fix, **not a verbatim raw
historical notice**. No fresh FULL campaign was launched.

| Consumer PR | Exact delivered head | Canary |
| --- | --- | --- |
| stranske/Travel-Plan-Permission#1715 | `80ae115d052d8668e048d4d3f30b1feaf0e3be09` | yes |
| stranske/Template#1097 | `3fc4565e95f38d3867d1b7f4759ca961e7a795c2` |  |
| stranske/Counter_Risk#1224 | `7058ca246d94b740785c252835c7ab6237bcb421` |  |
| stranske/Pension-Data#1007 | `88d98c77481ff012db1dc38b94b11150c7d4a3ac` |  |
| stranske/Inv-Man-Intake#1060 | `333b9dea43bbf91cea1c6f334ced4b66332662ef` |  |
| stranske/Ready#661 | `94a6f8f929e87b5d9a9714911bb245dc3b59d384` |  |
| stranske/trip-planner#1954 | `b900b51f7f4488dd222736686a0d5c720c7c9148` | yes |
| stranske/Manager-Database#1872 | `2bbb88acefe8961eef3a091ba3d084cac1e05084` |  |
| stranske/Portable-Alpha-Extension-Model#2452 | `eee634cd09e283e218e4670d15bba62de61bcde8` | yes |
| stranske/Trend_Model_Project#6180 | `ec2b575cd9379425db8096b57f3835aa2466b8c0` |  |
| stranske/learning-management-system#814 | `ef2406e8b0c348ba7cdcd5ba080e354cca1bfcb7` |  |
| stranske/Fine-Art-Archive#865 | `2747012a4d3c0730d9ce09b468a2ebdbd88db992` |  |
| stranske/Orchestrator#1016 | `29aaf359c9d81b2b4a0a8f50d4c0e65fe2ce5b14` |  |
| stranske/Doc-Lineage#166 | `3e42ab7243eadd39322697b8251e478681b1a450` |  |
| stranske/Deliverable-Render#125 | `a4d2026d88aaad5762b970643c27187f0202206b` |  |
| stranske/Manager-Mosaic#141 | `ae747511212875ddb0007e3cc343c48bbae228bb` |  |

Retrieved log SHA256 checksums (for reproducibility; source remains Actions):
```
41128486728 512f6cc535ad497aa9ffa9639ac7b0fb604f9879005dc895a7ee13dada76ca67
41128622575 041ee007f67b7d5c93dfd5b9182c065a06cb19d2fadd9252db1504d749f1703b
41132061438 622ebef65db3271345acbdc615019ed60e79ae8fdf58ed7a8c5d447fbff5ff72
```

## Review dispositions

- `PRRT_kwDOQprj9M60qnKy`: decline the proposed mock reversal. Run 30 skips authorization; run 31 authorizes and then cancels. An authorized newer cancellation must remain a hold. Changing all but run 21 to skipped removes the scenario being tested. All three changed JS test files pass together (435 passed, 0 failed, 0 skipped).
- `PRRT_kwDOQprj9M60qnLt`: optional malformed-CI matrix deferred. Existing exact-head mismatch and missing-channel tests pass; no observed production failure justifies expanding this acceptance push.
- `PRRT_kwDOQprj9M60qnL2`: accepted. Required reusable Python test job now fetches the fixed source since 2026-10-14, bounded by a two-minute step timeout, checks merge-base, and requires the ancestry test to fail rather than skip if history is missing. Other consumers lacking this test remain unaffected. A separate two-minute focused pytest step runs the named ancestry test before cache restoration and the matrix suite; hosted execution must still be read back.
- `PRRT_kwDOQprj9M60qnL7`: existing targeted fixes reject non-mapping stages, false/float terminal counts and non-boolean refresh eligibility. The named linkage tests pass; the optional broad matrix is deferred.
- `PRRT_kwDOQprj9M60qnMC`: optional additional negative-path matrix deferred. Existing source linkage tests verify missing channels, exact-head mismatch, NON_PASS preservation and guarded-merge evidence. Their passing results do not claim exhaustive validator coverage.

## Exact local validation commands

Interpreter: `/opt/anaconda3/bin/python3`, Python 3.12.2. Black 26.10.1; Ruff 0.17.1.
```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_pr_verifier_delivery_destinations.py -k 'report or record' -q -p no:cacheprovider --override-ini=addopts=
# 1754 passed, 22719 deselected in 13.00s
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 WORKFLOWS_REQUIRE_3900_ANCESTRY=1 /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_consumer_regeneration_linkage.py tests/scripts/test_source_delivery_linkage.py -q -s -p no:cacheprovider --override-ini=addopts=
# 18 passed in 0.17s before adding the required-history failure regression; ancestry executed, no skip.
node --test .github/scripts/__tests__/maint71_merge_sync_prs.test.js .github/scripts/__tests__/scoped-canary-refresh.test.js .github/scripts/__tests__/sync_pr_merge_contract.test.js
# 435 passed, 0 failed, 0 skipped; 666ms
/opt/anaconda3/bin/python3 -m black --check scripts/langchain/_llm_client.py scripts/langchain/pr_verifier.py tests/scripts/test_consumer_regeneration_linkage.py
/opt/anaconda3/bin/python3 -m ruff check scripts/langchain/_llm_client.py scripts/langchain/pr_verifier.py tests/scripts/test_consumer_regeneration_linkage.py
cmp scripts/langchain/pr_verifier.py templates/consumer-repo/scripts/langchain/pr_verifier.py
# Black unchanged; Ruff All checks passed!; parity exit 0.
```
Black printed an interpreter/target warning (3.12 runtime versus 3.13 target) but returned 0.
No full local test suite was run. A focused reusable-workflow test initially failed
because disabling plugin autoload also disabled pytest-cov in its child process;
its rerun explicitly loads `pytest_cov.plugin` through `PYTEST_PLUGINS`.

## Delivery boundary

Final-head hosted review, CI, guarded merge and post-merge disposition are pending
at this record's creation. A push alone does not trigger or prove all those stages.
The authorized guarded-merge/verifier lanes own continuation after review/CI.
Blocking/drainable pair: merge blocked until current-head required CI and review;
drainable work is the bounded ancestry proof and evidence-backed thread dispositions.
Historical #3902 provider CONCERNS / durable **NON_PASS** remains unchanged.

Final focused rerun (including new required-history failure regression):
```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_PLUGINS=pytest_cov.plugin WORKFLOWS_REQUIRE_3900_ANCESTRY=1 /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_consumer_regeneration_linkage.py tests/scripts/test_source_delivery_linkage.py tests/workflows/test_reusable_ci_workflow.py -q -p no:cacheprovider --override-ini=addopts=
```
Printed **62 passed in 6.40s**, zero skips. A fresh empty `/tmp` repository using
exactly the new bounded `git fetch` command also returned `bounded_fetch_ancestry_exit=0`.
Final Black check: 3 files unchanged; Ruff: All checks passed; parity: exit 0.
