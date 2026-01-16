# Keepalive Observability Contract (Goals & Plumbing Update)

**Status:** Canonical reference for keepalive behavior and on‑run observability  
**Scope:** PR‑meta workflow(s), Orchestrator/Worker workflow, Branch‑Sync module (Codex CLI keepalive)  
**Non‑goals:** Changes to acceptance‑criteria content, agent prompts, or moderation policy

> **Applicability:** This contract applies to the **Codex CLI keepalive** implementation. The legacy UI connector‑bot flow is documented in [`Keepalive_Approaches.md`](Keepalive_Approaches.md).

---

## 1) Purpose

Keepalive must iteratively nudge a PR toward acceptance by:
1) accepting a **human activation** (`@agent`) → **dispatch** an agent round after **Gate** success;
2) posting a **round instruction** and running a **worker** to process outputs;
3) **branch‑syncing** external outputs back to the PR;
4) repeating until **acceptance criteria** are satisfied, then terminating.

This document makes the **decision points observable** and **unskippable**: anyone can open the Checks page and see exactly why a round did or didn’t run, without private logs.

---

## 2) Actors & Signals

- **PR‑meta** — decides whether to dispatch a round.
  - **Lane A:** `issue_comment.created` (human @agent)
  - **Lane B:** `workflow_run` of **Gate** (replay activation once Gate succeeds)

- **Orchestrator** — posts the **instruction** (as `stranske`) and coordinates worker/branch‑sync.

- **Worker** — executes the round; may **execute** or **skip** based on new instruction & head.

- **Branch‑Sync** — lands agent output into the PR head with:
  - `update-branch` → `create-pr + auto-merge` → `escalate sync-required`

- **Connector** — external agent; moderation workflow may delete connector chatter.

**Labels (control plane)**  
- `agents:keepalive` — enable keepalive on this PR  
- `agents:activated` — set (auto) after first human activation  
- `agents:max-runs:X` — run‑cap override (default 1; clamp 1..5)

---

## 3) Required Markers & Instruction Shape

Every **keepalive instruction** comment MUST include (top of body):
<!-- codex-keepalive-marker --> <!-- codex-keepalive-round: <N> --> <!-- codex-keepalive-trace: <opaque-trace-id> -->

Followed by:

- `@<agent>` (e.g., `@codex`)  
- **Scope**, **Tasks**, **Acceptance Criteria** (agent‑consumable)  
- *(Optional short “Execution info”)* base/head/PR metadata  
- **MUST NOT** include long status bundles (Latest Runs, coverage, etc.)

---

## 4) Reaction Lock (cross‑event idempotency)

Before any dispatch, PR‑meta adds 🚀 to the **activation comment** (the human @agent comment for first activation; the instruction comment for subsequent rounds). If already present (HTTP 409), the lane **does not** dispatch and reports `reason=lock-held`.

---

## 5) Run‑Cap Definition (dispatch edge)

At the **dispatch edge** PR‑meta computes:

- `active` = number of **Agents 70 Orchestrator** runs for **this PR** in **{queued, in_progress}**
- `cap` = from label `agents:max-runs:X` (default 2; clamp 1..5)

If `active ≥ cap` ⇒ **do not** dispatch; report `reason=cap-reached`.

> Implementation note: filter by orchestrator workflow name/id and PR discriminator (e.g., PR number embedded in orchestrator `concurrency.group`).

---

## 6) Mandatory One‑Line Summaries (Summary tab only)

**PR‑meta (both lanes) — exactly one line per run**

DISPATCH: ok=<true|false> path=<comment|gate> reason=<ok|missing-label|no-human-activation|gate-pending|gate-failed|cap-reached|no-linked-pr|no-activation-found|lock-held|instruction-empty> pr=#<PR_NUMBER> activation=<COMMENT_ID|none> agent=<ALIAS> head=<SHA7> cap=<CAP> active=<ACTIVE> trace=<TRACE|->


**Orchestrator — three lines per run**

INSTRUCTION: ok=<true|false> author=<stranske|stranske-automation-bot> comment=<COMMENT_ID|none> ack=<ok|fail> head=<SHA7> trace=<TRACE>
WORKER: action=<execute|skip> reason=<new-instruction|no-new-instruction-and-head-unchanged|cap-reached|blocked> pr=#<PR_NUMBER> head=<SHA7> instr=<COMMENT_ID|none> trace=<TRACE>
SYNC: action=<update-branch|create-pr|escalate|skip> head_changed=<true|false> trace=<TRACE>


**Rules**
- Always print (even when skipping/failing).
- Never post these to the PR; **Summary tab only**.

---

## 7) Lane Behavior (Dispatch Contract)

### Lane A — `issue_comment.created`
**Preconditions:** `agents:keepalive` present; human @agent activation; Gate may be pending.

1) If Gate **not** success → `DISPATCH ok=false path=comment reason=gate-pending …`
2) If Gate success → evaluate run‑cap, markers, author allowlist, instruction extraction.
3) If everything OK → **dispatch** orchestrator and print `ok=true`.

### Lane B — `workflow_run` (Gate)
**Preconditions:** Gate concluded success.

1) If `activation_comment` output is empty → **fallback**:
   - resolve PR; fetch most‑recent **human** @agent activation (no hidden markers)
   - if none → `DISPATCH ok=false path=gate reason=no-activation-found …`
