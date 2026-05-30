# Issue Gate / Definition of Ready

Every candidate issue produced by a fleet review must clear this bar before it is
offered for human approval. Anything that doesn't clear it is a note, not an issue.
Source: `docs/ops/REPO_REVIEW_PROCESS.md` (Issue Gate) and
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md` (issue body format).

## The gate — a candidate must state

- **The design commitment or readiness goal** it serves.
- **Current evidence** from code, docs, tests, or archives (file:line, not "code exists").
- **What behavior is missing.**
- **Non-goals** that prevent a scaffold-only "done" claim.
- **Tasks** a coding agent can actually complete.
- **Acceptance criteria** with a failing test, a smoke test, or a documented live-verification gate.

If any of the six is absent, the candidate is not ready.

## Required body sections (enforced)

- `## Tasks` — checkboxes; each task specific, small, actionable (starts with a verb).
- `## Acceptance Criteria` — checkboxes; each verifiable, specific, independent.

## Recommended body sections (the weekly queue includes these)

- `## Why` — context/rationale.
- `## Scope` — what the issue covers and its boundaries.
- `## Non-Goals` — explicit exclusions (blocks scope creep and scaffold-only claims).
- `## Implementation Notes` — file paths, constraints, technical guidance.

## Quality checks

- **Tasks** are specific / small / actionable. Reject "Fix bugs", "Improve code".
- **Acceptance criteria** are verifiable / specific / independent. If you can't write a test for it, rephrase it. Reject "Works correctly".
- **File paths** named explicitly in Implementation Notes.

## Scope rule for consumer repos

Consumer-repo reviews must **not** generate issues for Workflows maintenance,
template sync, or cross-repo lane-management work unless that work directly
implements repo-local behavior the consumer's design requires. Those maintenance
tasks belong in `stranske/Workflows`.

## After candidates exist (not this skill's job to execute)

Candidates flow into the same human step the coordinator uses:
human approval recorded in `config/repo_review_feedback.json` → evaluator
regenerates `approved-issue-queue.json` → upload via
`scripts/upload_repo_review_issues.py` (dry-run by default; `--apply` to create,
which skips exact-title-duplicate open issues). This skill **outputs candidates
only** — it never pushes issues or changes automation.
