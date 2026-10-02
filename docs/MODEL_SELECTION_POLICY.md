# Auxiliary Model Selection Policy

> **Status:** Authoritative for `config/model_registry.json` and
> `config/llm_slots.json`
> **Policy version:** `auxiliary-verifier-model-selection-v1`
> **Reviewed:** 2026-10-01
> **Next decision review:** 2026-10-31

## Decision Principle

Provider positioning and list price are model facts, not workload-quality
evidence. A model can be selected **provisionally** from a small paired comparison
and human review. Statistical **approval** still requires the frozen,
adjudicated verifier corpus and all approval-stage gates.

Selection is constrained optimization, not a weighted score:

1. For a provisional decision, reject observed false PASS, schema errors, and
   candidates less accurate than the incumbent on the paired screen and API check.
2. Among those candidates, compare cost per accepted review from measured tokens,
   then review a reversible selection. A false PASS by the incumbent can justify
   advancing a safer candidate even if it costs more.
3. For statistical approval, pass every configured Wilson and paired quality gate;
   among passing models, minimize observed cost per accepted review and then latency.

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
Older consumer files may still contain `gpt-5.2` or `gpt-5.4` OpenAI pins
because this file is create-only in the sync manifest. Those two bundled legacy
pins are advisory; the reviewed `verifier-balanced` registry decision selects
the runtime model. Other current bundled pins and an explicitly supplied
`LANGCHAIN_SLOT_CONFIG` file remain overrides.

## Benchmark Protocol

The `verifier-balanced` policy is defined in
`config/model_selection_policy.json`.

### Fast provisional decision

MAINT-78's automatic run is a no-spend plan. The existing 51 historical cases
meet the candidate-stage count and category minima, but **they are not yet
valid screen inputs**. Their labels reflect later issue disposition, while the
pilot supplied raw PR text rather than the production verifier's context and
diff summary. The October 2 CLI diagnostic exposed this mismatch: GPT-6 Luna
matched Terra's total score by rejecting every PASS example. That result does
not justify a model change or a paid confirmation. The plan now reports an
input-alignment blocker before any model calls.

The next small screen requires independently adjudicated PASS and NON_PASS
cases tied to captured production verifier inputs at merge. The comparison
artifact now includes the exact context, diff summary, and identity manifest.
Capture them before any model verdict or later disposition comment can enter
them; record their hashes and merge heads, and review each expected outcome
against the acceptance criteria at that point. A controlled defect variant of
a captured input may supply a NON_PASS case when natural failures are scarce;
mark it `controlled_defect`, describe the mutation, and keep the original
capture provenance. The screen report must identify such cases as synthetic
evidence, and the final change needs monitoring on real verifier work. Use a
balanced eight-case paired set once available; there is no need to wait for
the statistical approval sample.
The manual `screen` compares the incumbent and up to three priced models
through Codex subscription auth with no API-key calls. A finalist must have
zero observed false PASS and schema errors, at least 50% PASS recall, no
regression in either verdict class relative to the incumbent, and lower
modeled cost per accepted review (or replace an incumbent with an observed
false PASS). These are small-sample safeguards, not confidence claims.

A separate manual `confirm` dispatch supplies that screen's run ID. The workflow
refuses a stale or incomplete screen by checking input and verifier-harness
fingerprints, plus the hash of each freshly fetched verifier prompt **before**
any API call. It also rejects unaligned inputs. It applies the configured provisional-stage thresholds at both
stages. It compares only the incumbent and finalist
on the same eight cases through the OpenAI API, disables SDK retries, and reserves
at most $5 in worst-case standard-rate cost before each pair. The estimate uses
measured API token counts but is not the provider invoice. If the paired result
meets the same observed-case safeguards, it produces a provisional proposal for
human review; it does not change `model_registry.json` itself. The owner may
approve a reversible provisional registry PR and monitor live verifier outcomes,
reverting on a false PASS or material quality regression. The small comparison
does not establish a population false-PASS rate. An API-only model absent from
the pinned CLI catalog (currently GPT-6.1 Sol) may be named explicitly in a
manual `confirm` dispatch. It reuses the completed screen's eight paired cases,
checks that the model is priced and actually absent from the catalog, and obeys
the same $5/16-call cap. Its report labels the CLI-stage exception.

This gives a usable decision during a model update cycle. The larger sample
requirements below remain the bar for a statistical `approved` status, not a
blocker to provisional selection.

### Statistical approval

