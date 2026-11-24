# Keepalive Reliability Plan

**Status:** Adopt and keep current  
**Related:** `docs/keepalive/Observability_Contract.md` (required one‑line summaries)

This plan closes the remaining reliability gaps in the keepalive pipeline by removing unsafe assumptions, adding a token‑free fall‑back path, and making every decision point machine‑auditable from the Checks UI.

---

## Goals

1. **Never silently skip** a round when preconditions are met.  
2. **Make dispatch, instruction post, worker decision, and branch‑sync auditable** via one‑line job summaries (no private logs required).  
3. **Guarantee authorship & token correctness** for agent‑consumable instructions.  
4. **Deliver outputs back to the PR head** (update‑branch or create‑PR+merge), or clearly escalate.

---

## Architecture (what changes)

### A) PR‑Meta (Detector/Dispatcher)
- **Dual lanes:** `issue_comment.created` (human activation) and `workflow_run` for **Gate** (replay activation).  
- **Dispatch proof:** refuse `GITHUB_TOKEN`; require PAT; print token identity and confirm an Orchestrator run exists.  
- **Run‑cap at dispatch edge:** count orchestrator runs in **{queued, in_progress}** for *this PR*.  
- **Reaction lock:** 🚀 on the chosen activation comment **before** dispatch.  
- **Activation fallback (Gate):** if the Gate script didn’t supply `activation_comment`, fetch most‑recent *human* `@agent` comment (excluding keepalive‑authored comments with hidden markers).

### B) Orchestrator
- **Token‑free fallback:** also triggers via `workflow_run` of **Gate** (no cross‑dispatch required).  
- **PR head checkout on `workflow_run`:** use `github.event.workflow_run.pull_requests[0].head.sha`.  
- **Secrets preflight:** choose a single `WRITE_TOKEN = ACTIONS_BOT_PAT || SERVICE_BOT_PAT`; fail fast if none.  
- **Author invariant:** if the agent requires `stranske`, fail instruction step with `reason=wrong-author` when only the bot token is available.  
- **Worker fan‑out:** set `worker_max_parallel = min(cap, 5)`; default 2.  
- **Worker guard:** execute iff **new instruction** exists OR **head changed**; else skip.  
- **Branch‑sync gate:** `update-branch` → `create-pr+merge` → `escalate` (label + actionable link).

### C) Observability (must‑emit one‑liners)
- **PR‑meta:** `DISPATCH:` (and `GATE:` where applicable).  
- **Orchestrator:** `INSTRUCTION:`, `WORKER:`, `SYNC:`.  
- If a required line would be missing, **fail** the job.

> The exact formats/reasons are defined in `Observability_Contract.md`. This plan assumes that contract is already adopted.

---

## Failure Map → Fixes (authoritative)

| Stage | Unsafe assumption | Symptom | Fix (this plan) |
|---|---|---|---|
| PR‑meta → Orchestrator | Any token can dispatch | Meta “success”, no Orchestrator run | Refuse `GITHUB_TOKEN`; require PAT with Actions:write; **prove** run exists; else fail |
| Gate replay | Script must provide `activation_comment` | Gate lane “success” but no dispatch | Fallback: fetch most‑recent human `@agent` and use it; always emit `DISPATCH:` with reason |
| Event coverage | All human instructions are `issue_comment` | Review comments ignored | (Optional) Add `pull_request_review_comment` created path to detector |
| Cap | One check is enough | Swarms or starvation | Count **{queued,in_progress}** Orchestrators for this PR at the **dispatch edge** |
| Lock | Any activation will do | Double launches | Reaction lock (🚀) on **the** chosen activation id (shared across lanes) |
| Authorship | Any commenter works | Agent ignores instruction | **Author invariant**: post as `stranske` or fail (`wrong-author`) |
| Token | PATs always OK | Early token/author aborts | **Secrets preflight** selects `WRITE_TOKEN` and fails fast if none |
| Worker | “head unchanged” means skip | New instruction but skip | Skip **only** if *no new instruction* **and** head unchanged |
| Branch‑sync | Agent output lands on PR by magic | “Done” but no HEAD change | Two‑path sync; escalate with PR label + actionable link if needed |
| Visibility | “Success” means OK | Green runs that did nothing | **Mandatory** `DISPATCH/INSTRUCTION/WORKER/SYNC` lines; missing → fail |

---

## Implementation Checklist

### PR‑meta
- [ ] Reject `GITHUB_TOKEN` for dispatch; require PAT; print `TOKEN_IDENTITY` and `DISPATCH_CONFIRMED`.  
- [ ] Count cap at dispatch edge; print `cap=<active>/<cap>` in `DISPATCH:`.  
- [ ] Gate fallback: if `activation_comment` empty, fetch most‑recent *human* `@agent`.  
- [ ] Reaction lock (🚀) on activation id prior to dispatch.  
- [ ] Always print `DISPATCH:` (and `GATE:` where applicable) to `$GITHUB_STEP_SUMMARY`.  
- [ ] (Optional) Add `pull_request_review_comment` created trigger.

### Orchestrator
- [ ] Add `on: workflow_run` (Gate) trigger; checkout PR head SHA on that path.  
- [ ] Secrets preflight → `WRITE_TOKEN`; all writes use this one token.  
- [ ] Author invariant: post as `stranske` or fail with `wrong-author`.  
- [ ] `worker_max_parallel = min(cap, 5)`; default 2.  
- [ ] Mandatory `INSTRUCTION/WORKER/SYNC` lines to `$GITHUB_STEP_SUMMARY`.  
- [ ] Branch‑sync: `update-branch` → `create-pr+merge` → `escalate` (+ link) and emit `SYNC:`.

---

## Acceptance (what “done” looks like)

1. **Comment‑first scenario:** Human `@agent` before Gate → `DISPATCH path=comment reason=gate-pending`.  
2. **Gate‑success replay:** Gate completes → `DISPATCH path=gate ok=true` and **Orchestrator run appears** (or precise skip reason).  
3. **Instruction post:** `INSTRUCTION ok=true author=stranske comment=<id>`.  
4. **Worker decision:** `WORKER action=execute reason=new-instruction`.  
5. **Branch‑sync:** `SYNC action=update-branch|create-pr|escalate head_changed=<true|false>`.  
6. **Cap test (cap=2):** Third concurrent attempt prints `reason=cap-reached` and no Orchestrator starts.  
7. **Negative test:** Remove instruction segment → PR‑meta fails with `reason=instruction-empty`.

---

## Rollout

1. Land PR‑meta changes (no behavior change beyond “fail loud” + better summaries).  
2. Land Orchestrator `workflow_run` trigger, secrets preflight, author invariant, one‑liners.  
3. Land branch‑sync dual path.  
4. Validate with the Acceptance matrix and attach Summary screenshots to the test PR.

