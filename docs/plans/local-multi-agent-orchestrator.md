# Local Cost/Capacity-Aware Multi-Agent Coding Orchestrator — Design (Revised)

*A LOCAL orchestrator that dispatches bounded coding tasks to a pool of coding agents (Codex, Claude, Cursor, Gemini/`agy`, Aider+Codestral), keeping a premium model in the cheap low-token orchestration seat and pushing high-token coding to cheaper agents. Routes by task difficulty × each agent's remaining capacity; tunes from LangSmith + code/bug-review-bot signals; adapts to token-price changes; optimizes cost-per-VERIFIED-success.*

**Revision note (this version):** rewritten after five adversarial red-team passes (over-engineering, economics, operations, prior-art, safety/quality). The headline changes: (1) the safety thesis is corrected — the LLM verifier is a **post-merge auditor, not a merge gate**, so the only pre-merge gate today is Gate CI; the design no longer claims otherwise and adds the deterministic checks that close the gap; (2) the capacity ledger is collapsed to **one correctness model per agent** and re-keyed on **account, not lane-agent**; (3) the relay/mutex reuse claims are corrected — the mutex is **per-lane not per-agent** and the relay is a **hard-coded 2-agent swap**, both of which must change; (4) the "~4 new components" tally is corrected to ~9 and the score/EWMA/ε-exploration/auto-rotation/self-escalation machinery is **cut from the early phases**; (5) the scorecard credits **only verified success** — `skipped`/`concerns`/`error`/parse-failure are `unverified`, never positive. Rejected red-team items are listed in §12.

**Grounding files (read-only, absolute):**
`/Users/teacher/Library/CloudStorage/Dropbox/Learning/Code/Workflows/.github/scripts/agent_delegation_policy.js` · `/Users/teacher/.../Workflows/.github/workflows/{agents-keepalive-loop,agents-autofix-loop,reusable-agents-verifier,pr-00-gate}.yml` · `/Users/teacher/.../Workflows/.github/scripts/agents_verifier_context.js` · `/Users/teacher/.../Workflows/.github/agents/registry.yml` · `/Users/teacher/.../Workflows/config/llm_slots.json` · `/Users/teacher/.../Workflows/docs/contracts/{langsmith-fleet-v1,run-contract-v1}.md` · `/Users/teacher/.../Workflows/scripts/{langsmith_fleet,aggregate_agent_metrics}.py` · `/Users/teacher/.../Workflows/config/repo_review_feedback.json` · `/Users/teacher/.../Workflows/docs/LABELS.md` · `/Users/teacher/.codex/bin/{handoff,handoff-prerun,handoff-postrun,handoff-relay,lane-agents,cursor-lane,lane-worktree-gc,ccusage-snapshot}.sh` · `/Users/teacher/.codex/handoff/{lane-handoff.json,lane-agents.conf}` · `/Users/teacher/.codex/automations/*/automation.toml`.

---

## 1. Goal & Economic Thesis

**Impetus.** Anthropic now charges API prices for Claude CLI on remote projects, which is expensive at coding volume — but a premium model used as a *low-token local orchestrator* is cheap. Aider's architect/editor split is the closest validated prior art: a strong planner + cheap editor hit SOTA at **30–50% lower cost** because the cheap model does the token-heavy mechanical work while the premium model does only low-token reasoning. Anthropic's own routing finding confirms the seat is cheap: a mid-tier model reads a routing protocol and delegates about as effectively as the flagship at a fraction of the cost.

**Thesis.** Keep the premium model in the low-token orchestration seat; route high-token coding to the cheapest agent that can pass verification for that task class. The objective is **`$-per-VERIFIED-success` per task-type at a fixed quality floor — never `$-per-dispatch`**.

**The thesis has a *narrow* realizable-savings pool, and the design must respect that (red-team E1).** The flat-rate seats (Codex, Claude, Cursor) are *already paid* whether or not we route cleverly; the only true variable cost in the pool is **Aider/Codestral pay-go** and **Claude-API-on-remote-projects**. So the meta-system's own cost (Conductor tokens + LangSmith ingest + ledger compute + babysitter runs) is a *new* expense charged against a *narrow* pool. **Before building any learning machinery we compute the realizable-savings ceiling explicitly** (`monthly_paygo_spend + monthly_claude_API_remote_spend`) and gate the project's ambition to it. If that number is small, the project *stops at P0+P1* (ledger + shadow telemetry) and the learner/babysitter are never built. This is the single most important framing change from the red-team: **the apparatus must be cheaper than the savings it chases, and we measure that, not assert it.**

**Hard requirements (govern every decision below):**

1. **Rotatable orchestrator** — orchestrator is a *role*, reassignable to whichever agent has the best quality AND capacity; it self-escalates genuinely hard tasks to the *strongest worker agent* (NOT to itself — see §5/§12).
2. **Capacity + token aware (first-class)** — no usage API exists; model each agent from publicly-documented windows + a local consumption ledger keyed on **account**.
3. **Adaptive economics** — respond to token-price changes (config-instant), LangSmith perf/cost signals, and review-bot verdicts (earned, slow); optimize cost-per-*verified*-success.
4. **Verification is load-bearing — and today's harness is weaker than it looks.** Routing to cheap agents is only safe if a **deterministic, pre-merge, LLM-independent** check catches the misses. Gate CI is that check; the LLM verifier is post-merge corroboration. §8 closes the gap before cheap volume turns up.
5. **Anti-over-engineering** — keep routing legible, overridable, simple-first; the meta-system must not consume the savings or become undebuggable.

**Two design assertions the research forces:**

- **Prefer single-worker + strong independent verification over multi-worker/debate.** ~79% of multi-agent failures are spec/coordination problems *absent in single-agent* systems (MAST); Mixture-of-Agents locks in *false consensus* via correlated errors. The cheap win is one task → one cheap worker → catch its errors — not agents collaborating.
- **The orchestrator's own token budget is a first-class SLO with a runtime tripwire (not just a structural rule).** Subagent architectures cost ~7–15× tokens, with token usage explaining ~80% of performance variance. The "premium-orchestrator-is-cheap" thesis only holds if the orchestrator is *structurally* prevented from ingesting worker output **and** a ledger-derived alarm fires when the meta/worker cost ratio exceeds threshold (red-team G7).

---

## 2. Architecture Overview

```
                          ┌─────────────────────────────────────────────────┐
                          │  CONDUCTOR (rotatable role; premium, low-token)   │
                          │  default = claude; seat is a one-line conf fact   │
                          │  selection is a CHEAP LOCAL COMPUTATION — never    │
                          │  itself an LLM call (red-team O9)                  │
                          │  reads: task envelope + capacity.json + scorecard │
                          │  writes: ONE routing-decision (agent, budget,     │
                          │          fallback) — NEVER ingests raw diffs;     │
                          │          NEVER writes code (no self-escalation)   │
                          └───────────────┬─────────────────────────────────┘
                                          │  routing-decision.json  (one brain, one language)
                                          ▼
                          ┌─────────────────────────────────────────────────┐
                          │  DISPATCH — TWO entry points, ONE decision file   │
                          │  (a) cron tick → prerun  (b) relay between rounds  │
                          │  relay no longer hard-swaps codex↔claude; it reads │
                          │  routing-decision (red-team O2)                    │
                          │  mutex re-keyed to (lane,agent,target) (O1)        │
                          │  account-level capacity lock, read-time ledger     │
                          │  free-space dispatch gate (O6)                     │
                          └───────────────┬─────────────────────────────────┘
                                          ▼
        ┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
        │   Codex      │   Claude     │   Cursor     │  Gemini/agy  │  Aider+      │
        │ (flat,top,   │ (flat,top,   │ (flat,mid)   │ (overflow,   │  Codestral   │
        │  scrape cap) │  429-shed)   │  scrape cap) │  babysat,    │ (paygo,real $│
        │              │              │              │  P3+, last)  │  spend,1st   │
        │              │              │              │              │  overflow)   │
        └──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
                                          │  outcome by side-effect, ATTRIBUTED by author+trailer (O12)
                                          ▼
                          ┌─────────────────────────────────────────────────┐
                          │  PRE-MERGE GATE (the ONLY real gate, deterministic)│
                          │  Gate CI + full-diff security scan + test-quality │
                          │  + criteria-lint  (red-team L2/L3/L4/L8, §8)      │
                          └───────────────┬─────────────────────────────────┘
                                          ▼ (merge)
                          ┌─────────────────────────────────────────────────┐
                          │  POST-MERGE AUDIT (corroboration, NOT a gate)     │
                          │  reusable-agents-verifier (LLM judge) → verdict   │
                          │  structured verdict file (not grep-injectable, L1)│
                          │  cross-family judge = dispatch precondition (G3)  │
                          │  autofix loop (bounded; cannot edit tests, L7)    │
                          └───────────────┬─────────────────────────────────┘
                                          ▼
                          ┌─────────────────────────────────────────────────┐
                          │  FEEDBACK — VERIFIED signal only (L6, L3)         │
                          │  scorecard credits verdict=pass ONLY; skipped/    │
                          │  concerns/error/parse-fail = UNVERIFIED, never +  │
                          │  meta-cost tripwire computed here (G7)            │
                          └─────────────────────────────────────────────────┘
```

