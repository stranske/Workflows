# Keepalive Approaches: Legacy UI vs Codex CLI

This document explains the two keepalive implementations used in this repository and the differences between them.

## Overview

There are **two distinct keepalive approaches**:

1. **Legacy UI Keepalive (Connector Bot)**
   - Uses the Codex UI connector bot (`chatgpt-codex-connector[bot]`).
   - Instructions and outputs are exchanged via PR comments.
   - Completion signals often arrive as checkboxes in connector comments.

2. **Codex CLI Keepalive (Current)**
   - Uses Codex CLI via `reusable-codex-run.yml`.
   - Task appendix is injected into the prompt (agent‑agnostic base prompt).
   - Produces structured outputs and deterministic logs.

These approaches are **not interchangeable**. The CLI workflow is the current preferred implementation and the one governed by the canonical keepalive contract.

---

## Legacy UI Keepalive (Connector Bot)

**Primary characteristics**
- **Agent interface:** Codex UI via the connector bot.
- **Trigger:** Human @agent activation in PR comments.
- **Instruction flow:** Keepalive posts instruction comments (with markers) that the connector bot reads.
- **Output flow:** The connector bot responds in PR comments.
- **Completion signals:** Task checkboxes may appear in connector comments and must be merged into the PR body.
- **Observability:** Limited structured telemetry; relies on comment history and workflow logs.
- **Branch sync:** Typically driven by comment‑based outputs and manual review; less deterministic.

**Where it appears in this repo**
- Older keepalive logic and archived gap assessments reference the connector bot and comment-based completion signals.
- The PR‑meta workflow merges connector checkbox states into the PR body to avoid infinite loops.

**Operational limitations**
- Higher variance in output format.
- Harder to automate summary extraction (comment parsing required).
- Reduced determinism for timing/perf analysis.

---

## Codex CLI Keepalive (Current)

**Primary characteristics**
- **Agent interface:** Codex CLI run via `reusable-codex-run.yml`.
- **Trigger:** PR labeled with `agent:*` and Gate success.
- **Instruction flow:** Agent‑agnostic prompt with explicit task appendix injected.
- **Output flow:** Structured CLI logs + JSONL session artifacts.
- **Completion signals:** Task updates derived from session analysis or commit/file matching.
- **Observability:** Designed for structured summaries and NDJSON metrics.
- **Branch sync:** Deterministic branch‑sync pipeline with retry/escalation rules.

**Where it appears in this repo**
- `agents-keepalive-loop.yml` and `reusable-codex-run.yml` implement the CLI flow.
- `MULTI_AGENT_ROUTING.md` documents label‑based routing.
- `METRICS_SCHEMA.md` defines the NDJSON record format for the CLI loop.

---

## Key Differences (Side‑by‑Side)

| Category | Legacy UI Keepalive | Codex CLI Keepalive (Current) |
|---|---|---|
| Agent interface | Codex UI connector bot | Codex CLI (`reusable-codex-run.yml`) |
| Trigger | Human @agent comment | `agent:*` label + Gate success |
| Instruction medium | PR comments | Workflow prompt + appendix |
| Task context | Implicit from PR body | Explicit task appendix injection |
| Output capture | PR comments only | Logs + session artifacts |
| Completion signals | Connector comment checkboxes | Session analysis + commit/file matching |
| Observability | Ad‑hoc logs | Structured summaries + NDJSON metrics |
| Determinism | Variable | Repeatable / traceable |
| Multi‑agent readiness | Limited | Built‑in routing (`agent:*`) |
| Noise | Higher PR comment volume | Lower (summary tab focus) |

---

## Benefits of the Codex CLI Implementation

1. **Deterministic execution** – predictable inputs/outputs per run.
2. **Structured telemetry** – NDJSON metrics and summary lines enable performance analysis.
3. **Task focus** – explicit task appendix reduces off‑task work.
4. **Multi‑agent routing** – `agent:*` label routing is built in.
5. **Reduced PR noise** – summary tab carries run metadata instead of repeated PR comments.
6. **Robust completion detection** – session analysis and commit matching are more reliable than comment parsing.

---

## Which One Applies?

- If you see **`reusable-codex-run.yml`** and **`agents-keepalive-loop.yml`**, you are on the **Codex CLI** path.
- If you see heavy reliance on **connector bot comments** for completion signals, you are on the **Legacy UI** path.

For any new changes, use the **Codex CLI keepalive** unless explicitly maintaining legacy behavior.

---

## Related Docs

- [Goals & Plumbing](GoalsAndPlumbing.md)
- [Observability Contract](Observability_Contract.md)
- [Multi‑Agent Routing](MULTI_AGENT_ROUTING.md)
- [Keepalive Metrics Schema](METRICS_SCHEMA.md)
- [Keepalive Integration Guide](Keepalive_Integration.md)
