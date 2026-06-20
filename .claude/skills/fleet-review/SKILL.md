---
name: fleet-review
description: >-
  Run an on-demand, multi-agent fleet/repo review across the supported stranske
  repos: fan out one Markdown-returning reviewer per repo, synthesize in the main
  loop, and emit Issue-Gate-quality candidates. Use for a manual design-vs-implementation
  review, applying a new cross-cutting concern (blueprint feasibility, dev-process,
  prior-art) across repos, or walking through how to deploy/test an app privately
  (the deployment decision-tree "shoulder tap"). Complements — does not replace —
  the scheduled scripts/repo_review_coordinator.py.
---

# Fleet Review

On-demand, human-driven multi-repo review and per-app deployment walkthrough.
This is the manual, conversational counterpart to the scheduled Python coordinator.

## When to use

Trigger this skill when the user asks for any of:

- A manual / on-demand **fleet review** or **design-vs-implementation review** of the supported repos (or a named subset).
- Applying a **new cross-cutting concern** across repos in one pass — e.g. blueprint feasibility, dev-process/adoption, prior-art research, observability.
- A **deployment / "how do I test this app privately"** decision — the per-app walkthrough (see `references/deployment-decision-tree.md`).
- Help **synthesizing** many per-repo reviews into one prioritized issue set.

## When NOT to use

- **Routine scheduled reviews.** The weekly packet is owned by `scripts/repo_review_coordinator.py` (round-1/round-2 fan-out, convergence, `human-decision-packet.md`, `approved-issue-queue.json`). Do not reimplement it here. This skill is for *ad hoc* runs, *new* concern overlays, and the *interactive* deployment walkthrough the coordinator doesn't do.
- When the answer is a single documented fact — read the doc, don't spin up agents.

Relationship: the coordinator produces the standing weekly queue from `config/repo_review_feedback.json`; this skill runs extra/interactive passes on demand and feeds candidates into that same human-decision step.

## Supported repos (the fleet)

`stranske/Workflows`, `Travel-Plan-Permission`, `Trend_Model_Project`, `Portable-Alpha-Extension-Model`, `Counter_Risk`, `Manager-Database`, `Inv-Man-Intake`, `Pension-Data`, `trip-planner`, `learning-management-system`. Authoritative roster: `config/repo_review_registry.json` (status `active`). Per-repo interpretation: `config/repo_review_profiles.json`.

## The review recipe

1. **Fan out one reviewer per repo.** Spawn one sub-agent per `active` repo, in parallel. Each reviewer reviews exactly one repo against the standard dimensions and **returns its final answer as Markdown in the final message** — NOT enforced structured output.
   - **Hard-won lesson:** forcing `StructuredOutput` / strict JSON schemas on heavy analysis agents failed on **26 of 32 agents** in the 2026-05-29 run. Markdown final-message returns are reliable. Ask for a consistent Markdown *shape* (headings below), not a validated schema.
   - Ask each reviewer for **file:line-grounded** evidence, not generic "code exists" statements.
2. **Standard dimensions** (every repo, same six — from `docs/ops/REPO_REVIEW_PROCESS.md`):
   - `design_contract` — intended product/workflow from README/docs + registry anchor.
   - `implementation_coverage` — real working behavior vs scaffolds/seams/fixtures/advisory-only.
   - `test_and_live_readiness` — do tests/smoke paths prove the user journey the design requires.
   - `integration_and_state` — cross-repo contracts, providers, persistence, reload, source authority, artifacts, workflow handoffs.
   - `liveness_evidence` — for claims that something is implemented, wired, scheduled, or automated, require a real sink/output row, artifact, smoke result, dashboard sample, or equivalent upstream-to-sink evidence before treating it as done.
   - `issue_generation` — convert verified gaps into drafts (see Issue Gate).
   - Suggested reviewer Markdown shape: one `##` per dimension, a short **Verdict**, then bulleted **Evidence (file:line)**, then **Candidate issues** each with Why / what's missing / acceptance.