**Data flow, one sentence:** the Conductor reads small aggregates (task envelope, `capacity.json`, the per-(agent×tier) **verified** scorecard) via a cheap local computation, writes one legible `routing-decision.json` that **both** the cron-prerun and the relay consult, the chosen agent is dispatched inside a (lane,agent,target)-keyed critical section, a **deterministic pre-merge Gate** produces the only trusted *blocking* success signal (the LLM judge is post-merge corroboration), and the verified outcome feeds back as bounded counters — closing the loop without the orchestrator ever reading a diff or writing code.

**Reuse, honestly accounted (red-team A).** The genuinely-free reuse: the baton `case` lists in `handoff-prerun.sh`/`handoff-postrun.sh` **already accept `cursor|gemini|aider`**; `lane-agents.conf` already lists the agents; `acquire_lock` + atomic-`mv` + dead-PID force-clear exist; the `RELAY-HALTED` kill-switch exists; the verifier **does** emit `verdict`/`chain_depth`/`acceptance_criteria_count`; the `cursor-lane.sh` adapter mold is real (~55 lines). The **net-new** components (the design previously undercounted these as "~one scorer + one ledger") are **~9**: (1) capacity-ledger writer, (2) read-time `capacity.json` reducer, (3) Codex *and* Cursor scrape-parsers, (4) the verified-success join across verifier-metrics + LangSmith + ledger keyed on (agent×tier) — *which does not exist today*, (5) difficulty estimator, (6) route-table resolver, (7) decayed-counter updater (P3+ only), (8) PTY babysitter (P3+ only), (9) the per-tick decision trace. Plus 2 new config files. The "superset of `agent_delegation_policy.js`" claim is **conceptual, not literal** — that file is 389 lines of GitHub-Actions-side Node; the local Conductor is a Mac process. §11/Open-Q6 is resolved up front (§3.0): **one brain, one language — a small Python module on the Mac**.

---

## 3. Routing Policy

**Governing rule:** the router is a *scored pre-filter bolted in front of* the existing `decideNextAgent` switch logic, not a replacement. `decideNextAgent` answers "should the *incumbent* keep going?"; the router answers "of the *eligible* agents, which class should this task *start* on?" Keep them separate.

### 3.0 Where the brain lives (Open-Q6, resolved before P1 — red-team D1/O2)

**One brain, one language.** Routing/difficulty/capacity logic lives in a **single Python module on the Mac** (`router.py`), called by both dispatch entry points (cron-prerun and the relay). We do **not** maintain routing logic in two languages on two runtimes (that is red-team C3 institutionalized). The GitHub-side `agent_delegation_policy.js` stays as-is for its *own* job (incumbent-switch on stall, label-side); the local router *reads the same verified signals* but does not share its runtime. Requires Python on the Mac in the lane context (already present for the digest tools) — confirmed at P0.

### 3.1 Cheap difficulty estimation (no model call) — now coverage-aware (red-team G4)

Difficulty is estimated in the cheap seat **without reading code**, from metadata the keepalive/verifier steps already extract. Pure integer arithmetic, readable in a log line:

```
difficulty_tier(task):
    s  = clamp(files_touched, 0, 5)              # 0..5
    s += min(diff_lines // 50, 5)                # 0..5
    s += min(acceptance_criteria_count, 4)       # 0..4
    s += 3 * prior_failure_count                 # escalator: each failed round +3
    s += repo_difficulty_bias[repo]              # small per-repo constant (default 0)
    structural = trivial if s<=2 ; standard if s<=8 ; hard otherwise

    # coverage is a difficulty input, not just an eligibility gate (G4):
    inverse_coverage = hard     if target_path_coverage < 0.4
                       standard if target_path_coverage < 0.7
                       trivial  otherwise
    tier = max(structural, inverse_coverage)     # low-coverage floors the tier

    # hard floors (cannot be cheapened) — reuse Gate's own classifiers:
    if is_security_relevant or is_workflow_change: tier = hard   # from pr-00-gate.yml:53-54
    if touches_sensitive_path:                     tier = hard
    if label_hint == "hard":                       tier = hard
    if label_hint == "easy":  tier = max(trivial, structural, inverse_coverage,
                                         sensitive_floors)        # ADVISORY only (G4/E8)
    return tier, s, reason   # reason names the top-2 contributing terms
```

- **`prior_failure_count` weighted ×3** — how the system learns "this is hard" from failure with no ML; two failed rounds (+6) push almost anything to `hard`.
- **Coverage is now a *difficulty* term (G4), not only an eligibility gate.** `tier = max(structural, inverse_coverage)`: a one-line diff in a low-coverage file is **at least `standard`** regardless of size — because that is exactly where the harness can't catch a cheap miss. This unifies the estimator with §8's coverage-gate so coverage is computed once.
- **`label_hint == "easy"` is ADVISORY, not a hard floor (red-team E8/G4).** A wrong/adversarial `easy` label can no longer force a hard task to the cheapest agent; the sensitive/coverage/structural floors all still apply. Only `hard` is a hard floor (asymmetric on purpose — cheapening is the dangerous direction).
- **`is_security_relevant`/`is_workflow_change` reuse Gate's existing classifiers** (`pr-00-gate.yml:53-54`) as hard `hard`-floors.

### 3.2 The route table (the policy *is* this file — but the file is NET-NEW, not reuse)

Hand-editable `config/routing-policy.json`, read at decision time. "Agent class" resolves against `registry.yml` eligibility + the capacity ledger; the table names *ordered preferences*, first eligible+capacity-available wins. **This file does not exist today; it and its loader/validator are net-new (red-team A).**

```jsonc
{
  "trivial":  { "prefer": ["aider", "cursor", "codex"] },
  "standard": { "prefer": ["codex", "cursor", "claude"] },
  "hard":     { "prefer": ["<quality_leader>", "codex", "claude"], "self_escalate": false }
}
```

**Fixed-order resolution (the function body):**

1. **Manual override** — explicit `agent:<x>` PR label, or `~/.codex/handoff/route-override.json` pin → that agent, stop. (Mirrors `getExplicitAgentFromLabels` precedence.)
2. **Eligibility filter** — drop agents failing `checkPrerequisites` (missing secret), `lane-agents.conf == off`, or **below the free-disk floor** (O6).
3. **Capacity filter** — drop agents whose **account-level** `remaining_state ∈ {shed, off}`; `agent:rate-limited` ⇒ `shed`.
4. **Cross-family-judge precondition (G3, cheap tier only)** — before routing a *coding* task to a cheap-tier family, confirm a cross-family judge has verifier-capacity; if none, route the coding to a family whose judge *does* have headroom, else hold as `needs-human`. Never dispatch-then-judge-same-family.
5. **Difficulty self-escalation** — `hard` bypasses cost → strongest eligible *worker* agent (never the Conductor seat).
6. **Tier preference + hysteresis** — first eligible agent in the tier's `prefer` list; switch off the incumbent *only* if stalled AND past the 5-round cooldown.

`<quality_leader>` is one field (today `claude`); a Claude↔Codex flip is a one-line edit and `hard` re-points automatically. A small closed set of `task_type` tags may layer on (e.g. `merge_only_sweep` → force `trivial`); **`task_type` is advisory and never bypasses the sensitive/coverage floors** (E8). Do not build a taxonomy — see Open-Q2; **P0–P2 key counters on the 3 difficulty tiers only** (red-team C, A).

### 3.3 The score (DEFERRED to P3, off by default — red-team C5/C/A)

The continuous score `w_q·q − w_c·cost + w_cap·cap − w_pen·flag` and its EWMA counters are **not built in P0–P2.** Reasons (red-team): (a) the (agent×tier) cost-per-verified-success feed it consumes *does not exist today* and must be built first; (b) at a solo operator's dispatch volume (tens/week per tier) the counters rarely leave cold-start, so weights add illegibility for no signal. **P0–P2 routing is the 3-row table + capacity gate + difficulty tier — no score, no weights.** The score enters at P3 *only if* the P0–P2 decision trace shows the static table making a wrong call you can name. When it does enter, `w_c`/`w_pen` start as tie-breakers *within* a tier's `prefer` list (never reordering it) until each (agent×tier) has ≥N≈10 *verified* observations.

