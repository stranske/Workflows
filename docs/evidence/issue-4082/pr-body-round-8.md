### Keepalive: ON
<!-- meta:issue:4082 -->

### Source Issue #4082: Gate trigger fixes cannot reach consumers: pr-00-gate.yml is create_only

Closes #4082

Head: codex/issue-4082

Opened by opener-core so codex engages (invite-mode intake).

<!-- pr-preamble:start -->
<!-- meta:issue:4082 -->
> **Source:** Issue #4082

Closes #4082

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
WF#3983, merged 2026-10-17 06:44Z, removed label events from the root and consumer-template `pr-00-gate.yml`, leaving `on.pull_request.types: [opened, synchronize, reopened, ready_for_review]`. Existing consumers did not receive the change because `.github/sync-manifest.yml:42-45` sets `sync_mode: create_only` to preserve consumer coverage and runtime policy. The trigger list is shared infrastructure.

At 2026-10-18 05:58Z, Manager-Database, Doc-Lineage, Trend_Model_Project and Counter_Risk still included `labeled`. Manager-Database#1821 had six Gate runs cancelled at 01:22:41Z when six labels arrived in one second; Gate did not restart and keepalive stopped with `Gate cancelled`. That PR subsequently merged at 2026-10-18T04:05:47Z; its merge does not establish completion of this campaign.

Situation: consumer PRs receiving labels, including agent PRs where opener and keepalive add several labels together. Demand: agent PRs per week across consumers. Outcome: over the complete 48 hours following the final campaign merge, at most 5% of consumer Gate runs are cancelled pull_request runs with another run on the same head starting within 5 seconds. Check date: final campaign merge timestamp plus 48 hours. Related work: WF#3977/#3983 fixed the root trigger; WF#4068 concerns an unrelated sync-loop cause.

<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent

