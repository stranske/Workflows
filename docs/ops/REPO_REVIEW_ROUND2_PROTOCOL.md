# Round 2 Negotiation Protocol

After both round-1 reviewer agents have produced `findings.json` files at `<output_dir>/round1/<agent>/<repo>/findings.json`, round 2 negotiates between them to produce a single converged candidate set for the human packet.

The protocol is explicit about three things:

1. **Per-candidate marks** — agents agree, merge, drop, revise, or abstain on each round-1 candidate from both sides.
2. **Meta-candidate detection** — when round-1 candidates from both agents share a systemic pattern, the negotiation surfaces ONE additional meta-candidate that scopes a *cross-codebase audit*, NOT a bundled fix. This is a designed feature of round 2, not an emergent possibility.
3. **Convergence rules + deadlock surface** — convergence is bounded by N turns (default 3); whatever doesn't converge is surfaced to the human packet with both agents' positions intact, never silently dropped.

## Inputs

For each repo, both round-1 findings files exist on disk and have validated:

```
<output_dir>/round1/codex/<repo_safe>/findings.json
<output_dir>/round1/claude/<repo_safe>/findings.json
```

The negotiation reads BOTH files, presents them to each agent, and asks each agent for marks + meta-candidate-detection. Each agent's session is independent — they negotiate via the shared turn-output files, not by talking directly to each other.

## Per-turn output

Each agent writes one file per turn to:

```
<output_dir>/round2/<repo_safe>/turn-<N>/<agent>.json
```

The schema is defined in `REPO_REVIEW_ROUND2_SCHEMA.md` and validated by `scripts/repo_review_round2_schema.py`.

### Reuse binding

A completed turn is reusable only with the runner-written input receipt at
`<output_dir>/round2/<repo_safe>/input-manifests/turn-<N>-<agent>.json`. The
receipt binds the exact bytes of both round-1 findings and their provenance,
the canonical prompt/protocol/schema, every prior-turn output supplied to the
agent, and the turn-output bytes themselves. Missing, malformed, or mismatched
receipts make a cached output stale: a normal run preserves it under
`<output_dir>/repairs/round2-stale/` and regenerates it. A `--dry-run` fails
closed instead; it may only synthesize from matching runner-written receipts.

## Per-candidate marks