Evaluate a case-level paired run with:

```bash
python tools/evaluate_model_benchmark.py benchmark.json --output benchmark-evidence.json
```

The evaluator computes the confidence bounds and recommendation from case-level
records. Do not hand-enter aggregate rates or recommendation rankings.

- Use a frozen, versioned corpus with owner-adjudicated expected outcomes.
- Run every candidate and baseline on the same cases and prompt version.
- Use at least 30 cases to retain a candidate and at least 75 cases, with 10 per
  required failure category, to approve it. Categories that cannot be labelled
  from realized downstream outcomes — `stale-verifier-claim`,
  `review-thread-debt`, `missing-acceptance-criterion` — are exempted from the
  10-case floor via `approval_stage.minimum_cases_per_category_overrides` and
  need only be *represented* (≥1 adjudicated case). `tools/harvest_verifier_corpus.py`
  can never produce them, so holding them to the machine-harvestable floor made
  approval unreachable without hand-labelling roughly 22 cases. The 75-case total
  and every statistical gate still apply to the whole corpus; raise these floors
  toward 10 as owner-labelled cases accumulate. See issue #2819.
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

### Advisory vs. blocking findings

`tools/check_model_registry_freshness.py` separates its findings into two
classes, and by default only one of them fails the gate:

- **Blocking (structural):** a malformed registry, a selection or slot that
  points at an absent or blocked model, or an *approved* selection with no
  passing workload-benchmark evidence. These mean work could be wrong, so they
  fail the gate (exit 1).
- **Advisory (cadence):** a review whose `review_by` date has simply passed
  (`review_overdue`, `provisional_overdue`, `selection_review_overdue`). A due
  review is not a danger signal — the provisional incumbents remain a valid
  runtime baseline — so it never fails the default gate and never blocks
  unrelated work. It is surfaced instead by the `maint-77` scheduled run, which
  opens a non-blocking tracking issue.

Pass `--strict` to fail on *any* finding (used where a PR itself edits model
configuration and should be proven fresh before merging).

## Incumbents and Candidates

The existing OpenAI, Anthropic, and GitHub Models verifier choices are recorded
as provisional incumbents. They remain the runtime baseline while the pilot is
assembled and run; catalog discovery can add candidates but cannot change a
selection. A replacement requires paired workload evidence that passes every
quality gate and an explicit approval update.

### Prepared promotions and rollbacks

`tools/prepare_model_promotion.py` (run by `maint-86`) can *prepare* a selection
change from a passing benchmark, but never applies one on its own. Candidates
must pass every benchmark quality gate and have known, finite, nonnegative costs.
Same-family candidates (e.g. openai `gpt-5.x`, anthropic `claude-<line>`) costing
**≤** the incumbent receive `preparation_mode=bounded`. Cross-family or pricier
candidates receive `preparation_mode=approval-required` and explicit
`approval_reasons`. The tool selects at most one candidate per provider, preferring
bounded changes, then lower cost and latency. Both modes retain
`human_approval_required=true`; preparation metadata does not authorize auto-merge.
The tool writes the registry mutation (recording the prior selection in
`selection_history`) for the workflow to open as a PR; merging that PR is the
human approval this policy requires — `human_approval_required`
stays true. The inverse path prepares a rollback to the prior selection when the
active model shows a failed workload-benchmark (a quality-gate breach).

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

### Replayable corpus evidence

`maint-79` harvests only PR outcomes joined to a bot-published
`verifier-corpus-decision/v1` record. The comparison verifier records the PR head,
evaluated merge SHA, repository/PR, run ID and attempt beside the durable report.
A candidate retains that decision and its comment URL. A stable merge without a
matching decision is excluded; a NON_PASS decision cannot become a clean PASS
just because the PR merged. Provider errors and unavailable reviews are not
benchmark verdicts. A failed merge CI check floors the structured verdict to
NON_PASS even when every provider says PASS. Missing or invalid CI-gate context
suppresses publication rather than creating unverifiable benchmark evidence.
Historical reports without these fields are not backfilled
from merge metadata. They can enter future harvests after fresh verification.

Case identity includes repository, PR, head and verifier run/attempt. Replaying
the same evidence does not duplicate a case. Existing adjudicated corpus entries
keep their historical identifiers. The staging file is FYI-only; a staging-only
PR does not grow approval metrics. Only additions to `model_eval_pilot.json` count
as promotions, and existing category/size caps and model approval policy remain.