### Related Issues/PRs
- [stranske/Counter_Risk#1178](https://github.com/stranske/Counter_Risk/issues/1178)
- [stranske/Deliverable-Render#101](https://github.com/stranske/Deliverable-Render/issues/101)
- [stranske/Doc-Lineage#138](https://github.com/stranske/Doc-Lineage/issues/138)
- [stranske/Fine-Art-Archive#832](https://github.com/stranske/Fine-Art-Archive/issues/832)
- [stranske/Inv-Man-Intake#1037](https://github.com/stranske/Inv-Man-Intake/issues/1037)
- [stranske/Manager-Mosaic#116](https://github.com/stranske/Manager-Mosaic/issues/116)
- [stranske/Orchestrator#732](https://github.com/stranske/Orchestrator/issues/732)
- [stranske/Pension-Data#979](https://github.com/stranske/Pension-Data/issues/979)
- [stranske/Portable-Alpha-Extension-Model#2390](https://github.com/stranske/Portable-Alpha-Extension-Model/issues/2390)
- [stranske/Ready#633](https://github.com/stranske/Ready/issues/633)
- [stranske/Travel-Plan-Permission#1682](https://github.com/stranske/Travel-Plan-Permission/issues/1682)
- [stranske/Trend_Model_Project#6112](https://github.com/stranske/Trend_Model_Project/issues/6112)
- [stranske/learning-management-system#775](https://github.com/stranske/learning-management-system/issues/775)
- [stranske/trip-planner#1921](https://github.com/stranske/trip-planner/issues/1921)
- [stranske/Workflows#4084](https://github.com/stranske/Workflows/issues/4084)
- [stranske/Manager-Database#1821](https://github.com/stranske/Manager-Database/issues/1821)
- [#3983](https://github.com/stranske/Workflows/issues/3983)
<!-- Updated WORKFLOW_OUTPUTS.md context:end -->

#### Tasks
- [x] Inspect `docs/AGENT_ISSUE_FORMAT.md`, `.github/sync-manifest.yml:42-50`, and `templates/consumer-repo/.github/workflows/pr-00-gate.yml`; confirm the template and Workflows trigger lists remain corrected and preserve `overwrite_repos` and `skip_repos` behavior.
- [ ] Use `gh pr view` and `gh pr diff` to reconcile each existing campaign PR below against its current head, merge disposition and changed file; do not duplicate an existing PR. Each consumer change must remove only `labeled` from `.github/workflows/pr-00-gate.yml` in a one-line diff. Inspect Portable-Alpha-Extension-Model#2390 directly rather than treating its previously unresolved disposition as an owner dependency.
- [ ] Run `scripts/list_registered_consumer_repos.py` and inspect `~/.codex/bin/handoff.sh` `SUPPORTED_REPOS`; for any eligible consumer still containing `labeled` without an existing campaign PR, prepare the same one-line change on `orch/gate-no-labeled-trigger`. Campaign PR metadata must cite WF#3983 and WF#4082, include `autofix`, `automerge`, and `<!-- workflow-source:local_request -->`, and be recorded in WF#4082's checklist. A restricted offload must return prepared changes and evidence to its authorized parent for publication.
- [ ] Inspect Workflows#4084 with `gh pr view` and `gh pr diff`; inspect the `health-68` workflow/job or its existing drift-scan command to locate the implementation and tests. Complete only missing behavior that compares each eligible consumer's `on.pull_request.types` against the template and prints `gate triggers: <repo> extra=<list>` for drift. Report missing template triggers explicitly as well, so absence of extras cannot falsely imply equality. Print `gate triggers: all match` only after successful reads establish equality for every eligible consumer; failed or unavailable reads must remain visible.
- [ ] Run the tests associated with Workflows#4084 and the discovered Health 68 drift-scan command using the repository-selected Python interpreter, otherwise `/opt/anaconda3/bin/python3`. Before changing code, record the real-input outcome command, check date, and an attempt/time stop rule; keep the acceptance command runnable in under two minutes. Repair only the failure that command demonstrates.
- [ ] Use authenticated `gh api` reads of each eligible consumer's `.github/workflows/pr-00-gate.yml` and run the Health 68 drift-scan command after campaign merges. Record the command, timestamp, repository coverage and output; do not substitute local tests or PR merge status for live readback.
- [ ] Determine the final campaign merge timestamp using `gh pr view`. For each eligible consumer, fetch all runs in the ensuing 48-hour interval using `gh run list -R stranske/<repo> --workflow pr-00-gate.yml --created ">=<merge>" --json conclusion,headSha,createdAt,event`, handling pagination and excluding runs outside the interval. Calculate the specified cancellation numerator and Gate-run denominator across consumers; record raw counts, percentage, interval and collection date. If the interval is incomplete, record its exact completion time and defer only this observation step.

#### Acceptance criteria
- [ ] Every affected eligible consumer has a recorded campaign PR whose diff changes exactly one line in `.github/workflows/pr-00-gate.yml` and removes only `labeled`; merge status is verified from current GitHub state.
- [x] Workflows#4084's associated test command passes and covers matching triggers, extra triggers, missing template triggers and failed consumer reads; record the actual runnable command and result.
- [ ] The authenticated Health 68 drift-scan command prints `gate triggers: all match` after complete successful consumer readback following campaign merges; skipped or failed reads cannot satisfy this criterion.
- [ ] The `gh run list` collection covers the complete 48-hour interval after the final campaign merge. The number of cancelled pull_request Gate runs with a sibling on the same head starting within 5 seconds, divided by all Gate runs in that interval, is at most 5%. Record numerator and denominator; zero runs do not establish the percentage criterion.
- [ ] WF#4082 records the verified campaign dispositions, live readback evidence and observation result, or explicitly identifies the remaining observation interval without claiming completion.

<!-- auto-status-summary:end -->

Verified 2026-11-07: first task complete; both Gate trigger lists and compiled manifest exceptions are preserved. Added two scanner integration cases using the real 16-consumer roster and compiled Gate policy. Focused suite: 173 passed; final scoped follow-up: 5 passed. Connected GitHub reads confirm all 14 campaign diffs remove only labeled, with required metadata and labels; 13 merged and PAEM#2390 remains open/ready with an unresolved verify:full wakeup review. All 16 connected default-branch trigger reads match. All 46 required gh reads failed to connect; real Health 68 output remains 16 unknowns. Final campaign merge and 48-hour counts remain undetermined. Staging failed because .git is read-only; automatic approval review rejected the checkbox/label updates. See docs/evidence/issue-4082/verification-round-8.md and verification-round-8.json for the authorized-parent handoff. No live or observation acceptance is claimed.

