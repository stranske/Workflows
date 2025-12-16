# Issues 3260 & 3261 — Keepalive Workflow Tracker

_A consolidated evidence log for the keepalive poster (Issue #3260) and detector/dispatcher hardening (Issue #3261). Status tables remain evidence-first: no item flips to “complete” without a linked workflow run, log excerpt, or PR artifact._

> **Status management**: Leave the scope, task, and acceptance criteria checkboxes unchecked until supporting evidence satisfies the paired acceptance criterion. Checking off an item should include an evidence link so the keepalive workflow continues reminding us only while work remains.

---

## Scope

- [x] Issue 3260 — Keepalive poster enhancements validated with live evidence (orchestrator run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) posted round-2 instruction [#3489994704](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489994704) with hidden markers).
- [ ] Issue 3261 — Keepalive detection and dispatch hardening confirmed in production runs.

## Task List

- [x] Capture proof that instruction comments are emitted with required markers and mention on every cycle (instruction [#3489994704](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489994704) from run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) includes all hidden markers and `@codex`).
- [ ] Demonstrate acknowledgment loop behavior, including fallback dispatch when 🚀 is absent.
- [x] Show detector-to-orchestrator hand-off through repository dispatch with populated round/trace metadata (detector run [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) dispatched orchestrator run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) with trace `mhlrf2obd4nlr5`).
- [x] Record guard skip formatting and labelling outputs for failing keepalive rounds (orchestrator run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) posted skip comment [#3489997416](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489997416) and mirrored the summary line).

## Acceptance Criteria

- [x] New instruction comment created each cycle with required markers and `@codex` mention (instruction [#3489994704](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489994704) contains required markers and mention from run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611)).
- [x] Comment author resolves to `stranske` (ACTIONS_BOT_PAT) or `stranske-automation-bot` fallback (run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) authored the instruction as `stranske`).
- [x] PR-meta acknowledgment observed, or fallback dispatch and PR comment emitted when acknowledgment is missing (`Ack keepalive instruction` in run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611/job/54557502956) recorded the 🎉/🚀 loop completing).
- [x] Step summary includes `Round`, `Trace`, `Author`, and `CommentId` fields (summary step in run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) lists these columns).
- [x] Valid instruction comment triggers PR-meta run reporting `ok: true`, `reason: keepalive-detected`, and populated metadata fields (detector run [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) logged the populated summary table for comment [#3489991425](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489991425)).
- [ ] Exactly one orchestrator `workflow_dispatch` fires per accepted instruction comment with matching TRACE and no conflicting cancellations.
- [x] Exactly one `codex-pr-comment-command` repository_dispatch is emitted per accepted instruction comment (detector runs [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) and [#19096425133](https://github.com/stranske/Trend_Model_Project/actions/runs/19096425133) each emitted a single dispatch).
- [x] Guard failures yield PR comment `Keepalive {round} {trace} skipped: <reason>` plus a matching summary entry (orchestrator run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) produced skip comment [#3489997416](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489997416) and summary line).
- [ ] Two consecutive valid rounds produce distinct traces, distinct orchestrator runs, and no duplicate dispatches.

## Issue 3260 — Keepalive Poster Enhancements Progress

### Task Tracking

| Task | Status | Verification Notes |
| --- | --- | --- |
| Helper module exports `makeTrace` and `renderInstruction`. | Complete | `.github/scripts/keepalive_contract.js` normalizes inputs and prefixes the required hidden markers. |
| Orchestrator computes round/trace, selects token, posts comment via helper. | Complete | `Prepare keepalive instruction` job in `.github/workflows/agents-70-orchestrator.yml` resolves round/trace, chooses PAT, and renders the comment body. |
| Summary records round, trace, author, comment ID. | Complete | `Summarise keepalive instruction` step writes all four fields to `$GITHUB_STEP_SUMMARY`. |
| Reaction ack loop with 🎉/🚀 handling. | Complete | `Ack keepalive instruction` adds 🎉 then polls for 🚀 for 60 s at 5 s cadence. |
| Fallback dispatch and PR comment when ack missing. | Complete | Fallback steps emit the repository_dispatch payload and a one-line PR comment when acknowledgment fails. |

### Acceptance Criteria Tracking

| Acceptance Criterion | Status | Evidence |
| --- | --- | --- |
| New instruction comment created each cycle with required markers and @codex. | ✅ Complete | Orchestrator workflow-dispatch [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) posted round-2 instruction [#3489994704](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489994704) containing the hidden markers and explicit `@codex` mention. |
| Comment author resolves to `stranske` (ACTIONS_BOT_PAT) or `stranske-automation-bot` fallback. | ✅ Complete | The same instruction comment [#3489994704](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489994704) is authored by `stranske`, satisfying the allowed-author requirement captured in run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611). |
| PR-meta ack observed or fallback dispatch + comment emitted. | ✅ Complete | Run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611/job/54557502956) shows `Ack keepalive instruction` recording `ACK: yes` after the 🚀 reaction, demonstrating the acknowledgement loop. |
| Step summary includes Round, Trace, Author, CommentId. | ✅ Complete | Step `Summarise keepalive instruction` in run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) writes the summary table with Round 2, Trace `mhlrf2obd4nlr5`, Author `stranske`, and Comment [#3489994704](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489994704). |

### Notes & Local Validation

- 2025-11-04 – Ran `PYTHONPATH=./src pytest tests/test_keepalive_workflow.py` (12 passed) to confirm helper + keepalive workflow coverage.
- 2025-11-04 – Ran `PYTHONPATH=./src pytest tests/test_workflow_agents_consolidation.py` (39 passed) to validate orchestration + PR-meta integration.
- 2025-11-04 – Ran `PYTHONPATH=./src pytest tests/test_workflow_naming.py` (7 passed) to ensure workflow naming conventions remain aligned.
- 2025-11-04 – Ran `PYTHONPATH=./src pytest tests/test_workflow_autofix_guard.py` (3 passed) to verify autofix guard workflow behavior.
- 2025-11-04 – Ran `PYTHONPATH=./src pytest tests/test_workflow_multi_failure.py` (1 passed) to confirm multi-failure handling.
- 2025-11-05 – Guarded `workflow_dispatch` concurrency inputs to prevent push-triggered runs from failing before job execution; awaiting new detector/orchestrator cycle for validation.
- 2025-11-05 – Added detector tolerance for sanitized keepalive markers and expanded coverage via `tests/test_agents_pr_meta_keepalive.py` (5 passed locally); awaiting merged workflow run to consume the fix.

---

## Issue 3261 — Keepalive Detection & Dispatch Hardening Log

### Acceptance Criteria Status

| Acceptance Criterion | Status | Latest Evidence |
| --- | --- | --- |
| Valid instruction comment (allowed author, hidden markers) triggers PR-meta run reporting `ok: true`, `reason: keepalive-detected`, and populated round/trace/PR fields. | ✅ Complete | Detector run [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) auto-inserted the hidden markers on comment [#3489991425](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489991425) and logged `ok = true`, `reason = keepalive-detected`, `round = 1`, `trace = mhlre7vybcsv40`, `pr = 3285` in the summary table. |
| Exactly one orchestrator `workflow_dispatch` fires with matching TRACE and no cancellations from other rounds. | ⏳ In progress | Detector runs [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) and [#19096425133](https://github.com/stranske/Trend_Model_Project/actions/runs/19096425133) each emitted a single dispatch, but round 2 halted at the gate guard; need a CI-idle rerun showing the belt worker progressing. |
| Exactly one `codex-pr-comment-command` repository_dispatch emitted per accepted instruction comment. | ✅ Complete | The same detector runs ([#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085), [#19096425133](https://github.com/stranske/Trend_Model_Project/actions/runs/19096425133)) report `repository_dispatch emitted for PR #3285`, confirming one connector dispatch per instruction. |
| Guard failures yield PR comment `Keepalive {round} {trace} skipped: <reason>` plus matching summary entry. | ✅ Complete | Orchestrator run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) recorded the skip summary and posted PR comment [#3489997416](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489997416) with `Keepalive 2 mhlrf2obd4nlr5 skipped: gate-run-status:in_progress`. |
| Two consecutive valid rounds produce distinct traces, distinct orchestrator runs, and no duplicate dispatches. | ❌ Not satisfied | Guard stop on round 2 prevented observing back-to-back belt executions; still awaiting consecutive runs that both complete. |

### Task List Status

| Task Group | Task | Status | Latest Evidence |
| --- | --- | --- | --- |
| PR-meta detector | Ensure `actions/checkout@v4` occurs before loading detector script. | ✅ Complete | Detector run [#19096651969](https://github.com/stranske/Trend_Model_Project/actions/runs/19096651969/jobs/54558266617) shows `actions/checkout@v4` preceding the detection script. |
| PR-meta detector | Enforce allowed authors + hidden markers, surface structured outputs. | ✅ Complete | Run [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) auto-inserted markers and emitted the populated summary table, proving the enforcement path. |
| PR-meta detector | Add 🚀 dedupe and dispatch orchestrator (`workflow_dispatch`) + connector (`repository_dispatch`). | ✅ Complete | Detector runs [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) and [#19096425133](https://github.com/stranske/Trend_Model_Project/actions/runs/19096425133) each produced exactly one orchestrator dispatch and one `codex-pr-comment-command` event. |
| PR-meta detector | Emit summary table on every run. | ✅ Complete | Job summary in run [#19096651969](https://github.com/stranske/Trend_Model_Project/actions/runs/19096651969/jobs/54558266617) renders the Markdown table with `ok`, `reason`, and `comment` columns. |
| Orchestrator | Parse `options_json`, export TRACE/ROUND/PR, configure `concurrency` without cancel-in-progress. | ✅ Complete | Workflow-dispatch [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) echoes keepalive metadata into environment variables while running under the non-cancelling concurrency group. |
| Orchestrator | Post `Keepalive {round} {trace} skipped:` PR comment + summary when guard fails. | ✅ Complete | Skip path in run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) posted comment [#3489997416](https://github.com/stranske/Trend_Model_Project/pull/3285#issuecomment-3489997416) and logged the same line in the job summary. |
| Orchestrator | Filter assignees to humans; skip gracefully when none remain. | ⏳ In progress | Guard auto-assigns humans and applies `agents:keepalive`/`agent:codex` labels (commit `e3dc4c65`); confirmation pending live run. |

### Evidence Log

| Timestamp (UTC) | Event | Notes |
| --- | --- | --- |
| 2025-11-02 09:14 | Issue synced by workflow run [#19060644912](https://github.com/stranske/Trend_Model_Project/actions/runs/19060644912) | Baseline import from topic GUID `c99d3476-9806-5144-8a69-98a586644cbd`. No compliant runs yet. |
| 2025-11-04 17:59 | Gate workflow run [#19078172801](https://github.com/stranske/Trend_Model_Project/actions/runs/19078172801) | Shows current failure mode (coverage test AttributeError); lacks TRACE propagation. |
| 2025-11-04 22:24 | Orchestrator run [#19084601666](https://github.com/stranske/Trend_Model_Project/actions/runs/19084601666) | Workflow ended before job steps; no TRACE export or skip comment. |
| 2025-11-04 22:25 | Agents PR meta manager run [#19084629319](https://github.com/stranske/Trend_Model_Project/actions/runs/19084629319) | Detection table `ok=false`, `reason=not-keepalive`; dispatch hooks dormant awaiting hidden markers. |
| 2025-11-04 23:08 | Updated orchestrator idle precheck for explicit keepalive dispatches. | Should allow detector-triggered runs to reach keepalive jobs even without open agent issues; validation pending. |
| 2025-11-04 23:16 | Normalized keepalive skip comment format in orchestrator guard. | Guarantees `Keepalive {round} {trace} skipped: <reason>` comment + summary; awaiting skip event. |
| 2025-11-04 23:24 | Added comment metadata + specific missing-round reason to detector. | Detector now emits comment ID/URL and differentiates missing round markers; summary table gains comment column. Awaiting live run. |
| 2025-11-04 23:31 | Forwarded keepalive round/trace with repository dispatch. | Codex dispatch attaches round/trace and falls back to detector comment metadata; awaiting valid keepalive for evidence. |
| 2025-11-04 23:38 | Keepalive guard auto-labels PR before failing. | Guard attempts to apply `agents:keepalive` / `agent:codex` labels before logging skip; validate on next label-missing case. |
| 2025-11-04 23:48 | Added harness + pytest coverage for detector metadata + missing-round reason. | `tests/test_agents_pr_meta_keepalive.py` asserts new outputs using fixtures under `tests/fixtures/agents_pr_meta/`. |
| 2025-11-05 00:38 | Agents PR meta manager run [#19087372965](https://github.com/stranske/Trend_Model_Project/actions/runs/19087372965) | Detection/dispatch jobs skipped; no summary or metadata emitted. |
| 2025-11-05 00:48 | Agents PR meta manager run [#19087550353](https://github.com/stranske/Trend_Model_Project/actions/runs/19087550353) | Push-triggered run ended before jobs; detector evidence still pending. |
| 2025-11-05 00:49 | Orchestrator run [#19087550223](https://github.com/stranske/Trend_Model_Project/actions/runs/19087550223) | Workflow terminated at setup; skip comment & summary unverified. |
| 2025-11-05 01:05 | Guarded `workflow_dispatch` concurrency inputs. | `.github/workflows/agents-70-orchestrator.yml` now short-circuits missing inputs to prevent push-triggered job failures. Awaiting next detector/orchestrator cycle. |

### Upcoming Verification Steps

1. ✅ Detector run [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) captured a keepalive instruction with hidden markers and populated metadata (`dispatch=true`, `reason=keepalive-detected`, trace/round/PR recorded).
2. ✅ Orchestrator run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) propagated TRACE/ROUND, produced the instruction comment, and completed the acknowledgment loop.
3. ✅ Detector runs [#19096404085](https://github.com/stranske/Trend_Model_Project/actions/runs/19096404085) / [#19096425133](https://github.com/stranske/Trend_Model_Project/actions/runs/19096425133) each emitted exactly one `codex-pr-comment-command` dispatch for their accepted instruction comments.
4. ✅ Skip guard in run [#19096414611](https://github.com/stranske/Trend_Model_Project/actions/runs/19096414611) posted `Keepalive 2 mhlrf2obd4nlr5 skipped: gate-run-status:in_progress` and mirrored the summary line.
5. 🔄 Run two valid consecutive rounds to ensure distinct traces, no duplicate dispatches, and absence of cancellations.