For each round-1 candidate (whether your own or the other agent's), each agent records exactly one mark:

| Mark | Meaning |
|---|---|
| `agree-keep` | The candidate matches a real gap; keep with the other agent's framing as-is |
| `agree-merge` | The candidate overlaps with one of mine; propose a merged candidate with combined framing |
| `disagree-drop` | The candidate does not describe a real gap; argue why with evidence |
| `disagree-revise` | The candidate describes a real gap but framing/scope is wrong; propose a revised version |
| `abstain` | I lack independent evidence to take a position; ask for clarification |

Every `disagree-*` mark must cite evidence (file refs, test refs, or specific reasoning). Marks without reasons are rejected by the schema validator.

## Convergence rules

After each turn, the runner computes convergence per candidate:

- **Converged-keep**: both agents marked `agree-keep` (or both `agree-merge` with compatible merge proposals)
- **Converged-drop**: both agents marked `disagree-drop` with mutually-consistent reasons
- **Converged-merge**: both agents agreed on a merge; the merged candidate replaces the originals
- **Pending**: at least one agent marked `disagree-revise` or `abstain`, OR the agents disagree
- **Deadlocked**: still pending after `N` turns (default 3)

Deadlocked candidates surface to the human packet under "Deadlocked candidates" with both agents' final positions inline. They do NOT silently drop and they do NOT block the rest of the packet.

## Meta-candidate detection (designed feature)

After per-candidate marking each turn, every agent is **prompted** to look for systemic patterns across the union of all candidates from both round-1 agents. A pattern exists when ≥2 candidates point to:

- the same class of bug (e.g., "multiple SQL queries reference legacy table names")
- the same architectural seam left half-migrated (e.g., "multiple call sites still trust a deprecated auth header")
- the same kind of incomplete scaffolding (e.g., "multiple modules import from a path documented as deprecated")

If an agent sees a pattern, it proposes ONE meta-candidate:

```json
{
  "proposed": true,
  "pattern": "<concise description of the systemic pattern>",
  "title": "Audit and remediate <pattern> across the codebase",
  "rationale": "<why ≥2 instances justify a systemic audit>",
  "supporting_candidate_indexes": [
    {"agent": "codex", "candidate_index": 1},
    {"agent": "claude", "candidate_index": 1}
  ],
  "scope": "audit",
  "tasks": [
    "Enumerate every call site / file matching the pattern with rg/ast/gitnexus.",
    "Classify each instance: confirmed-bug | needs-investigation | already-correct.",
    "Prioritize remediations and file ONE follow-up issue per remaining instance.",
    "Produce an audit report artifact (path declared in acceptance) that lists all instances + their disposition."
  ],
  "acceptance_criteria": [
    "Audit report artifact exists at <named-path> listing every matching call site with its disposition.",
    "One follow-up issue is filed for each instance not addressed by the converged per-instance candidates.",
    "Pattern detector / linter is added (or test asserting absence) so new instances can't regress in.",
    "PR description names the audit-report path and the follow-up issues filed."
  ],
  "non_goals": [
    "Do NOT bundle all per-instance fixes into a single PR — each per-instance candidate ships separately.",
    "Do NOT widen scope to refactor adjacent code that doesn't match the pattern."
  ],
  "priority": "normal",
  "confidence": "medium"
}
```

### Meta-candidate convergence rules

A meta-candidate is added to the converged set ONLY if:

1. Both agents proposed a compatible pattern (same theme, overlapping `supporting_candidate_indexes`), OR
2. One agent proposed and the other agreed (`agree-keep` mark on the meta) in a subsequent turn

If only one agent proposes and the other rejects the pattern as not-systemic, the meta-candidate becomes a deadlocked item in the human packet.

### Why this is risk-controlled

The meta-candidate is bounded by three explicit guardrails baked into the schema:

- **`scope: "audit"`** is an enumerated value distinct from regular candidates' implicit "fix" scope. The evaluator's issue-body builder treats `audit` candidates differently — the body says "produce a report + plan + follow-up issues", not "fix everything".
- **Acceptance criteria must reference an audit-report artifact path** + a follow-up-issue-filing requirement. The validator rejects meta-candidates whose acceptance criteria look like fix criteria.
- **Non-goals must explicitly state "do NOT bundle fixes into one PR"**. The validator enforces this string.
- **Confidence defaults to `medium` and priority to `normal` or `low`.** A meta-candidate at `high` confidence requires the supporting per-instance candidates to be ≥4 (configurable threshold). This stops one agent from upgrading the meta past what the per-instance evidence supports.

The per-instance candidates always ship alongside the meta — the meta does not replace them.

## Bounded turns + budget

Default: N=3 turns max. Per-turn agent budget is smaller than round-1 (the inputs are bounded — both agents' findings + accumulated turn outputs — and the agent isn't doing fresh repo inspection). Estimate 5–15 minutes per agent per turn.

The runner stops early if the candidate set is fully converged after fewer turns. Most repos with non-conflicting findings converge in turn 1.

## Outputs

After all turns complete, the runner writes:

```
<output_dir>/round2/<repo_safe>/converged.json
```

This file is the source the evaluator's `load_round1_findings`-equivalent reads — it supersedes the individual round-1 findings.json files for packet rendering. The evaluator function `load_round2_converged(output_dir, repo)` returns the converged set if present, else falls back to the most-recent round-1 findings (single-agent mode for repos that haven't completed round 2 yet).

## Stall recovery

Each turn output is written to disk before the runner waits for the next turn. If an agent times out mid-turn, the runner restarts that agent's turn (up to 2 retries). If an agent fails persistently, that turn surfaces all that-agent's marks as `abstain` and the negotiation continues with the other agent's marks treated as the authoritative position; the resulting candidates surface as deadlocked or single-side-only, never as silently-converged.

## Versioning

This is round-2 protocol `v1`. Future evolutions will add `protocol_version` to the converged.json. The current schema includes it implicitly via the schema doc's version label.