3. **Main-loop synthesis.** Collect all reviewer Markdown and synthesize in the main loop (the 1M context holds every review at once). Produce: a fleet summary, readiness tiers, and a single prioritized cross-repo issue list. Do not just concatenate the reviews.
4. **Issue candidates must clear the Issue Gate / Definition of Ready.** See `references/issue-quality-bar.md`. Anything that doesn't clear it is a note, not an issue. Output candidates only — **never push to GitHub or change automation in this skill**; they flow into the same human-decision step the coordinator uses (`config/repo_review_feedback.json` → approved queue → uploader).

## Monitoring discipline (load-bearing)

The harness only notifies you on **completion**, not on death or stall. A silent background run is the #1 failure mode (an agent went silent for ~2h in the 2026-05-29 run).

- **Attach a stall-watcher to every long background run.** Poll log/output mtime; if it stops advancing, treat the run as stuck — terminate and retry on a fresh process rather than waiting on the wall timeout.
- **Process every notification immediately** when a run completes or stalls; don't batch.
- **Report proactively.** Surface progress, partial results, and any stall to the user as it happens. Never go silent — if you have nothing new, say so.
- Prefer many short, observable passes over one long opaque one.

## Concern overlays

To add a new cross-cutting concern, run it as an **extra pass** layered on the same fan-out, not a rewrite of the standard dimensions:

- Keep the per-repo, Markdown-return, file:line-grounded pattern.
- Give each reviewer the concern as one added dimension/question (e.g. **blueprint feasibility** — can this repo's core run headlessly and emit a run-contract; **dev-process/adoption** — is there a browser-reachable instance and a no-terminal way in; **prior-art** — what off-the-shelf tool would replace building this).
- Synthesize the overlay separately, then fold its issue candidates into the same Issue-Gate filter.
- Examples and verdict format mirror the 2026-05-29 review's FEASIBILITY / DEVPROCESS / RESEARCH passes.

## Grounding rules

- **Read the Workflows docs first.** Ground every system-level claim in a named doc — `README.md`, `docs/ops/REPO_REVIEW_PROCESS.md`, `docs/INTEGRATION_GUIDE.md`, `docs/keepalive/GoalsAndPlumbing.md`, `docs/LABELS.md`. If you can't name the doc, go read it before concluding.
- **Check the sync-manifest for source-of-truth.** Many files in consumer repos are synced copies; the original lives in Workflows (`.github/sync-manifest.yml` + `templates/consumer-repo/`). Don't flag "drift" or fix in a consumer what is owned here. (E.g. LangSmith/langchain scripts: Workflows is source, consumers hold copies.)
- **Never conclude from one truncated or isolated signal.** An empty queue, a stale warning, a `head`-truncated grep, or one idle lane is downstream of a pipeline — read the owning doc before drawing a system conclusion. Idle lanes never *prove* "nothing to do"; the opener also draws from already-open GitHub issues.

## Deployment decision-tree walkthrough (the "shoulder tap")

When a repo first becomes **testable**, before sharing a tool with a colleague, when **adding/enabling an LLM feature**, or when onboarding someone — run the interactive per-app walkthrough in `references/deployment-decision-tree.md` *with the user*. It encodes the two boundaries (network + LLM), the five privacy-safe deploy options, the decision tree, and per-app starting recommendations. Walk one app at a time, ask the gating questions, and record the chosen path.

## References

- `references/deployment-decision-tree.md` — the per-app deployment walkthrough (5 options, decision tree, per-app table, when to tap on the shoulder).
- `references/issue-quality-bar.md` — the Issue Gate / Definition of Ready every candidate must clear, with required/recommended sections.

## Related (in-repo)

- `docs/ops/REPO_REVIEW_PROCESS.md` — the standard process, dimensions, registry, Issue Gate, human decision point.
- `scripts/repo_review_coordinator.py` — the scheduled coordinator this skill complements.
- `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md` — the canonical issue body format.
- `.github/sync-manifest.yml` — consumer source-of-truth map.