2) Reaction lock on `activation_comment`; 409 ⇒ `reason=lock-held`
3) Evaluate run‑cap/markers/instruction; then **dispatch** or report precise reason.

**Fail‑fast:** If instruction extraction empty when dispatch would occur ⇒ `instruction-empty` and **fail** the job.

---

## 8) Orchestrator Contract

**Author Invariant (recommended hardening)**  
If `ACTIONS_BOT_PAT` is configured but the post would use `SERVICE_BOT_PAT`, **fail** the instruction step with:

INSTRUCTION: ok=false reason=wrong-author token=<SERVICE_BOT_PAT> head=<SHA7> trace=<TRACE>


**Instruction Post & ACK**  
On success post + ACK:

INSTRUCTION: ok=true author=stranske comment=<COMMENT_ID> ack=<ok|fail> head=<SHA7> trace=<TRACE>


**Worker Guard**  
Skip **only if** both:
- no **new** instruction since last processed, **and**
- head SHA unchanged.

Otherwise **execute**. Always print `WORKER:` line.

**Branch‑Sync Gate**  
If worker signals “done” but head unchanged:
1) try `update-branch` (poll head),
2) else `create-pr + auto-merge` (poll head),
3) else `escalate` + label `agents:sync-required`.

Always print `SYNC:` line.

---

## 9) Failure Reasons (canonical list)

- `missing-label` — `agents:keepalive` absent  
- `no-human-activation` — comment didn’t match human @agent activation  
- `gate-pending` / `gate-failed` — Gate not success  
- `cap-reached` — run‑cap enforced at dispatch edge  
- `no-linked-pr` — workflow_run lacked PR and no PR could be resolved  
- `no-activation-found` — Gate lane fallback couldn’t find human activation  
- `lock-held` — reaction lock already present on activation comment  
- `markers-missing` — required hidden markers not present (where expected)  
- `instruction-empty` — instruction segment extraction failed (fail job)  
- `wrong-author` — orchestrator would post as bot when human PAT required  
- `blocked` — worker blocked due to policy (rare; document if introduced)

---

## 10) Test Matrix (minimum)

| Scenario | Expected summaries (key fields) |
|---|---|
| Human @agent before Gate | `DISPATCH ok=false path=comment reason=gate-pending pr=#…` |
| Gate success with prior activation | `DISPATCH ok=true path=gate …` then Orchestrator prints `INSTRUCTION ok=true author=stranske …` |
| Cap reached | `DISPATCH ok=false reason=cap-reached cap=2 active=2` |
| No activation found on Gate | `DISPATCH ok=false path=gate reason=no-activation-found` |
| Instruction empty (parser/regression) | `DISPATCH ok=false reason=instruction-empty` **and job fails** |
| Worker skip (no new instruction & head unchanged) | `WORKER action=skip reason=no-new-instruction-and-head-unchanged` |
| Branch‑sync escalate | `SYNC action=escalate head_changed=false` |

---

## 11) Minimal Implementation Checklist (step insertion points)

> Names below match typical jobs; adapt IDs/paths to your repo.

**PR‑meta (`.github/workflows/agents-pr-meta-v4.yml`)**

- **Comment lane** (`on: issue_comment`):
  - _Before dispatch_: run‑cap check; reaction lock; instruction extraction guard.
  - _After decision_: print `DISPATCH:` (always).

- **Gate lane** (`on: workflow_run` of Gate):
  - _Early_: resolve PR; if `activation_comment` missing → fallback fetch; reaction lock.
  - _Before dispatch_: run‑cap; instruction extraction guard.
  - _After decision_: print `DISPATCH:` (always).

**Orchestrator (`.github/workflows/agents-70-orchestrator.yml`)**

- _After token selection_: author invariant (optional hard fail).
- _After post + ACK_: print `INSTRUCTION:`.
- _Worker pre‑decision_: print `WORKER:` with execute/skip reason.
- _After branch‑sync_: print `SYNC:`.

All summary lines should be appended using:
```bash
echo "…SUMMARY LINE…" >> "$GITHUB_STEP_SUMMARY"

## 12) Example Summary Lines

DISPATCH: ok=true path=gate reason=ok pr=#3541 activation=2012345678 agent=codex head=abc1234 cap=2 active=1 trace=ka-3541-r3
INSTRUCTION: ok=true author=stranske comment=2012348901 ack=ok head=def5678 trace=ka-3541-r3
WORKER: action=execute reason=new-instruction pr=#3541 head=def5678 instr=2012348901 trace=ka-3541-r3
SYNC: action=update-branch head_changed=true trace=ka-3541-r3

## 13) Rollout Notes

- Land PR‑meta changes first; they add visibility immediately and do not affect posting behavior.

- Then land Orchestrator summaries and (optionally) author invariant.

- Validate with the Test Matrix; capture Summary screenshots in the PR description.

## 14) FAQ

Q: Why “Summary tab” and not PR comments?
A: We avoid PR noise; the Summary tab is sufficient for reviewers and agents.

Q: Do we remove connector moderation?
A: No. Keep moderation; the observability contract reduces reliance on private logs and races, not moderation.

Q: Does this change run‑cap, Gate, or acceptance content?
A: No. It only hardens the activation→dispatch hop and makes decisions auditable.


