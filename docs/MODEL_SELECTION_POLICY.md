# Auxiliary Model Selection Policy

> **Status:** Authoritative for `config/model_registry.json` and
> `config/llm_slots.json`
> **Policy version:** `auxiliary-verifier-model-selection-v1`
> **Reviewed:** 2026-07-10
> **Next decision review:** 2026-07-24

## Decision Principle

Provider positioning and list price are model facts, not workload-quality
evidence. A model is eligible for approval only after it runs the same frozen,
adjudicated verifier corpus as the current baseline.

Selection is constrained optimization, not a weighted score:

1. Pass every quality and safety gate.
2. Among passing models, minimize observed cost per accepted review.
3. Use observed p95 latency as the final tie-breaker.

This avoids arbitrary normalized quality, cost, and speed numbers. It also
prevents an inexpensive model from offsetting an unacceptable false-PASS rate.

## Data Boundaries

`config/model_registry.json` keeps three kinds of data separate:

- **Facts:** provider ID, lifecycle, observed catalog date, source URL, and list
  pricing as of a date.
- **Evidence:** a catalog review or a versioned repository workload benchmark.
- **Decision:** one provider/profile model, status, rationale, evidence IDs,
  decision date, and review deadline.

`config/llm_slots.json` keeps consumer-specific provider preferences but carries
only a workload profile. Model versions resolve from the registry decision.

## Benchmark Protocol

The `verifier-balanced` policy is defined in
`config/model_selection_policy.json`.

Evaluate a case-level paired run with:

```bash
python tools/evaluate_model_benchmark.py benchmark.json --output benchmark-evidence.json
```

The evaluator computes the confidence bounds and recommendation from case-level
records. Do not hand-enter aggregate rates or recommendation rankings.

- Use a frozen, versioned corpus with owner-adjudicated expected outcomes.
- Run every candidate and baseline on the same cases and prompt version.
- Use at least 30 cases to retain a candidate and at least 75 cases, with 10 per
  required failure category, to approve it.
- Report Wilson 95% confidence intervals for task success, false PASS, false
  FAIL, and schema errors.
- Require the configured bounds and a paired success result no more than two
  percentage points below the baseline.
- Record input/output tokens, actual billed cost, and latency per case. Compare
  cost per accepted review, not provider list price alone.
- Treat prompt, schema, reasoning-effort, and retry-policy changes as new
  benchmark versions. Do not combine unlike runs.

An approved evidence record uses `kind: workload-benchmark` and
`status: passed`. The freshness gate rejects an approved decision without it.

## Incumbents and Candidates

The existing OpenAI, Anthropic, and GitHub Models verifier choices are recorded
as provisional incumbents. They remain the runtime baseline while the pilot is
assembled and run; catalog discovery can add candidates but cannot change a
selection. A replacement requires paired workload evidence that passes every
quality gate and an explicit approval update.

## Catalog Discovery

Run:

```bash
python tools/discover_model_catalog.py --output model-catalog-discovery.json
```

GitHub Models discovery is public. OpenAI and Anthropic discovery is enabled
when their API keys are available. The weekly maint-77 workflow attaches the
diff to its tracking issue.

A newly observed model becomes a candidate. It never changes a selection until
the benchmark and human-approval rules are satisfied. This is the mechanism
that keeps the system current without converting a provider release into an
unreviewed production change.

## Review Triggers

Review at least every 30 days and immediately after any of:

- provider catalog or durable pricing change;
- material prompt, output schema, workload, or retry-policy change;
- observed quality-gate breach;
- selected model lifecycle or availability change.

Update the facts and catalog baseline first, run the paired benchmark, attach
evidence, then update the explicit selection. Maint-68 propagates the registry;
consumer slot provider preferences remain intact.
