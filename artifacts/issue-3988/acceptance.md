# Workflows #3988 operational acceptance evidence

Follow-up: [#4515](https://github.com/stranske/Workflows/issues/4515).
Checked 2026-11-09 UTC. **Overall acceptance: NOT ESTABLISHED.** The actual
production step summary and its posterior/capacity condition remain unverified.
No production repair is demonstrated or included in this evidence PR.

Round 7 verification (2026-11-09): **T2 and T4 verified; T3/A3 remain
UNVERIFIED; A4 FAILS.** Repeated the isolated merge-commit mutation: 55/74
passed and 19 failed, including the named source/template top-pool-shed cases.
Restored both policy files byte-for-byte (SHA-256 receipts in
[round7-verification.json](round7-verification.json)); both named commands then
passed 74/74. New full transcripts are retained as `round7-*.txt`, alongside
all earlier transcripts. The PR body retains the original full transcripts.
Direct inspection of both current workflow files confirms the chooser,
DEFAULT_AGENT propagation and awaited summary writing remain present.
The live candidate check-run API again returned `output.summary: null`; see
[round7-check-run-summary.json](round7-check-run-summary.json). Therefore no
qualifying production summary/condition is asserted and T3 is not complete.

The previous literal-label PASS is insufficient for A4: `agent:auto` names no
provider and may select Codex. The acceptance metric now requires the **first**
routing label to name a non-Codex provider, conservatively handling same-second
mixed labels. This is 13/51 = 25.49%, below 30%. The historical literal-label
metric (17/51) and later first-concrete-label metric are retained separately;
neither replaces the first-label acceptance calculation. This corrects an
evidence verdict, not production routing. Stop rule: one evidence pass and
one mutation/restoration cycle, within 30 minutes. No production repair.

Round 6 validation (2026-11-09): the issue-consistency gate reproduced a
header mismatch because the collector's example invocation contained the
historical artifact directory's issue slug. Rewording that docstring leaves
collector behavior unchanged. The following command now exits 0 and reports
`Issue consistency check passed for #4515`:

```sh
/opt/anaconda3/bin/python3 scripts/check_issue_consistency.py --base-sha d17b088aa5c97e6b024101c39252480c622e8395 --pr-title 'Record #4515 routing acceptance evidence and remaining live-proof gap' --head-ref orch/issue-4515
```

Both named Node commands were rerun on a fresh archive of the exact merge
commit and each passed 74/74. PR #4505 checks still show the successful
suite-bearing JavaScript job and the separate failed keepalive job. Both full
mutation/restoration transcripts were matched against the current PR body.
Saved-history replay still reports 17/51 and complete coverage. The production
summary/condition gap remains unresolved; this gate repair does not establish
overall acceptance. Stop rule for this repair: two attempts or 20 minutes.

## Outcome, command and stop rule

The real-input outcome is a non-Codex first-routing-label share of at least 30%
over the complete first 48 hours after [PR #4505](https://github.com/stranske/Workflows/pull/4505)
merged, accompanied by a real non-Codex intake default under the specified
posterior/capacity condition. Merge commit:
`3e7f75d3750e54a1453cf9ea0ce4ed048bf24288`.

The observation window is **[2026-11-07T02:51:20Z, 2026-11-09T02:51:20Z)**;
the complete window had elapsed before collection. The read-only collector
prints the numerator, denominator, share, coverage and literal-label verdict:

```sh
/opt/anaconda3/bin/python3 artifacts/issue-3988/collect_observations.py
```

It invokes `gh api` for explicitly approved repository PR lists and each
in-window PR's timeline. To reproduce the calculation without further API reads:

```sh
/opt/anaconda3/bin/python3 artifacts/issue-3988/collect_observations.py --from-saved
```

Stop rule recorded before implementation: at most two attempts per failed
evidence query and 60 minutes total. Summary retrieval stopped after the API
returned no summary and the available web/browser routes failed to expose it.
No local full suite, new production dispatch, label mutation, or routing repair
was run. Only the two issue-named Node test commands were executed locally.

## Acceptance matrix

| Criterion | Observed result | Status |
| --- | --- | --- |
| Both named Node commands on the merge commit; successful CI containing the suite | Both pass 74/74; successful suite-bearing CI linked below | PASS |
| Deliberate-break and restored-green transcripts in the implementing PR body | Isolated mutation produces the named top-pool-shed failures; restored bytes pass 74/74; full transcripts included in PR body | PASS |
| Real post-merge non-Codex DEFAULT_AGENT summary under the specified condition | Real logs establish a Cursor default, but actual summary and posterior/pool values were not retrieved | UNVERIFIED |
| Complete 48-hour non-Codex first-routing-label share >=30% | First-label non-Codex provider share 13/51 = 25.49%; four `agent:auto` labels are not provider evidence | FAIL; below 30% |

## Exact-merge tests and deliberate break

An isolated archive of the merge commit was extracted under
`/private/tmp/issue-4515-merge`. Node version: `v24.3.0`.

| Command | Original merge | After restoration |
| --- | --- | --- |
| `node --test tests/scripts/test_agent_delegation_policy_intake.js` | exit 0, 74 passed, 0 failed | exit 0, 74 passed, 0 failed |
| `node --test .github/scripts/__tests__/agent-delegation-policy-intake.test.js` | exit 0, 74 passed, 0 failed | exit 0, 74 passed, 0 failed |

In **both isolated policy copies only**, temporarily replace
`const poolState = getAgentPoolState(routeWeights, candidate, row);` with
`const poolState = 'ok';`. Run the first named command unchanged. It exits 1:
55 passed, 19 failed. The source and template
`top pool shed and next exhausted -> highest remaining ok agent` tests select
Claude (0.88) instead of the expected Codex (0.62). The named
`top pool shed -> next agent` test also fails with `'claude' !== 'cursor'`.

Restore both originals in a `finally` block, verify byte equality against
`git show <merge>:<path>`, and rerun both named commands green. No mutation
entered the provisioned branch. Hashes, commands and exit codes are in
[provenance.json](provenance.json). Full original, mutation and restored
transcripts are retained in this directory; historical evidence was not
replaced (no versioned `artifacts/issue-3988/` files existed on the provisioned
base or merge commit).

## PR #4505 CI

Executed the issue-named command:

```sh
gh pr checks 4505 --repo stranske/Workflows
```

The [Selftest CI run](https://github.com/stranske/Workflows/actions/runs/42328604172)
succeeded. Its [JavaScript Tests job](https://github.com/stranske/Workflows/actions/runs/42328604172/job/128269684942)
ran the discovery glob and logged passing source/template top-pool-shed tests.
[The retained log excerpt](pr-4505-ci-suite-excerpt.txt) proves the suite was
actually present; the discovery wrapper requires the issue's direct suite.
This CI run is on the PR head `ae822033ad6e23baa44070b0ab91fe81da593158`,
before merge; the local narrow runs above are on the exact merge commit.

The checks command exits 1 because the later **Keepalive next task (Codex)**
job failed. Therefore this report does **not** claim that every PR check passed.
The full checks readback is retained in [pr-4505-checks.txt](pr-4505-checks.txt).

## Direct workflow inspection and real intake evidence

Directly inspected the merge-commit source and consumer workflow copies:

- [Source intake workflow](https://github.com/stranske/Workflows/blob/3e7f75d3750e54a1453cf9ea0ce4ed048bf24288/.github/workflows/agents-63-issue-intake.yml#L1418): when the bridge input is empty, fetch weights, load the registry, and call `chooseAgentForIntake('implement', routeWeights, registry.agents)` before resolving `defaultAgent`.
- [Consumer intake workflow](https://github.com/stranske/Workflows/blob/3e7f75d3750e54a1453cf9ea0ce4ed048bf24288/templates/consumer-repo/.github/workflows/agents-issue-intake.yml#L152): the same chooser/default/summary sequence.

Both assign `intakeChoice.agent` to `process.env.DEFAULT_AGENT` only when the
bridge input is empty, then resolve `defaultAgent`. Both await `core.summary`
writing Chosen Agent, Posterior, Pool State and Default Agent. Explicit input
and existing routing labels retain their documented precedence. The actual
merge-commit excerpts and line numbers are in [workflow-wiring.txt](workflow-wiring.txt).
This is direct source inspection, not a claim that a production summary was seen.

A real post-merge candidate is [intake run 42353296252](https://github.com/stranske/Workflows/actions/runs/42353296252),
[Validate Codex issue labels job](https://github.com/stranske/Workflows/actions/runs/42353296252/job/128345864413),
created 2026-11-07T07:55:49Z on `d2106cc83e060d0063f63dd08ea94bbaa4104fbf`.
The executed log, with an empty bridge input, says:

```text
2026-11-07T07:55:59.5554356Z   INPUT_ISSUE: 4523
2026-11-07T07:55:59.5555106Z   DEFAULT_AGENT:
2026-11-07T07:55:59.7123093Z Overriding bridge agent 'cursor' with 'claude' from labels.
```

The override message establishes that `defaultAgent` was Cursor before the
existing issue label selected Claude. It does not establish final routing to
Cursor. See [live-intake-log-excerpt.txt](live-intake-log-excerpt.txt).

**Unresolved:** the REST check-run `output.summary` is null, the public HTML
does not expose the step summary, and the browser host was unavailable. The
actual table and the historical posterior/pool condition could not be read.
Do not substitute the log inference or a synthetic run for that criterion.
All 29 successful source intake runs in the window were inspected; retained
execution lines are in [intake-run-inspection.json](intake-run-inspection.json).
Later runs also show static fallback because the export was unavailable or
stale. Their non-Codex label overrides are not capacity-aware chooser evidence.

## Complete fleet observation

Fleet scope: the 16 consumers in `REGISTERED_CONSUMER_REPOS` at the merge
commit, plus source Workflows. Direct owner exclusions are applied before API
requests or inventory output. All 17 repositories were accessible. All 147
in-window PRs, open and closed, were enumerated by creation time. Every PR's
timeline was exhausted: **zero unavailable histories**. Per-repository saved
histories include label additions and removals, IDs, timestamps, source URLs,
and pagination counts. This avoids survivorship bias from current labels.

Eligibility requires an in-window creation time and an `agents:keepalive`
addition before the window ends, even if subsequently removed. There are
51 eligible PRs and 96 explicit non-keepalive exclusions. No branch name,
author, current label, or later delegation substitutes for a first label.

| Repository | All in-window PRs | Eligible keepalive PRs | Literal non-Codex first labels (includes auto) |
| --- | ---: | ---: | ---: |
| Workflows | 43 | 21 | 6 |
| Travel-Plan-Permission | 3 | 0 | 0 |
| Template | 2 | 0 | 0 |
| Counter_Risk | 2 | 0 | 0 |
| Pension-Data | 3 | 1 | 1 |
| Inv-Man-Intake | 2 | 0 | 0 |
| Ready | 3 | 0 | 0 |
| trip-planner | 11 | 5 | 2 |
| Manager-Database | 4 | 1 | 1 |
| Portable-Alpha-Extension-Model | 3 | 1 | 0 |
| Trend_Model_Project | 12 | 4 | 2 |
| learning-management-system | 3 | 0 | 0 |
| Fine-Art-Archive | 2 | 0 | 0 |
| Orchestrator | 48 | 18 | 5 |
| Doc-Lineage | 2 | 0 | 0 |
| Deliverable-Render | 2 | 0 | 0 |
| Manager-Mosaic | 2 | 0 | 0 |
| **Total** | **147** | **51** | **17** |

The named suite explicitly treats `agent:auto` as a routing label. Counting
literal first `agent:*` labels therefore yields a conservative **17/51 =
33.33%**, including four `agent:auto` first labels. Orchestrator #1275 has
same-second `agent:codex`/`agent:auto` events: its ordering is treated as
ambiguous, contributing zero to the guaranteed numerator. The upper bound is
18/51 = 35.29%; the lower bound already exceeds 30%. Workflows #4559 has no
routing-label event; its complete history establishes absence within the
window, so it remains in the denominator and contributes zero.

This literal result is weaker than demonstrated provider redistribution.
Excluding `agent:auto`, **13/51 = 25.49%** first name a non-Codex provider:
six Gemini, five Vibe, one Claude, one Cursor. Five PRs have no concrete
provider-routing label in the window. Counting auto-selection intent as a
non-Codex execution would overstate what was observed.

The complete machine-readable result, coverage, individual eligible PRs,
first events, exclusions, numerator/denominator and timestamps are in
[routing-observations.json](routing-observations.json). The evidence measures
labels, not provider execution, pool state at assignment, or causal effect
of PR #4505. The original issue's separate zero-shed-assignment aspiration
cannot be evaluated without historical capacity at each assignment.

## Outstanding evidence

The production summary and its historical posterior/capacity condition still
need direct evidence before T3/A3 can be marked complete. A4 fails the measured
first-label provider threshold (25.49%); a closed historical window cannot be
made to pass by rerunning collection or changing current labels.
The preserved logs and first-label study do not fill that gap. The merged
capacity fix is preserved; no unrelated workflow or policy repair was made.

## Round 8 format repair — 2026-11-09

Reproduced the reported Black failure on `collect_observations.py` using
Black 26.10.1, then applied its formatting to the nested verdict expression.
`/opt/anaconda3/bin/python3 -m black --check artifacts/issue-3988/collect_observations.py`
passes. The Python 3.12 runtime warns about the configured Python 3.13 target;
an explicit `ast.dump(ast.parse(...))` comparison of the original and formatted
file also passes, establishing AST equivalence for this change.

Both issue-named Node commands pass on the repaired branch (74/74 each).
`gh pr checks 4505 --repo stranske/Workflows` still reports successful
suite-bearing JavaScript CI and the separate failed post-merge Codex keepalive
job. Saved-history replay via
`/opt/anaconda3/bin/python3 artifacts/issue-3988/collect_observations.py --from-saved`
produces byte-identical observation JSON: complete coverage, acceptance share
13/51 (25.49%), verdict FAIL. T3/A3 remain unproved and A4 remains unsatisfied.
No new fleet collection or production-routing change was made in this round.

## Round 9 remaining-criteria verification — 2026-11-09

**Outcome: T3/A3 UNVERIFIED; A4 FAIL (13/51 = 25.49%).** The command
`/opt/anaconda3/bin/python3 artifacts/issue-3988/collect_observations.py --from-saved`
prints the acceptance metric and FAIL verdict in under two minutes. This
round's stop rule was one evidence pass and at most one targeted repair within
30 minutes. No production repair was justified by the evidence collected.

Directly inspected both current workflow files again: each calls
`chooseAgentForIntake('implement', routeWeights, registry.agents)`, propagates
the chooser result into an empty `DEFAULT_AGENT`, resolves `defaultAgent`,
and awaits the summary table write. Current file hashes and inspected line
numbers are retained in [round9-verification.json](round9-verification.json).
The existing [candidate production job](https://github.com/stranske/Workflows/actions/runs/42353296252/job/128345864413)
still returns null summary and text from the check-run API. The browser
lookup failed with `native pipe is closed`, so no production summary was
observed. The earlier Cursor log remains evidence of a default, but cannot
establish the missing historical posterior/capacity condition. T3 and A3
remain unchecked.

Saved-history replay produced byte-identical observation JSON, preserving
complete coverage and the failing first-label provider share. A4 remains
unchecked: the fixed historical window cannot be repaired with current label
changes. The table above is now explicitly headed as the historical literal
metric so its 17 total cannot be mistaken for the acceptance numerator of 13.
No new fleet API collection was necessary or performed.

Both named Node commands passed again on this branch, 74/74 each; full output
and exit codes are in the receipt. `gh pr checks 4505 --repo stranske/Workflows`
again showed passing JavaScript Tests and the separate failed Codex keepalive
job. No full suite was run. This round adds verification evidence only and
does not claim completion of any remaining task or criterion.

## Round 10 remaining-criteria verification — 2026-11-09

**Outcome: T3/A3 UNVERIFIED; A4 FAIL (13/51 = 25.49%).** Checked on
branch head `a1f87d31989ec23e13343a631893ba496ab524aa`. Stop rule: one
evidence pass, at most 30 minutes. The pass finished without a production
change. The reproducible real-input check remains:

```sh
/opt/anaconda3/bin/python3 artifacts/issue-3988/collect_observations.py --from-saved
```

It prints complete coverage and the failing acceptance metric in under two
minutes; the observation JSON remains byte-identical. The fixed historical
window cannot be changed by a present-day repair. No new fleet queries were
needed for this replay.

Direct inspection of both current intake workflows confirms the chooser
call, empty-input DEFAULT_AGENT propagation and awaited summary-table write.
The live candidate job log was fetched again and still shows Cursor as the
default before a Claude label override. The live check-run API again returns
null summary/text, and browser retrieval failed with `native pipe closed
before response`. Neither the actual production summary nor its historical
posterior/capacity condition was observed. Consequently the inspection
portion of T3 is verified, but T3 as a whole and A3 remain unchecked.

Both issue-named Node commands pass 74/74 on this branch. PR #4505 checks
still include the successful suite-bearing JavaScript job and the separate
failed Codex keepalive job. Full command outputs, live API/log readback and
workflow hashes/line references are in
[round10-verification.json](round10-verification.json). Historical receipts
are retained. No remaining criterion is newly completed by this round.