### 3.4 Escalation on repeated failure — now cost-gated and value-gated

`detectStall` (3 zero-progress rounds) stays the *agent-switch* trigger; the 5-round `inCooldown` stays the anti-thrash. But two corrections from the red-team:

- **Tier-upgrade is decoupled from agent-switch (red-team E5.2).** A *single* failed expensive verify round on a `trivial`/`standard` dispatch **immediately upgrades the difficulty tier** (`cost_stall = 1`) by incrementing `prior_failure_count` and re-running `difficulty_tier`. The agent-*switch* still waits for `detectStall=3`/cooldown=5 (anti-thrash for label-flipping), but the *tier estimate* corrects instantly so the next dispatch is to a stronger agent. This severs the cost-amplifier where the reused 3-round/5-cooldown machinery forced ~3–5 expensive verify cycles before correcting.
- **The escalation ladder tops out at the strongest WORKER, then a human — NOT the Conductor (red-team C2/G2, §5).** Ladder: `trivial → standard → hard → strongest-worker → agent:needs-attention (human)`. The **`orchestrator-self` rung is deleted**: a hard coding task is maximum token ingestion and would turn the cheap premium seat into the fleet's most expensive coder on exactly the worst tasks.
- **A per-task spend gate caps the ladder (red-team E5.3, G2).** Before re-dispatching one tier up, check `accumulated_cost(task) < task_budget` **and** `task_value ≥ value_threshold`. If a task has burned > K verify cycles, **skip the remaining ladder and go straight to `agent:needs-attention`**. `task_value` reuses existing signals (repo priority from the supported-repo tiering, opener-cap/`key-PR` pressure from the sentinel, or an `effort:`/`priority:` label) — a low-value, genuinely-hard chore must not ratchet up to the most expensive resources.

Escalation is monotonic up a finite ladder; it never cycles down on the same task. The only change to `decideNextAgent`'s switch branch is `alternatives[0]` → `rerouteByTier(task, ledger)` against the upgraded tier — and `rerouteByTier` is **net-new** (red-team confirms the switch is hard-wired to `alternatives[0]` today).

---

## 4. Capacity & Token Ledger

**Premise:** no agent exposes a queryable remaining-balance API. Cap *structure* is public; *balance* is not. The previous design blended **five correctness models** for one `remaining_frac` field (scrape, backoff-EWMA, exact, `cap×0.8`, calibration-EWMA, `soft_empty`) — the red-team correctly flags this as the single most likely thing to become undebuggable (C1) and as resting on a signal (`ccusage`) that the script *itself* says is inferred-not-measured (E2). **This revision collapses capacity to ONE model per agent and a 4-state enum, keyed on account.**

### 4.0 `remaining_state`: a 4-state enum, not a continuous float (red-team C, E2)

Per **account** (see §4.1), capacity is `{ok, low, shed, off}`:
- `ok` — dispatch freely.
- `low` — de-prioritize; eligible only if no `ok` agent can take the task.
- `shed` — not eligible as a **worker** (set by an observed 429/`agent:rate-limited` within the reset window, or scraped remaining below floor). May still **conduct** (see §5 asymmetry).
- `off` — `lane-agents.conf` off, missing secret, or below free-disk floor.

The continuous-float score is gone from P0–P2. This is the asymmetry the design actually needs (near-empty Claude can conduct but not code) reduced to **one enum + one boolean**, not a state machine (red-team D2).

### 4.1 Capacity is keyed on ACCOUNT, not lane-agent (red-team E3)

The windows are **per-credential**, consumed by opener + closer + interactive use of the *same* subscription. The previous per-agent ledger assumed the lane was the only spender; on a day of heavy interactive Claude use it would shed Claude from coding while the lane budget was untouched (mis-routing premium work). Therefore:

- **One `capacity.json` per credential**, written under a **single account-level lock** (NOT the per-lane mutex — different scope), with both lanes decrementing the same counter.
- A per-account **`reserve_for_interactive`** band: foreground use gets first claim; lanes route around it. On days with foreground activity we widen the Claude safety margin (or read the session count where available).
- Ledger rows tag `actor = lane | interactive`; only `lane` rows are authoritative for lane capacity (interactive is invisible to scrape, so it only ever *widens* the margin, never narrows it).

### 4.2 Where it lives, and how it's read (red-team O4 — no two-writer derived state)

Two files under `~/.codex/handoff/` (local FS only — never the Dropbox mount, which rejects `.git`/lock writes; bash-3.2 + BSD-`date` portability per MEMORY):

- **`capacity-ledger.ndjson`** — append-only event log; one row per dispatch + one per backoff/reconcile. Append is a single `>>` under the account lock; never rewritten.
- **`capacity.json`** — **a pure read-time reduction over the NDJSON** (router tails the log, applies the reset/decay window, derives the 4-state enum). It is **not** a file two processes rewrite — that lost-update race is exactly the F12 the ledger exists to prevent (red-team O4). Every dispatch row carries `task_id` so reconciliation is **idempotent** under retry.

**Ledger row:**
```jsonc
{"ts":"…Z","account":"anthropic-teammax","agent":"claude","actor":"lane","lane":"closer",
 "task_id":"…","repo":"stranske/Trend_Model_Project","difficulty":"standard",
 "unit_kind":"active_minutes","est_units":7,"obs_units":null,"outcome":null,
 "window":"5h","window_shape":"rolling","backoff_seen":false}
```

### 4.3 The capacity signal hierarchy — INVERTED from the draft (red-team E2)

The draft made scraped `ccusage` "near-ground-truth" and let it overwrite the model. **`ccusage-snapshot.sh`'s own header says its `$`/`%` figures are API-equivalent and inferred from your own peak block, not a real plan cap, and Claude totals include interactive sessions.** Pinning the ledger to that and calling it ground-truth is wrong. Inverted hierarchy:

1. **Observed 429 / backoff = the real ceiling (authoritative).** It is an *observation*, not an inference. `agent:rate-limited` (auto-applied, keepalive-cleaned) ≡ `remaining_state = shed` for that account until the observed reset. This unifies the existing recovery path with the ledger.
2. **Scraped remaining % (Codex, Cursor) — a useful but WEAK prior.** Codex/Cursor print a figure in their own CLI/UI; read it, but it never *overwrites* an observed-429 shed. It maps to the enum (`<15%` ⇒ `low`) and decays out once a real observation exists.
3. **`ccusage` — a cold-start HINT only, never authoritative (E2).** Demoted from "overwrite" to "weak prior that decays out after ≥1 observed reset." Tagged `actor`-aware so interactive use doesn't silently debit the lane model.
4. **Aider/Codestral — exact real $ spend**, capped by `$/day`. This is the one true variable cost (E1) and the one source that *cannot* be modeled away — P0 must confirm a real `spend_usd` row is written per Aider dispatch.

**No `cap×0.8` / tighter-for-unreadable / calibration-EWMA stack (red-team C/D2).** For the unreadable agents (Claude/Gemini) the rule is the dumb one: **`ok` until an observed 429 → `shed` until the observed reset.** Learning the unpublished weekly cap "over a few reset cycles" (weeks) is not worth a subsystem; 429-shed is ~95% of the value for ~5% of the code.

### 4.4 Window shape is modeled per-agent (red-team E9), and cliffs are ramped (red-team E6)

- **Window shape is a per-agent field, not a uniform "stamp to 0 until reset."** `rolling` (Codex/Claude 5h: oldest spend ages out continuously — the read-time reducer decays spend by `elapsed/window_len`, so a 429 means "shed for ~window_len from the tipping spend," not "dead until a guessed reset T"); `fixed-bucket`; `calendar-anchor` (Cursor monthly $ pool — reconcile by **dispatch** timestamp so a round straddling the anchor charges the window it *started* in). **Max's two weekly buckets** are represented as two windows; gate on the tighter.
- **Date-aware cap cliffs are RAMPED, not stepped (red-team E6).** Known cliffs in the planning horizon (Codex 2× boost ends 2026-05-31; **Gemini AI-Pro CLI access ends 2026-06-18**; Claude weekly +50% ends 2026-07-13) taper the modeled cap linearly over the 48h around the date, so a cliff doesn't trigger a discontinuous mass re-route → simultaneous 429s → herd-shed onto the flaky overflow path. A **global re-route rate limiter** caps the fraction of active tasks that may change assigned agent in a single tick, regardless of score — a circuit breaker on herd movement.
- **P3's `agy` enablement is sequenced AFTER the 2026-06-18 Gemini cliff is absorbed** (red-team E6 timing) — do not land Gemini's first real traffic onto a just-collapsed cap.

