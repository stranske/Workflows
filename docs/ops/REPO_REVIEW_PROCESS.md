# Repo Review Process

This process exists to standardize periodic design-vs-implementation reviews across active repos. Issue generation is an output of the review, not the review itself.

The weekly packet must answer one core question for each active repo:

> What does the repo intend to be, how much of that design is actually implemented, and what gaps block testing or live use?

## Review Order

1. Read the registry decision anchor and the repo design sources.
2. Inspect the implementation areas named by the packet.
3. Compare design commitments to real behavior, tests, integrations, persistence, and workflow handoffs.
4. For features, reports, dashboards, or pipelines described as implemented, wired, scheduled, or automated, query the actual sink/output and require a real recent row, artifact, smoke result, dashboard sample, or equivalent upstream-to-sink evidence.
5. Use archived review conversations as precedent for the review standard and known project intent.
6. Identify gaps that block testing, live implementation, or product completeness.
7. Draft issues only for verified gaps, with evidence and acceptance gates.
8. Queue one human decision packet before creating remote issues.
9. After human approval, upload approved drafts to the target repos with duplicate checks.

## Registry

The repo roster lives in `config/repo_review_registry.json`.

Statuses:

- `active`: included in the scheduled design-vs-implementation review.
- `paused`: tracked, but not normally reviewed until reactivated.
- `ignored`: deliberately out of the current review lane.
- `needs-human`: blocked until a human resolves the recorded ambiguity.

The registry excludes repos named `stranske` and `collab-deliverables`.

Repo-specific review interpretation lives in `config/repo_review_profiles.json`. The evaluator uses these profiles for human-usable progress summaries, readiness summaries, review focus, and known concerns. Generic code-existence statements are not acceptable as the final human packet summary when a profile exists.

Human feedback from the weekly packet lives in `config/repo_review_feedback.json`. This file records per-repo decisions, priority, selected candidate indexes, dropped candidate indexes, and routing rules. It is the source for the approved issue queue consumed by coding-agent opener lanes.

## Standard Dimensions

Every active repo review uses the same dimensions:

- `design_contract`: identify the intended product or workflow from README/docs and the registry decision anchor.
- `implementation_coverage`: distinguish real working behavior from scaffolds, seams, fixtures, or advisory-only outputs.
- `test_and_live_readiness`: determine whether tests or smoke paths prove the user journey required by the design.
- `integration_and_state`: check cross-repo contracts, external providers, persistence, reload behavior, source authority, generated artifacts, and workflow handoffs.
- `liveness_evidence`: for any feature or pipeline claimed as implemented, wired, scheduled, or automated, require real sink/output evidence before accepting the claim as done.
- `issue_generation`: convert verified gaps into issue drafts with evidence, non-goals, tasks, acceptance criteria, and tests that would fail before the fix.
- `dynamic_run_evidence`: real run-outcome evidence the static review cannot see — reverted/abandoned agent PRs and recurring failure patterns from the week's runs. This dimension is **automated and locally sourced**: the evaluator shells to the Orchestrator feedback Brain (`keepalive_evidence.py`) and the dimension is present only when that local store is reachable. It degrades silently (the dimension is omitted, never an error) wherever the Brain is absent, e.g. CI. A reverted PR raises a `material` gap; an abandoned PR or recurring failure raises `needs human decision`; a candidate whose linked issue is still open is flagged as already-tracked rather than net-new.

## Weekly Run

Run from the Workflows repo:

```bash
python scripts/repo_review_coordinator.py \
    --output-dir docs/reports/repo-review \
    --registry config/repo_review_registry.json
```

The coordinator is the Phase-4 entry point. It runs the evaluator preflight,
then for each `active` repo drives the skip-this-cycle gate, round-1 fan-out
(Codex + Claude in parallel), round-2 negotiation, and per-repo state update,
before a final evaluator pass renders `human-decision-packet.md`. Pass
`--repos <repo> [<repo> ...]` to run the full Phase-4 flow against only the
named subset of `active` repos:

```bash
python scripts/repo_review_coordinator.py \
    --output-dir docs/reports/repo-review \
    --registry config/repo_review_registry.json \
    --repos stranske/Manager-Database stranske/trip-planner
```

`python scripts/repo_review_evaluator.py` remains valid as a standalone
preflight step: it produces the per-repo `review-inputs.md` artifacts without
running the multi-agent round-1/round-2 negotiation. Use it when you only need
fresh evaluator inputs (for example, regenerating evidence before a human
review pass); use the coordinator when you need the complete weekly packet
with converged candidates and human-decision sections.

The default weekly run performs a GitNexus preflight for active repos before
the packet is generated. It checks map freshness and refreshes stale or missing
active maps with `gitnexus analyze <repo> --skip-agents-md` when the CLI is
available. Use `--no-refresh-stale-gitnexus` to report stale maps without
refreshing, or `--skip-gitnexus-preflight` only when GitNexus is deliberately
out of scope for that run.

### Docs-drift fix-agent

The weekly semantic docs-drift scanner and monthly `maint-48-docs-drift-audit`
issue find stale operational claims, but they do not repair the docs directly.
Use the deterministic fix-agent to turn drift findings into bounded PR-ready
repair briefs:

```bash
python scripts/docs_drift_fix_agent.py \
    --repo-root . \
    --scan-json docs/reports/repo-review/docs-drift-scan.json \
    --out-dir docs/reports/docs-drift-fix-agent
```

The command is read-only by default. It writes `plan.json`, one repair prompt,
one issue body, and one PR plan per bounded batch. Give the repair prompt to an
agent lane to open a docs-only fix PR, or pass `--apply` only when you want the
tool to create one GitHub issue per batch. The fix-agent composes existing scan
outputs; it does not launch a new Claude review and it does not edit files.

### Phase-4 Components

The coordinator orchestrates five Phase-4 scripts under `scripts/`:

- `repo_review_coordinator.py` — sequential per-repo orchestrator that drives
  evaluator preflight → skip-this-cycle gate → round-1 → round-2 → body-writer
  → final evaluator pass.
- `repo_review_round1_runner.py` — round-1 fan-out runner that refreshes the
  GitNexus map and spawns Codex + Claude in parallel for the initial
  design-vs-implementation pass.
- `repo_review_round2_runner.py` — round-2 negotiation runner that coordinates
  per-turn agent calls, validates schema, and synthesizes `converged.json`.
  Protocol details: [`REPO_REVIEW_ROUND2_PROTOCOL.md`](REPO_REVIEW_ROUND2_PROTOCOL.md).
- `repo_review_heartbeat.py` — heartbeat-aware subprocess runner that polls
  agent log mtime and terminates stuck agents before the wall timeout so the
  retry budget can fire on a fresh process.
- `repo_review_body_writer.py` — body-writer pass that converts round-2
  converged candidates into `AGENT_ISSUE_FORMAT.md`-compliant issue bodies
  with concrete file:line refs, tasks, and acceptance criteria.

Round-1 schema and round-2 protocol references:
[`REPO_REVIEW_ROUND1_SCHEMA.md`](REPO_REVIEW_ROUND1_SCHEMA.md) and
[`REPO_REVIEW_ROUND2_PROTOCOL.md`](REPO_REVIEW_ROUND2_PROTOCOL.md).

Outputs are written to `docs/reports/repo-review/`:

- `human-decision-packet.md`: one review queue across active repos.
- `repo-review-summary.json`: machine-readable summary.
- `approved-issue-queue.json`: machine-readable queue of approved, prioritized, agent-formatted issue bodies. Written by exactly one producer — the final evaluator pass (`repo_review_evaluator.write_approved_issue_queue`), which applies the priority-tiering and cycle-binding guards (#2272). The coordinator's step-3 queue-builder is a log-only preview and does **not** write this file. Scorecard findings enter this queue only after explicit human approval in `config/repo_review_feedback.json`.
- `approved-issue-queue.md`: human-readable rendering of the approved issue queue, deeper-review items, and dropped candidates.
- `scorecard-scan.json`: machine-readable OpenSSF Scorecard scan output for configured repos. Low-scoring checks are surfaced in the notify desktop reminder; they do not become queue issues until a human sets `decisions.<repo>.scorecard.decision = "approve"` and lists explicit `approved_findings` IDs, then reruns the evaluator.
- `repos/<owner>__<repo>/decision-brief.md`: human-facing progress, readiness, issue-set, and feedback brief.
- `repos/<owner>__<repo>/review-execution.md`: automated evidence gathering and preliminary gap classification.
- `repos/<owner>__<repo>/design-review.md`: standardized review worksheet for that repo.
- `repos/<owner>__<repo>/state.md`: repo state, sources, implementation areas, and local signals.
- `repos/<owner>__<repo>/issue-drafts.md`: existing draft inputs and archive-derived candidate inputs.

The `docs/reports/repo-review/` directory is ephemeral output and is ignored by git.

## Local Signals

Local changes are split by how they affect the review:

- `Issues.txt` is a helper/queue file. Changes there are review inputs, not blockers.
- Generated output such as `docs/reports/` is ephemeral and does not block review.
- Other non-generated local changes are surfaced as review-blocking until they are understood, because they may change the implementation being evaluated.
- `workloop-state.md` is local opener/closer lane scratch, not a review input or deliverable; it should not be tracked. See [`LOCAL_LANES.md`](LOCAL_LANES.md) for the lane state/retention/steward contract that the opener (which consumes this review's approved queue) operates under.

Local `.gitnexus/` maps are review inputs, not blockers. The evaluator reads only `.gitnexus/meta.json` to report map freshness, indexed commit, and index size. It does not parse the binary local map. For deeper semantic review, especially repos marked `deeper-review`, use the GitNexus MCP query/context tools against the repo design target, review focus, and implementation paths surfaced in the packet. If a natural-language GitNexus query returns no processes, fall back to Cypher community/process listings before concluding the map has no useful signal.

Refresh GitNexus maps:

- before each weekly review for active repos, which the evaluator now does by default for stale or missing maps;
- after significant local or remote implementation updates land on a repo's default branch;
- before any deeper semantic review where issue generation depends on current call-flow evidence;
- after pushing Workflows changes that alter review automation, templates, or agent handoff behavior.

Use the fleet helper when working from Workflows:

```bash
docs/ops/bin/gitnexus_fleet.sh index <local-repo-name>
```

If natural-language GitNexus query returns no processes and the repo map has `embeddings: 0`, treat that as a search-mode limitation, not as evidence that no relevant code exists. Use Cypher to list communities and processes, then inspect exact symbols with `context()`.

`pending standardized review` means the worksheet has been queued and evidence still needs to be gathered. It does not mean the design-vs-implementation review has already been completed.

`standard review executed; human decision queued` means the automated evidence pass has run and the repo is ready for the single human decision point.

`decision-brief.md` is the human review surface. It summarizes current progress against the design anchor, readiness for testing/live implementation, candidate issue set, and a compact feedback slot for approve/revise/defer/drop/deeper-review decisions.

`review-execution.md` is the automated execution phase. It gathers evidence for each standard dimension and classifies obvious automated gaps such as missing design sources, missing implementation surfaces, missing tests/workflows, or absent smoke/live-readiness markers. When the local Orchestrator feedback Brain is reachable it also adds the `dynamic_run_evidence` dimension — reverted/abandoned PRs and recurring failures observed in the week's runs — which the static design-vs-implementation pass structurally cannot detect. Dimensions marked `needs human decision` still require semantic review before issue approval.

The liveness dimension exists to catch dry seams: a feature can have code, docs, tests, and a schedule while its durable sink still has zero real rows or no recent output. Do not mark such work complete until the review can trace a real upstream event into the claimed sink/output.

## Archive Use

Archived conversations are not just a source of issue text. They are review precedent:

- what design goal was previously stated;
- what implementation shortcuts were rejected;
- what testing/live-readiness gates were expected;
- what follow-up issues were considered valuable.

Archive-derived candidates still require the standardized review before approval. They should not be copied into remote issues without checking current code and docs.

## Human Decision Point

The human reviews `human-decision-packet.md` and each relevant `design-review.md`, then chooses per repo:

- approve selected issue drafts after the review;
- edit drafts before issue creation;
- request another implementation inspection;
- pause the repo;
- mark the repo `needs-human` with a blocking question;
- ignore the repo for now.

Only approved drafts should flow into the remote issue-intake workflow. After feedback is recorded
and the evaluator has regenerated `approved-issue-queue.json`, upload the approved issue set with:

```bash
python scripts/upload_repo_review_issues.py \
  --queue docs/reports/repo-review/approved-issue-queue.json \
  --apply
```

Without `--apply`, the uploader performs a dry run. With `--apply`, it creates missing labels,
skips open issues with exact matching titles, adds missing review labels to skipped duplicates,
and creates the remaining approved issues in the individual repos. Deeper-review repos are not
uploaded until the deeper review produces a new candidate set and the human approves it.

Approved drafts flow through `approved-issue-queue.json`. Opener-lane automations should select from that queue by priority, using `high` before `normal` before `low`, while respecting the repo recorded on each item. Closer-lane automations should continue to sweep PRs, review comments, merge readiness, and verifier status across all active repos rather than focusing on a fixed two-repo list.

### Scorecard approval flow

OpenSSF Scorecard findings are a supplemental candidate source, not an automatic issue creator:

1. The coordinator runs `scripts/repo_review_scorecard.py` and writes `scorecard-scan.json`.
2. `scripts/repo_review_notify.py` surfaces low-scoring checks in `~/Desktop/REPO-REVIEW-ACTION-NEEDED.md`, grouped by repo, with ready-to-paste approval snippets for `config/repo_review_feedback.json`.
3. The human edits `config/repo_review_feedback.json` and sets `decisions.<repo>.scorecard.decision = "approve"` plus explicit `approved_findings` IDs (for example `["scorecard:Branch-Protection"]`). Blanket `approved_candidates: "all"` and `"approved_findings": "all"` do **not** approve Scorecard findings.
4. The human reruns `scripts/repo_review_evaluator.py` to regenerate `approved-issue-queue.json`.
5. Only then may `upload_repo_review_issues.py --apply` publish the approved Scorecard queue items.

The final evaluator pass remains the sole producer of `approved-issue-queue.json`.

## Issue Gate

No issue should be approved unless it states:

- the design commitment or readiness goal;
- the current evidence from code, docs, tests, or archives;
- what behavior is missing;
- for completion or automation claims, the real sink/output evidence that proves the data or user-visible result actually flowed;
- non-goals that prevent scaffold-only completion claims;
- tasks a coding agent can complete;
- acceptance criteria with a failing test, smoke test, or documented live-verification gate.

Approved issue bodies must follow the required agent issue sections from `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`:

- `## Tasks`
- `## Acceptance Criteria`

The weekly queue also includes the recommended sections:

- `## Why`
- `## Scope`
- `## Non-Goals`
- `## Implementation Notes`

Consumer repo reviews must not generate issues for Workflows maintenance, template sync, or cross-repo lane-management work unless that work directly implements repo-local behavior required by the consumer repo design. Those maintenance tasks belong in `stranske/Workflows`.

Completion audits should still use the issue-completion audit workflow before declaring issue work fully done: review feedback, merge state, verifier outcomes, and non-PASS follow-up disposition all matter.