### 4.5 Decrement on dispatch, reconcile on completion — crash semantics fixed (red-team E4)

Charge **intent-to-dispatch immediately** with a conservative estimate so the next dispatch sees correct capacity. Reconcile actuals afterward where a source exists. **The fix the red-team forces:**

- **Charge request-overhead at dispatch; work-units at reconcile; refund NOTHING on crash** — the overhead (e.g. Gemini's ~24k tokens/call) was really spent even on a crash.
- **Never store a ratio with a zero denominator.** Track `cost_per_attempt` and `verified_success_rate` as **two separate counters**, combined only at read time with the clamp. A crash (no verified success) does not make the metric infinite/undefined; it correctly drags the success-rate counter down — the most informative sample, not a dropped one.
- **Claude/Gemini are honestly open-loop-conservative.** They expose no actuals source, so for them the dispatch estimate = the conservative window model and we *stop pretending reconcile happens*. This is an argument for keeping Gemini overflow-only and treating Claude-as-worker cautiously once its seat is tight.

---

## 5. Rotatable Orchestrator (the "Conductor")

The Conductor is **the low-token decision pass that writes `routing-decision.json`**, not a daemon and not a coder. **Critically (red-team O9): Conductor *selection* is a cheap local computation that cannot itself require an LLM call** — it reads `lane-agents.conf` + `capacity.json` + the verified scorecard and picks. Expensive routing *reasoning* (a premium model call) happens only when difficulty is genuinely ambiguous, and even then it never reads diffs.

**The seat is a one-line config fact:**
```
# ~/.codex/handoff/lane-agents.conf
conductor=claude
conductor_fallback=codex,cursor          # claude is implied first; fallback chain when shed
```
Claude holds it today. Reassignable by editing one line (fail-open, next-tick-effective).

**Auto-rotation machinery is CUT from P0–P2; the seat is a manual one-line edit (red-team C).** The seat field exists from P0 (free). The three-trigger auto-rotation (release-shift / capacity-exhaustion / manual-pin) with hysteresis margins is **deferred to P3 and reconsidered there** — you will know about model releases anyway, and a one-line edit when a release lands is strictly simpler than rotation triggers + `CONDUCTOR_RESERVE` asymmetry. **The one piece that is NOT optional even pre-P3:** capacity-exhaustion fail-over must be **synchronous per-tick** (red-team O9) — a 429 on the seat demotes to `conductor_fallback` *that tick* and fires a `PushNotification`-class alert (never silently degrade — MEMORY `feedback_monitor_long_runs`; never wait for a weekly cadence). The "fail-open to claude" rule is **not circular when claude is the down thing**, precisely because selection is the cheap local computation above and reads the live `shed` state.

**Self-escalation of hard tasks → strongest WORKER, never the seat (red-team C2/G2).** trivial/standard route down; `hard` → strongest eligible *worker*; genuinely-hard/repeatedly-failed/over-budget → `agent:needs-attention` (human). The premium seat never writes code. (Removed: the draft's "orchestrator does this one task in-band" rung — see §12 for why this is a rejection of the draft's own feature, kept here as a hard deletion.)

**`CONDUCTOR_RESERVE` asymmetry, simplified.** A `shed`-for-coding account can still hold the seat if it has any headroom at all — encoded as the single boolean "`shed` blocks worker dispatch but not conducting," not a separate continuous reserve float (red-team D2). If the seat account hits a true `off`/hard-429, synchronous fail-over fires.

**Two framing rules (unchanged, load-bearing):** (1) *The Conductor never writes code* — a decision that needs deep code reading is a signal to escalate the task, not to think harder in the cheap seat. (2) *Fail-open to today's behavior* — every absent input degrades to `conductor=claude` + the current static lanes.

---

## 6. Agent Adapters, Babysitting & Cleanup

**Shape:** every coding agent is reached through **one POSIX-shell adapter** (`<agent>-lane.sh <opener|closer>`), cut from the `cursor-lane.sh` mold, all honoring the three-call baton. The orchestrator's *entire* vocabulary onto the pool is "dispatch the agent named in `routing-decision.json`" + reading back one run-record.

**The mutex and relay reuse claims are CORRECTED (red-team O1/O2) — these are the central concurrency fixes:**

- **O1 — Re-key the round mutex from per-lane to (lane, agent, target).** Today `handoff-prerun.sh:56` keys `.lane-$lane.lock` on the *lane only*, so all agents running the closer lane contend on **one** lock dir — 4 of 5 pool agents would hit `RELAY-HALTED ... already has a round in progress` and silently skip the tick (`prerun.sh:67`). Fix: the Conductor acquires the lane critical section and invokes the chosen worker *inside* it (worker never runs prerun's mutex logic itself), **and** a sentinel lane-occupancy gate prevents two agents both picking `closer#312`. Without this, the scheduler — not the Conductor — picks the agent, and routing is non-deterministic.
- **O2 — Route the relay through the Conductor; it is NOT a fan-out today.** `handoff-relay.sh` is a hard-coded `codex ↔ claude_code` swap (literally `prompt//HANDOFF_AGENT=codex/HANDOFF_AGENT=claude_code`) that fires the *other* CLI in the background between rounds. It has no concept of 5 agents or capacity. There are **two schedulers** (cron tick + relay) and the draft modeled only one. Fix: the relay calls the router to choose the next agent (replacing the hard-coded swap) and reads `routing-decision.json`; prerun no-ops if a relay-launched round for that (lane,agent,target) is already live (mutex must cover relay-launched rounds).

**Five mandatory phases per adapter (fixed order):**

| Phase | Does | Reuse |
|---|---|---|
| 1. Auth | resolve credential; `export HANDOFF_AGENT`; fail-fast w/ distinct exit codes; **set own process group** (O7) | `cursor-lane.sh` |
| 2. Prompt refresh | re-render lane prompt from the **Codex TOML SSOT** | `render-*-prompts.sh` |
| 3. Translation preamble | map Codex "skills" → "use `gh` + `~/.codex/bin` + judgment"; restate "FIRST bash = prerun, LAST = postrun" | `cursor-lane.sh` |
| 4. Supervised invoke | run CLI under the babysitter (PTY/timeout/capture as needed); **`kill -- -$pgid` on timeout** (O7) | new `pty-run.py` |
| 5. Outcome capture + cleanup | diff repo state → outcome → run-record; **delete worktree on terminal outcome** (O6) | §6 below |

**Per-CLI cheat-sheet:** Codex → `codex exec -p`; Claude → `claude -p` (treat `not_logged_in` as hard `RELAY-HALTED`, not retry — MEMORY `feedback_scheduled_task_oauth`); Cursor → `cursor-agent -p --force --output-format text`; Gemini → `agy …` under PTY (P3+); Aider → `aider --message --yes --model codestral/…`. A new agent = one ~50-line adapter + render script + one `case` line + one conf line.

**Outcome attribution is by AUTHOR + trailer, not raw delta (red-team O12/G5/L6) — load-bearing for the scorecard:**

- With a shared canonical and concurrent agents, a `new commit` between before/after snapshots **may be another agent's commit**. Attribute by **commit author/committer + a `HANDOFF_AGENT` trailer the adapter injects**; diff only commits whose parent was the pre-snapshot HEAD *and* whose author is this agent. Without trailer-based attribution the scorecard is poisoned exactly when concurrency is highest.
- **A commit is NOT a verdict (G5/L6).** Distinguish `advance` (committed *and* the diff touches a file the task envelope names) from `touched` (committed but unverifiable locally). `touched` records `verified:false`, does **not** count as success in the scorecard, and does **not** fire a terminal baton event until the server-side verdict lands. This keeps "only verified = success" true at the local layer and stops a single stub commit on `agy` from smuggling in a fake success or advancing the baton over real work.

**The `agy`/Gemini babysitting contract (P3+ only; worst case):**
- **(a) PTY to defeat no-stdout-under-pipe (#76):** `stdbuf -oL -eL` first; if the CLI keys on `isatty`, a real PTY via one shared `~/.codex/bin/pty-run.py` (stdlib `pty.spawn` + wall-clock alarm). Python shim over `script(1)` for macOS portability.
- **(b) Warm keychain (#85):** run lanes as a **LaunchAgent, not a LaunchDaemon**; pre-touch via `security unlock-keychain` on a timer (not per-call — each `agy` call carries ~24k-token overhead).
- **(c) Side-effect outcome with attribution (above).**
- **(d) Supervision + orphan reaping (red-team O7):** hard wall-clock timeout via the `pty-run.py` alarm; **kill the whole process group** (`kill -- -$pgid`), not just the top PID, or the PTY child orphans holding a keychain session + worktree — the exact leak MEMORY `feedback_dropbox_fs_agent_fanout` records. Write a **PID/PGID file** so a reaper can find orphans, and **extend the existing `com.stranske.claude-agent-reaper`** (which targets Claude agents only) to cover `agy`/`cursor-agent`/`aider`. At most one jittered retry on timeout/crash/empty-diff; then the *orchestrator* (not the adapter) picks the fallback.

**Cleanup is first-class, because the leak already happened (red-team O6).** `lane-worktree-gc.sh`'s header documents a realized incident (447 worktrees / 66 GB / 92%-full volume) at *2-agent* volume. Adding 3 more worktree-creating agents at higher dispatch rate without lifecycle management invites a disk-full → true fleet halt. Therefore:
- Adapters **delete their worktree immediately on a terminal outcome** (merge/close); archive on `no_op`.
- A **pre-dispatch free-space gate** in `checkPrerequisites` refuses to dispatch below N GB free — disk is the one capacity dimension the ledger doesn't model and the one that hard-stops the *whole* fleet.
- The GC idle window **drops from 14 days to days** at pool volume.
- Worktrees live on **local disk** (the GC already assumes `~/.codex/automations/*/worktrees`); adapters must inherit that, never write worktree metadata to the Dropbox mount.
- Snapshot/temp files go **under the per-round worktree/lock dir** so they're reclaimed with it (EXIT traps don't fire on SIGKILL).

**Failure is scoped, never a fleet halt.** A wedged CLI records `crashed`/`timeout` and, if a target is implicated, calls `handoff.sh scope-blocker <target>` — never `request-pause`. **Pool agents may NOT propose/review a peer-review pause (red-team O10):** the relay's pause path is a 2-agent gate (proposer + one reviewer) defined only for codex↔claude; a gemini-proposed pause has no defined reviewer and would silently degrade to self-review (`relay.sh` preflight-fallback). Rule: only codex/claude can propose/review pauses; pool workers can only `scope-blocker` or record a crash. **Kill switch:** `lane-agents.sh off <agent>` makes the next prerun return `RELAY-HALTED` and self-release the mutex.

**The force-clear timeout must exceed the slowest worker's hold (red-team O5).** `acquire_lock` force-clears a *live* PID after a timeout tuned for fast codex/claude sentinel writes; a multi-minute `agy`/aider round would be force-cleared mid-work → two agents mutating the same sentinel/worktree (silent corruption). Fix: the babysitter **heartbeats the lock** (re-stamps `meta` ts while alive) so age-based takeover never fires under a legitimately-slow worker, and the global-lock force-clear timeout exceeds the slowest worker's sentinel-hold.

**Run-record** (append-only NDJSON, `~/.codex/handoff/ledger/<agent>.jsonl`; the *only* thing the orchestrator reads back — never the transcript):
```jsonc
{"ts":"…Z","agent":"gemini","lane":"closer","target":"stranske/Trend_Model_Project#312",
 "baton_round":47,"outcome":"touched","verified":false,"author_attributed":true,
 "cost":{"unit_kind":"request","est_units":1,"obs_units":1,"overhead_tokens":24000,"wall_seconds":412},
 "supervision":{"pty":true,"pgid":54231,"retries":1,"timeout_hit":false,"stdout_bytes":0},
 "verdict":null,"verdict_provenance":null,"langsmith_trace_id":null,"backoff_seen":false}
```
`verdict`/`verdict_provenance` are filled later from the post-merge verifier, keyed by `target`+`baton_round`, so the join can compute cost-per-**verified**-success.

---

## 7. Economics & Feedback Model

**Objective (formal, legible) — now null-safe (red-team G1):**
```
expected_cost_per_success(a, tier) =  expected_$(a, tier) / verified_success_rate(a, tier)

route(t) = argmin_a expected_cost_per_success(a, tier)
           s.t.  verified_success_rate(a, tier) ≥ quality_floor(tier) + margin   # hard; barely-passing is NOT cheap-eligible (E8)
                 AND remaining_state(account(a)) ∈ {ok, low}
                 AND prereqs(a) present  AND cross-family judge has capacity (G3)
```

- **The cost-per-verified-success feed DOES NOT EXIST today and must be built (red-team A, G1).** `langsmith_fleet.py` has `cost_usd` but **no `task_class` dimension and no verdict join**; `aggregate_agent_metrics.py` classifies by verdict but does not emit `cost_per_verified_success[agent][tier]`. Building this join (verifier-metrics + LangSmith + ledger, keyed on agent×tier) is the **biggest hidden build** and the draft mislabeled it "already emitted." P1 builds it in shadow.
- **`cost_usd` is OPTIONAL in the contract and frequently null (red-team G1).** `langsmith-fleet-v1.md:80` marks it optional; `run-contract-v1.md:63,67` documents it empty in practice. The objective is **null-safe**: when `cost_usd` is absent, fall back to *modeled* cost (`agent_economics.json` price × ledger `est_units`) and flag the cell `cost_source: modeled|observed`. **P2's "turn `w_c` on" is BLOCKED until ≥N cells per agent are `observed`** — otherwise the optimizer tunes economics on a constant.
- **Quality floor is a hard constraint *with margin* (red-team E8).** A cheap agent eligible for the *cheap-wins* path only if `verified_success_rate ≥ floor + margin` (e.g. +15pp). Barely-passing agents (just over a 50% floor) cost maximal rework per success; they may run only via the (deferred) ε-path, never as the primary cheap route.
- **`expected_$` unifies flat-rate and pay-go**, and now **charges verification externalities (red-team E5.1/E7)** — see below.

**Verification cost is charged to the routing decision (red-team E5.1/E7) — the dominant hidden cost the draft's optimizer was blind to:**
Every Gate run + LLM-judge call + autofix attempt triggered by a dispatch is added to that `(agent,tier)` attempt's cost in the ledger, **including the cross-family judge's cost** (which is disproportionately the *premium* model when the worker is cheap — E7: scaling cheap dispatch mechanically scales premium judging). Only with this charged does `$-per-success` see the true cost of a cheap-agent gamble: a cheap agent that needs 3 verify cycles per success correctly becomes *more* expensive than a one-shot premium agent. Where the cross-family judge would be premium and capacity is tight, prefer **deterministic Gate-only gating on `trivial`/high-coverage paths** (skip the LLM judge entirely — it's post-merge corroboration anyway, §8) rather than buying a premium judge.

**Inputs:**

| Input | Source | Note |
|---|---|---|
| token/seat prices | **config** `config/agent_economics.json` (net-new; hot-swap; date-aware cap table) | price = config-instant |
| **verified** success rate | post-merge verifier `verdict` + Gate `gate_conclusion` via the **net-new** (agent×tier) join | `skipped`/`concerns`/`error`/parse-fail = **unverified, never +** (L3/L6) |
| real $ (pay-go) | Aider `spend_usd` row | the one cost that can't be modeled (E1) |
| cost/latency | `langsmith-fleet-v1` (`cost_usd` often null → modeled fallback) | G1 |
| review-bot down-weight | `config/repo_review_feedback.json` | earned |
| chain depth (rework) | verifier `chain_depth` | rising = down-weight before outright fail |
| meta-cost ratio | ledger reduction (Conductor tokens ÷ worker tokens) | **tripwire — G7** |
| capacity headroom | read-time `capacity.json` | 4-state enum |

**Weight updates — slow, bounded, auditable, and DEFERRED to P3.** When built: three decayed counters per (a,tier), updated once per aggregation cycle: `q` ← EWMA(**verified** success), `cost` ← EWMA(cost/verified-success), `flag` ← EWMA(review_flag_rate). Discipline: **EWMA not retrain** (learned routers oscillate); **min-sample gate** (N≥5–10 *verified* obs) before a prior leaves cold-start; **clamps** (`q∈[0.02,0.98]`). **Split half-lives by volatility (red-team G6):** `cost`/`flag` get the slow 14–21d half-life (genuinely slow-moving); **`quality_rank` for the conductor-seat and hard-tier routing gets a SHORT 3–5d half-life plus an event-reset hook** — a manual `quality_leader` edit *zeros the incumbent's prior* (does not blend against two stale weeks), and cliff dates nudge priors, because a model release / cap cliff is a known forcing event, not something to slowly rediscover. (The draft claimed a 14–21d half-life "propagates within days" — it does not; this corrects that internal inconsistency.)

**Two adaptation paths, deliberately distinct:**
- **Price change → config edit, instant, no learning.** *Prices we trust on declaration.*
- **Efficiency gain → earned via the VERIFIED success counter.** *Quality we trust only on harness-verified demonstration.* An agent cannot talk its way into more traffic; failure is *priced in* (rework + judge + extra `chain_depth` cost charged to that (a,tier)).

**Anti-starvation ε-exploration — DELETED for now (red-team C5/E8/G8).** At a solo operator's volume (tens of dispatches/week per tier), ε≈5–10% mostly means randomly sending ~1-in-15 tasks to a worse agent, paying rework/judge cost, to gather statistics the min-sample gate means you'll rarely accumulate. Worse, it can leak traffic into a *freshly-regressed* agent (G8) and farm the at-floor band (E8). **Cut outright.** If, at P3, the decision trace shows lock-in to a stale winner, reintroduce ε **only** gated on the *fast* (3–5d) quality signal and the `floor+margin` band — never into an at-floor or recently-regressed arm.

**Realizable-savings tripwire (red-team E1/G7) — first-class, not asserted:**
- The **Conductor's own token spend is a line item in the ledger** (it is an agent too).
- Define orchestrator success as `baseline_$ − (routed_$ + meta_$) > 0`, logged weekly, where `baseline_$` = "send everything to the flat-rate seat with capacity."
- A hard **meta-cost tripwire**: if `conductor_cost / dispatched_worker_cost` exceeds threshold (e.g. >15% over a rolling window) **OR** orchestrator success goes negative for 2 cycles, fire the `PushNotification` alert and **auto-`off-router`** to static lanes. This is the #1 stated failure mode (F9) given an actual detector — wired into P0's verify, not added after the savings are gone.

---

## 8. Verification & Safety

**The thesis correction that reframes this whole section (red-team safety lens):** the draft treated "Gate + verifier + autofix" as a three-layer **merge gate**. Grounded in the files, it is not:
- `reusable-agents-verifier.yml` runs **only on merged PRs** (`agents_verifier_context.js:271,286` → skip if `pr.merged !== true`; the context literally says *"This verification runs post-merge. CI status is irrelevant."*). **The LLM judge is a post-merge auditor, not a pre-merge gate.**
- The verifier's follow-up-issue creation is **hard-disabled** (`reusable-agents-verifier.yml:1162`, gated `if: github.run_id == 0`, never true). A FAIL emits an NDJSON `needs-human` artifact and **posts nothing / opens no issue** by default.
- **So the only true pre-merge gate today is Gate CI** (`pr-00-gate.yml`), which on the Workflows repo sets **`coverage-min: ''`** (no coverage floor) and has no security diff-scan.

This **inverts the safety thesis**: routing more volume to weaker agents pushes more confidently-wrong code through the one deterministic gate and relies on a human noticing an artifact. **The design therefore adds the missing deterministic, pre-merge, LLM-independent checks BEFORE cheap volume turns up (P2 must not land before these).**

**Layers, corrected:**
1. **Gate CI (the ONLY real pre-merge gate) — hardened:**
   - **Full-diff, LLM-independent security scan** (semgrep/gitleaks rules: removed auth checks, widened workflow permissions, `eval`, `# nosec`, dependency-pin downgrades), run on the **full** diff (immune to the verifier's 50-file/20k-line/300k-char truncation — red-team L4). Reuse Gate's existing `is_security_relevant`/`is_workflow_change` classifiers (`:53-54`).
   - **Test-quality eligibility (red-team L2):** no coverage floor + same-agent-authors-impl-and-tests = self-locking green tests. Reject cheap-tier PRs whose new test files contain only truthiness asserts; require ≥1 assertion against a literal expected value; **forbid the same cheap agent from authoring both the fix and its only new tests** for `bugfix`/`feature` (cheap agent implements; criteria author / different agent owns the acceptance test).
   - **Criteria-lint (red-team L3):** any PR carrying `agent:<x>` must contain parseable Tasks+Acceptance sections or Gate fails — closing the verifier's `should_run=false` skip hole on the one real gate.
2. **`reusable-agents-verifier.yml` (post-merge corroboration, NOT a gate) — hardened:**
   - **Structured verdict file, not grep-injectable (red-team L1):** today the verdict is `grep -qiE 'verdict:\s*pass'` over agent-authored text that *includes the diff*, so a worker can write `Verdict: PASS` into its own diff/comment/test-name and the judge echoes it → false pass. Fix: the judge writes JSON to a separate path the diff cannot contain (`$RUNNER_TEMP/verdict.json`); strip the diff fence before parsing; **any `verdict:` string inside the diff region ⇒ tamper ⇒ forced FAIL + agent flag.**
   - **Cross-family rule, fail-CLOSED (red-team L5/G3):** `compare` mode today PASSes on whatever judges are *available* (`:1022-1028`) and silently degrades to single same-family when the cross-family key/capacity is missing; `evaluate` defaults a missing result to `CONCERNS` (`:815`), a soft non-event. For **cheap-tier** PRs: cross-family judge availability is a **dispatch precondition** (§3.2 step 4); `compare` with <2 usable judges ⇒ blocking `concerns`, not pass; `evaluate` parse-failure ⇒ blocking `error`, not `CONCERNS`; emit `verdict_provenance: same_family_fallback` and the scorecard treats it as **unverified** (never earns traffic).
   - **Re-enable a real consequence for FAIL:** either re-enable follow-up-issue creation or make `needs-human` page a human (synchronous `PushNotification`). A post-merge FAIL that posts nothing is not a safety net.
3. **`agents-autofix-loop.yml` (bounded repair) — scoped (red-team L7):** autofix exists to make **Gate** pass on cosmetic classes (it already self-limits to `py,pyi` cosmetic for the auto-label, `max_attempts: 2`, `needs-human` on exhaustion). **Forbid autofix from editing test files or assertions on cheap-tier PRs** (a fix that rewrites the test to match wrong output is the canonical gamed pass). Count `autofix attempts > 0` as a **quality-cost charge** against that (agent×tier) — a near-miss is not free (§7).

**The scorecard credits VERIFIED success ONLY (red-team L6/L3) — the load-bearing feedback invariant:**
`calculateEffectiveness`/`detectStall` (effectiveness = `commits>=1`, `agent_delegation_policy.js:223`) is kept for **liveness/anti-thrash only** — it is NOT a quality signal (a confidently-wrong agent that commits every round is "effective" and never escalates). The router's quality counter is fed **only** by post-merge `verdict=pass` (via the verified-success join), revert rate, and follow-up-issue rate. `skipped`/`concerns`/`error`/parse-failure/`touched`/`same_family_fallback` are **`unverified` — never positive, never neutral.** Add a **churn-without-verification detector**: N commits with no `verdict=pass` and rising `chain_depth` is a *down-weight + escalate* trigger (the inverse of today's "commits = good").

**Why the reward is (now actually) un-gameable.** The draft claimed un-gameable-because-server-side; the red-team showed two holes: the verdict parse was grep-injectable (L1) and a non-pass defaulted to *silence* the scorecard could misread as neutral (L3/L5). Both are closed above: structured verdict file + tamper-detection, and "unverified ≠ success." Now success is computed server-side on infra the local agent doesn't control, *and* the local parse can't be spoofed, *and* a non-pass can never earn traffic.

**Anti-over-engineering guardrails (each mapped to existing plumbing):**

| Property | Mechanism | Reuse |
|---|---|---|
| **Legible** | 3-tier table + fixed-order gate chain; every decision a one-line trace | `formatDelegationSummary` |
| **Overridable** | label/pin > eligibility > capacity > cross-family > self-escalation > tier-pref+hysteresis | `getExplicitAgentFromLabels` |
| **Kill-switch + pin** | `lane-agents.sh off <agent>`; `conductor=<agent>`; `off-router` → static lanes; meta-cost tripwire auto-`off-router` | `lane-agents.conf` (fail-open) |
| **Observable** | per-tick **decision trace** (chosen vs ran vs why-skipped + held worktree/lock) | `acquire_lock`/atomic-`mv` |
| **Orchestrator token SLO** | never ingests diffs; **ledger-derived meta-cost tripwire** (not just a structural rule) | `langsmith-fleet-v1` no-raw-payload |

**Rollback is NOT uniformly "delete a file" (red-team O13).** True for the scorecard, economics weights, route table. **Not** true for the mutex re-key (a semantic change to `handoff-prerun.sh`) and the new launchd plists: `off-router` while cursor/gemini schedulers stay loaded leaves them firing and contending (O1). Rollback is therefore defined as: `lane-agents.sh off <agent>` for **all** pool agents **+ a documented `launchctl unload` list**, and the mutex code must be backward-compatible with both lock-key schemes during a rollback window.

---

## 9. Observability: the per-tick decision trace (red-team O14 — highest-value addition)

With two dispatch entry points (cron + relay) × up to 5 agents, "why did agent X run / not run this tick?" requires joining ~6 files. `formatDelegationSummary`'s one-liner is necessary but insufficient: it never fires when a decision is overridden by a relay-launched round (O2) or lost a mutex race (O1). Therefore **emit one decision trace per tick**, keyed by `(lane, tick_ts, dispatch_source ∈ {cron, relay, self-escalate})`, recording:
- who the Conductor **chose**, and the tier + top-2 difficulty reasons;
- who actually **ran** — or why the tick **skipped** (`mutex-lost` / `off` / `halted` / `capacity-shed` / `disk-floor` / `no-cross-family-judge`);
- the worktree + lock it held, and the `task_id`;
- the capacity enum per account at decision time (so a "why was Claude skipped" answer doesn't require reconstructing five correctness models — there's now only one).

One greppable line that closes the gap between *intended route* and *what the OS actually executed*. This is the prerequisite for debugging every concurrency case in §6.

---

## 10. Risks & Failure Modes (strengthened with red-team findings)

| # | Failure mode | Source | Design counter |
|---|---|---|---|
| F1 | Over/under-routing (cheap gets hard) | RouteLLM | Difficulty tier + **coverage-as-difficulty** (G4) + per-tier quality floor **+margin** (E8); objective is cost-per-*verified*-success |
| F2 | Router overfit / drift | RouteLLM | EWMA priors (P3) w/ bounded half-life + min-sample gate on *verified* obs; **coverage floors the proxy** (G4) |
| F3 | Orchestrator context bloat → seat not cheap | Claude Code ~7×, Anthropic ~15× | No raw diffs; **ledger-derived meta-cost tripwire + auto-`off-router`** (G7), not just a structural rule |
| F4 | Lossy spec on handoff | MAST, Aider | One structured task-spec (acceptance criteria + constraints + repo gotchas) |
| F5 | Premature "done" (PR layer) | OpenHands, MAST | Server-side verdict authority; outcome by git side-effects |
| **F5b** | **Premature "done" at the side-effect layer — commit ≠ verdict** | **red-team G5/L6** | **`advance` requires a commit touching a named file; else `touched`/`verified:false`; never counts as success, never fires terminal baton** |
| F6 | Verifier monoculture | MoA | Provider≠worker; **fail-CLOSED** (G3/L5): cross-family judge is a dispatch precondition; `compare`<2 judges ⇒ blocking; same-family-fallback = unverified |
| F7 | Failure cascade / runaway spend | Anthropic | Bounded fan-out (no worker-spawns-worker); **per-task spend + value gate caps the ladder** (E5.3/G2); `scope-blocker` |
| F8 | Delegation overhead on trivial | Claude Code | trivial → cheapest capped agent |
| F9 | **Meta eats the savings / undebuggable** | MAST #1 | **Realizable-savings ceiling computed first (E1); meta-cost tripwire (G7); per-tick decision trace (O14); ~9 components honestly counted; score/EWMA/ε/auto-rotation/babysitter all deferred or cut** |
| F10 | Router oscillation | adaptive-reward lit | EWMA not RL (P3); 5-round cooldown; switch on 3-round stall; **global re-route rate limiter** (E6) |
| F11 | macOS/`agy` fragility | `agy` #76/#85 | PTY shim; LaunchAgent + warm keychain; **process-group kill + PGID file + extended reaper** (O7); side-effect outcome; `agy` overflow-only, P3+, post-cliff |
| F12 | Capacity mis-estimate → mid-task 429 | no usage API | **One model per agent: 429-shed authoritative; ccusage demoted to decaying hint (E2); per-ACCOUNT keying + interactive reserve (E3); read-time ledger, no two-writer derived state (O4); per-agent window shape (E9)** |
| F13 | Concurrent-lane race | MEMORY | **(lane,agent,target) mutex re-key (O1)**; re-verify before terminal action; skip relay if not the transitioning actor |
| **F14** | **Relay overrides the Conductor (two schedulers)** | **red-team O2** | **Relay reads `routing-decision.json` instead of the hard-coded codex↔claude swap; prerun no-ops if a relay round is live** |
| **F15** | **Per-lane mutex starves the pool (4/5 agents skip ticks)** | **red-team O1** | **Re-key to (lane,agent,target); Conductor invokes worker inside the critical section; sentinel lane-occupancy gate** |
| **F16** | **Worktree/disk leak → true fleet halt** | **red-team O6; realized incident** | **Pre-dispatch free-space gate; delete-worktree-on-terminal; GC window days-not-weeks; local-disk worktrees** |
| **F17** | **Orphaned PTY/agent processes** | **red-team O7; MEMORY** | **Process-group kill; PGID file; extend `claude-agent-reaper` to all CLIs** |
| **F18** | **Force-clear kills a slow live worker → silent dual-write** | **red-team O5** | **Babysitter heartbeats the lock; force-clear timeout > slowest worker hold** |
| **F19** | **Conductor seat exhaustion = SPOF** | **red-team O9** | **Selection is a cheap local computation (never an LLM call); synchronous per-tick fail-over to `conductor_fallback` + alert; fail-open-to-claude is non-circular** |
| **F20** | **Verdict-string injection via the judged diff** | **red-team L1** | **Structured verdict file outside the diff; tamper inside diff ⇒ forced FAIL** |
| **F21** | **Tests-pass-but-wrong / self-locking green tests** | **red-team L2; no coverage floor** | **Test-quality eligibility; ≥1 literal-expected assertion; split impl/test authorship; full-diff security scan in Gate** |
| **F22** | **`should_run=false` skip = no logic audit, misread as neutral** | **red-team L3** | **`skipped` = unverified (never +); Gate criteria-lint on `agent:*` PRs** |
| **F23** | **Diff truncation hides regression past file #50/20k lines** | **red-team L4** | **LLM-independent full-diff security scan in Gate; truncation caps the judge at `concerns`** |
| **F24** | **Autofix launders a logic-wrong PR to green** | **red-team L7** | **Autofix can't touch tests/assertions on cheap tier; attempts charged as quality cost** |
| **F25** | **Economics inert at launch (cost_usd null; join doesn't exist)** | **red-team G1/A** | **Null-safe modeled-cost fallback w/ `cost_source` flag; P2 blocked until ≥N `observed` cells; build the (agent×tier)×verdict join in P1 shadow** |
| **F26** | **Low-value hard task ratchets onto premium resources** | **red-team G2** | **`task_value ≥ threshold` gate on escalation; ladder tops at strongest-worker→human, never the seat** |
| **F27** | **Cap-cliff discontinuity → herd-shed onto flaky overflow** | **red-team E6** | **Linear cap taper over 48h; global re-route rate limiter; sequence `agy` after 2026-06-18** |
| **F28** | **Cheap routing summons expensive cross-family judging** | **red-team E7** | **Judge cost charged into worker `expected_$`; deterministic Gate-only gating on trivial/high-coverage paths** |
| **F29** | **EWMA lag contradicts "propagates in days"** | **red-team G6** | **Split half-lives: cost/flag 14–21d; quality_rank 3–5d + event-reset on `quality_leader` edit / cliff** |
| **F30** | **Account contention (opener+closer+interactive share a seat)** | **red-team E3** | **Capacity keyed per-account under one account lock; `reserve_for_interactive`; `actor`-tagged rows** |
| **F31** | **Rollback not "delete a file"** | **red-team O13** | **Rollback = `off` all pool agents + `launchctl unload` list; mutex code backward-compatible during rollback** |

---

## 11. Phased Rollout (concrete enough to start P0)

Each phase is independently valuable and reversible. Per MEMORY `feedback_verify_dont_wait`, each is driven to **end-to-end verification in-session** — never "the next cron tick will validate." Attach a stall-watcher to long babysat runs (MEMORY `feedback_monitor_long_runs`).

**P-1 — Decide the economics ceiling and the brain's home (gate the whole project — red-team E1, O2/D1).**
- Compute `realizable_savings_ceiling = monthly_paygo_spend + monthly_claude_API_remote_spend`. If small, **cap the project at P0+P1** and do not build the learner/babysitter.
- Confirm Python is available in the lane context; commit to **one brain in Python** (`router.py`), called by both dispatch entry points. Resolve Open-Q5 (extend `llm_slots.json` to cover cursor/gemini, or keep their capacity in the local ledger only) — **decision: local ledger is the single home for *capacity*; `llm_slots.json` stays the home for *verifier model-selection slots*; document the boundary to avoid drift.**
- *Verify:* the ceiling number exists and is written down; `python3 router.py --selftest` runs on the Mac.

**P0 — Static router + consumption ledger + observability (pure observability + a 3-row table; zero routing risk).**
- Build `capacity-ledger.ndjson` + the **read-time** `capacity.json` reducer; account-level lock; `actor` tagging; per-agent `window_shape`; scrape-parsers for **Codex + Cursor**; 429-shed-until-reset for Claude/Gemini; **real `spend_usd` row for Aider**.
- Add `cursor`/`gemini`/`aider` to `registry.yml` with a `capacity` block (net-new) and a **free-disk floor** in `checkPrerequisites`.
- Router = today's static lanes + the **3-row tier table + hard capacity gate (4-state enum) only** — no score, no weights.
- Emit the **per-tick decision trace** (§9) and the **meta-cost line item** (Conductor token spend).
- **Mutex re-key to (lane,agent,target)** and **relay-reads-`routing-decision.json`** land here (they are prerequisites for *any* multi-agent dispatch — O1/O2).
- *Reversible:* `off-router` + `launchctl unload` list → today. *Verify (in-session):* run a week in shadow; a forced `agent:rate-limited` flips the **account** to `shed` until reset; a forced low-disk blocks dispatch; the decision trace explains a skipped tick; **a forced meta-cost spike fires the alert** (G7 detector exists before any cheap volume).

**P1 — Verified-success join + LangSmith/verifier feedback (advisory / shadow).**
- Build the **net-new** (agent×tier)×verdict join across verifier-metrics + LangSmith + ledger; emit `cost_per_verified_success[agent][tier]` with `cost_source` flags. Consume verifier `verdict`/`chain_depth` + autofix `attempts` as **read-only** counters; **`skipped`/`concerns`/`error`/parse-fail = unverified.**
- Router still runs the static table; emit the decision it *would* make under economics and compare.
- *Reversible:* stop reading the join → P0. *Verify:* a deliberately bad cheap-agent run raises its `chain_depth`/flag and the shadow decision down-weights it; a `should_run=false` PR is recorded `unverified`, not neutral; a grep-injection attempt (`Verdict: PASS` in a diff) is caught by the structured-verdict + tamper check.

**P2 — Harden Gate, then flip cheap-tier dispatch on (first real routing change, scoped to safe paths).**
- **First** land the §8 Gate hardening: full-diff security scan, test-quality eligibility, criteria-lint, structured verdict file, fail-closed cross-family rule, autofix test-edit ban. *These gate the flip — P2 dispatch must not land before them.*
- Then turn on cheap-tier dispatch (**Aider/Codestral, Cursor**) **ONLY on high-verification-coverage paths**, with hard cost caps + cooldown + the cross-family-judge precondition. Turn on `w_c`/`w_pen` **only after ≥N `observed` cost cells exist** (G1); until then they stay off and the table rules.
- *Reversible:* zero the economics weights / `off-router` → P1; the coverage gate confines any regression to safe paths. *Verify:* watch cost-per-**verified**-success; confirm a cheap-tier miss is caught **pre-merge** by Gate (security scan / test-quality), not merged; confirm judge cost shows up in the cheap agent's `expected_$`.

**P3 — Optional: score/EWMA, auto-rotation, `agy`/overflow (flakiest + least-valuable last; only if P-1 ceiling justifies it).**
- Only if the P0–P2 decision trace shows the static table making a *named* wrong call: add the continuous score + EWMA counters (split half-lives, min-sample on verified obs, clamps). Reconsider auto-rotation vs. the one-line manual seat edit. Add **Aider as first overflow** (pay-go, no babysitting); reach for **Gemini/`agy` only if Aider's cap is also blown**, and **only after the 2026-06-18 cliff is absorbed** (E6).
- Build the `agy` babysitter (`gemini-lane.sh`: PTY + LaunchAgent keychain + process-group kill + PGID file + side-effect/attribution outcome), `quarantined:true`, overflow-only; extend the reaper to cover it.
- *Reversible:* remove the `conductor`/score config → static seat + table; `lane-agents.sh off gemini` → no overflow. *Verify (per `feedback_verify_dont_wait` + `feedback_monitor_long_runs`):* drive one full `agy` dispatch in-session — confirm empty-stdout-but-committed scores `touched`/`verified:false` (not a fake `advance`), a force-killed CLI's process group is reaped and self-releases the mutex without halting the fleet, a forced seat-exhaustion fails over **synchronously** + alerts, and a slow live worker is **not** force-cleared (heartbeat works).

---

## 12. Open Questions & Rejected Red-Team Items

**Open questions (carried, with current leanings):**
1. **`quality_rank` proxy for the *seat* vs. for *coding*.** Seat selection wants planning/routing quality; the proxy is fleet verified-success. P3 should measure shadow would-have-routed vs. actually-ran agreement before trusting any auto-rotation. Until then, the seat is a manual edit.
2. **`task_class` taxonomy granularity (Open-Q2).** P0–P2 deliberately key counters on the **3 difficulty tiers only** (volume can't fill a 5-class × N-agent grid). Revisit only if tier-only demonstrably loses signal in the trace.
3. **Cross-family judge under capacity pressure (Open-Q3).** Resolved to fail-**closed** for cheap tier (§8/G3): prefer cross-family; if unavailable, route coding to a family whose judge *is* available; never proceed same-family; never silently degrade.
4. **Calibrating unreadable caps.** Resolved by *not* building a calibrator (§4.3): 429-shed is authoritative; we accept conservative under-use rather than a multi-week EWMA. A deliberate near-ceiling probe is explicitly **not** worth its cost at this volume.
5. **`llm_slots.json` vs. local ledger (Open-Q5).** Resolved in P-1: local ledger owns *capacity*; `llm_slots.json` owns *verifier model-selection*; the boundary is documented to prevent drift.
6. **Where the brain runs (Open-Q6).** Resolved in P-1: one Python module on the Mac, both entry points call it. No two-language routing logic.

**Rejected red-team items (with why):**
- **"Cut Gemini/`agy` entirely" (over-engineering lens).** *Partially accepted, not fully.* `agy` is deferred to P3, sequenced post-cliff, overflow-only, behind Aider — but kept as a *designed* (not built) backstop, because the brief names a flat-rate-exhaustion case the user explicitly wants overflow for. Building it is gated on actually hitting Aider-cap-blown; we do not pre-build the PTY babysitter. (This honors the cut without discarding a stated requirement.)
- **The draft's own "self-escalate to the orchestrator seat" rung.** *Rejected (deleted).* Red-team C2/G2 are correct that this turns the cheap seat into the most expensive coder on the worst tasks and can drain the seat it protects. The ladder tops at strongest-worker → human. This is a deliberate removal of a draft feature, recorded here so it isn't re-added.
- **"Keep ε-exploration as the minimal bandit move."** *Rejected for now.* At this volume it is net-negative (C5/E8/G8); reintroduce only at P3 if the trace shows stale-winner lock-in, and only gated on the fast quality signal + `floor+margin`.
- **"Extend `llm_slots.json` to be the single home for all agent capacity."** *Rejected.* It models verifier model-selection slots; conflating capacity there couples two concerns and risks the exact drift Open-Q5 warns about. Two documented homes (capacity = ledger; model-slots = `llm_slots.json`) is the simpler invariant.

---

**Net:** this is, honestly counted, **~9 net-new components** — but the *early phases* deliberately build only a handful: a read-time capacity ledger (one model per agent, keyed per-account), a 3-row tier table, a per-tick decision trace, the corrected mutex/relay plumbing, and the deterministic pre-merge Gate hardening that makes cheap routing *actually* safe. The score, EWMA counters, auto-rotation, ε-exploration, and the `agy` babysitter are **deferred or cut** until the decision trace earns them. Hold the four load-bearing invariants and resist everything else: **the only real pre-merge gate is Gate CI, so harden it before turning up cheap volume; the scorecard credits verified success only; capacity has one model per agent keyed on account, with 429-shed authoritative; and the meta-system has a measured savings tripwire that auto-disables it if it ever starts eating the savings.** If it grows past that, it has become the F9 failure it exists to prevent.