# Verifier Judge Evaluation: candidate judges, third-judge tie-breaks and failover

This guide covers how a new model or agent earns a place among the pull-request verifier's judges,
and how to decide, from evidence, whether a **third judge** (to break ties) or a **backup judge** (for
when one token pool runs out) is worth enabling. It extends the existing selection pipeline
(`config/model_selection_policy.json`, `tools/run_model_eval_cli_screen.py`,
`tools/run_model_eval_api_confirm.py`, `tools/prepare_model_promotion.py`); it does not replace it.

## 1. Two different things are called a "verify agent"

| | Keepalive acceptance verification | PR verifier judge |
| --- | --- | --- |
| What runs | An **agent round** (`verify-acceptance`, `fix-verification-gaps`) on a CLI runner such as `run-claude` | An **LLM judgement call** through `scripts/langchain/pr_verifier.py` |
| Independence rule | Must not run on the implementing agent. `resolveIndependentVerifier` in `keepalive_loop.js` (Workflows#4041) picks the verifier from the repository's `verifier_agent`, the agent's registry `independent_verifier`, the historical Codex ⇄ Claude pair, or the first other usable agent | Compare mode uses **two** slots (`resolve_slots()[:2]`), and a third slot exists in `config/llm_slots.json` |
| Cursor and Muse | Eligible now (their CLI runners exist; Cursor verifies with Claude, Muse with Codex by default) | Candidates only; see sections 3 and 6 |
| Contract | Agent output, judged by the loop | **Strict**: PASS needs complete exact-slot coverage, a configured FAIL always survives, a missing judge cannot be replaced by an available fallback, and the two slots must be different provider families |

Everything below concerns the second column.

## 2. The quality gates a judge must clear

The policy's `provisional_stage` (an 8-case screen) and `approval_stage` (75 adjudicated cases) already
define the gates, with false PASS as the highest-cost error:

- Screen: at most 0 false PASS, 0 schema errors, at least 50% PASS recall, no accuracy loss versus the
  incumbent, no regression in either verdict class.
- Approval (retired 2026-10-30, owner decision): it never approved a judge; the bounds were
  loosened to false PASS 0.10 and false FAIL 0.20 on 2026-10-18 and still required a perfect run.
  A judge now changes by the owner's decision after a corpus trial (`VERIFIER_SHADOW.md`,
  "Trialling a new candidate"); the bounds are reported as information only.

A screen result is **exploratory evidence**. It can justify the capped API confirmation, never a
promotion. Zero false PASS on 4 NON_PASS cases only bounds the false-PASS rate below about 0.49; the
approval gate needs zero errors on roughly 70 or more NON_PASS cases to reach 0.05
(`tools/analyze_judge_ensemble.cases_needed_for_bound`).

## 3. Screening a candidate: `tools/run_judge_backend_screen.py`

One tool, one set of cases, one production prompt, the same thresholds, several backends:

| Backend | What it is | Billing / evidence class |
| --- | --- | --- |
| `claude-cli` | Claude Code CLI with every tool disabled | Subscription login; exploratory CLI |
| `muse-cli` | Muse CLI (`--preset empty`, contributor mode off, no session log) | Subscription login; exploratory CLI. The CLI reports no token usage, so none is invented |
| `cursor-cli` | Cursor CLI in read-only `ask` mode | Cursor account; exploratory CLI; reports token usage |
| `agy-cli` | Antigravity CLI, `--mode plan`, explicit model, scratch workspace, empty response is an error | Local use only; exploratory CLI |
| `muse-api` | Meta Model API (OpenAI-compatible, `https://api.meta.ai/v1`) with its **own** pay-as-you-go key, `MUSE_API_KEY` | Observed API usage; **a different credential from the subscription key** stored as `META_API_KEY` |

Safeguards built in (each pinned by a test):

- Contributor-tier models are refused: that tier may train on prompts, and verifier prompts contain
  PR diffs.
- Each backend receives only the variables it needs; GitHub and unrelated credentials are removed,
  and the subscription CLIs never see the API key.
- Keys never appear in errors or output. A rate limit, authentication failure or tool activity
  stops *that judge* and is recorded; it never becomes a verdict.
- An invalid or empty result counts as a failure of the judge, and can never be a PASS.

```bash
# incumbent baseline (existing Codex screen), then candidates on the same cases
python -m tools.run_model_eval_cli_screen --models gpt-6.1-sol,gpt-6-luna --output codex-screen.json
MUSE_API_KEY=... CURSOR_API_KEY=... python -m tools.run_judge_backend_screen \
  --judges claude-cli,muse-cli,cursor-cli,agy-cli,muse-api \
  --muse-api-price-in <USD/M> --muse-api-price-out <USD/M> --output judge-screen.json
```

Muse API pricing, verified from Meta's own pricing page on 2026-10-18
(<https://dev.meta.ai/docs/pricing-rate-limits>): `muse-spark-1.3` and `muse-spark-1.2`, standard mode,
cost 1.25 USD per million input tokens, 4.25 per million output tokens and 0.15 per million cached input
tokens (rate limit 3,000 requests and 4,000,000 tokens per minute). The `-contributor` variants are cheaper
because Meta may train on the prompts; they are refused here. Pass the two prices to the screen
(`--muse-api-price-in 1.25 --muse-api-price-out 4.25`); the modelled cost is then labelled with the page it
came from. The price is **not** entered in `config/model_registry.json`: the registry's native-capacity
reader accepts only the openai, anthropic and github-models providers, so a `meta` row fails 30 existing
registry tests until provider support exists (section 6 lists it as a precondition).

## 4. Deciding on a third judge or a backup: `tools/analyze_judge_ensemble.py`

Feed it one or more screen outputs. It reports, from real per-case verdicts:

- per judge: correct, false PASS, invalid results, the false-PASS Wilson bound, and the specific
  **blockers to PASS authority**;
- per pair: agreement, cases both get wrong, and the result of the production strict-AND rule;
- **tie-break value**: of the cases where two judges disagree, how often the third is right, and the
  2-of-3 outcome (needs at least 5 disagreements to be estimable at all);
- **failover value**: how a backup performs standing alone when a primary is unavailable.

It enables nothing. Its recommendation is "not enabled" until at least three judges (for tie-break)
or two (for failover) each meet the PASS-authority gates, and "insufficient evidence" when the
sample cannot support a claim.

## 5. What a tie-break or failover implementation must preserve

The strict compare contract exists because a false PASS is the costliest error. Both options are
therefore **opt-in policy with earned authority**, not a relaxation:

1. **A FAIL always survives.** No third or backup judge can turn any judge's FAIL into a PASS.
2. **Only approved judges vote.** A judge may count toward PASS only after it has cleared the
   approval-stage gates (`prepare_model_promotion` already models approval and rollback).
3. **Two provider families.** A substituted judge must keep the two-family requirement
   (`expanded_comparison_verdict` returns CONCERNS otherwise).
4. **Substitution is recorded, never silent.** The result names the slot that was replaced and why
   (quota exhaustion, authentication), and the verdict is marked degraded.
5. **Exhaustion is distinguished from disagreement.** Failover triggers on HTTP 429 / quota /
   credential errors; tie-break triggers only on a PASS-versus-CONCERNS split between two valid
   judges. Neither triggers on a malformed result.
6. **Rollback exists.** A false PASS attributable to a substituted or tie-breaking judge removes its
   authority, using the same rollback path as model promotion.

Suggested shape (not built): an `ensemble` block in `config/llm_slots.json` with
`mode: off | tie_break | failover`, the ordered judge list, and `authority: approved-only`. The
default stays `off`.

## 6. Preconditions for a production judge slot

A candidate that clears the screen still needs, before it can appear in `config/llm_slots.json`:

- a provider class in `tools/llm_provider.py` and the provider name in `tools/llm_registry.py`
  (`normalize_provider`, native capacity facts), plus `scripts/langchain/pr_verifier.py` client
  construction, including semantic mode, which requires two native judge slots;
- a verified price and a `current`, non-blocked entry in `config/model_registry.json`;
- the capped API confirmation (at most 8 cases, 2 models, $5) against the incumbent, then the
  human-approved provisional selection, then the approval-stage corpus (75 cases).

Cursor has no model API, only a CLI, so it can be screened and can verify in keepalive rounds, but it
cannot become a production API judge slot unless a CLI-judge harness is built and validated as a
production path; its cost cannot be treated as observed spend.

## 7. First measurement

(See the evidence directory for the raw files; the table below is generated from them.)

Eight adjudicated cases (4 PASS, 4 NON_PASS) from the existing screen corpus, the production verifier
prompt, one run per judge, 2026-10-17. Raw rows: `docs/evidence/judge-screen-20261017/`.

**Evidence class: exploratory CLI/API screen, not production use.** The harness differs from the production
verifier (CLI wrappers add their own system prompts; the Claude row is the Claude Code CLI, not the
production Anthropic judge slot). Token counts are as reported by each backend; Muse CLI reports none.

| Judge | Harness | Correct | False PASS | False FAIL | Invalid | Tool activity | Median latency | Tokens in / out |
|---|---|---:|---:|---:|---:|---:|---:|---|
| gpt-5.6-terra | Codex CLI (incumbent baseline) | 6/8 | 0 | 2 | 0 | 0 | 9s | 111,388 / 2,273 |
| gpt-6-luna | Codex CLI | 5/8 | 1 | 2 | 0 | 0 | 5s | 117,974 / 1,479 |
| claude-cli | Claude Code CLI, tools off (served claude-opus-5-5) | 4/8 | 2 | 2 | 0 | 0 | 16s | 58,010 / 10,308 |
| cursor-cli | Cursor CLI, ask mode, default model | 6/8 | 2 | 0 | 0 | 0 | 17s | 98,767 / 16,288 |
| muse-api | Meta Model API muse-spark-1.2, separate key | 6/8 | 2 | 0 | 0 | 0 | 29s | 21,861 / 20,339 |
| muse-cli | Muse CLI muse-wonder-1.0, subscription | 3/8 | 2 | 2 | 1 | 1 | 21s | not reported |
| agy-cli | agy gemini-4-argon-medium, plan mode | 4/8 | 2 | 0 | 2 | 0 | 18s | 127,453 / 9,352 |

The screen table counts false FAIL only for schema-valid verdicts; the historical ensemble table fails closed on invalid results. Historical ordering and conflicting Muse observations are documented in `../evidence/judge-screen-20261017/PROVENANCE.md`; that aggregate must not qualify a judge for authority. The corrected analyzer requires all approval-stage gates, category evidence and a paired recorded incumbent, and refuses conflicting observations or corpus/prompt identities.

Reading the table:

- Only the incumbent (`gpt-5.6-terra`) had zero false PASS, and even that bounds the false-PASS rate only
  below about 0.49 on 4 NON_PASS cases. No judge qualifies for PASS authority on this evidence.
- Cursor and the Muse API each scored 6/8 with no false FAIL but 2 false PASS: they are plausible
  candidates for the capped API confirmation, not for a vote.
- Muse CLI and agy had invalid or tool-using results; their CLI wrappers are poor judge harnesses today.
- Cursor has no model API, so only its CLI can be screened.

### Ensemble analysis (generated)

8 cases (4 NON_PASS). **Nothing is enabled by this report.**

| Judge | Correct | False PASS | False-PASS upper bound | Invalid | PASS authority |
|---|---:|---:|---:|---:|---|
| agy-cli | 4/8 | 2 | 0.85 | 2 | no: 2 false PASS observed; 2 invalid result(s); false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| claude-cli | 4/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| cursor-cli | 6/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| gpt-5.6-terra | 6/8 | 0 | 0.4899 | 0 | no: false-PASS upper bound 0.4899 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| gpt-6-luna | 5/8 | 1 | 0.6994 | 0 | no: 1 false PASS observed; false-PASS upper bound 0.6994 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| muse-api | 6/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| muse-cli | 3/8 | 2 | 0.85 | 1 | no: 2 false PASS observed; 1 invalid result(s); false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |

### Pairs (production strict-AND contract)

| Pair | Agreement | Both wrong | False PASS | False FAIL |
|---|---:|---:|---:|---:|
| agy-cli + claude-cli | 0.75 | 3 | 2 | 3 |
| agy-cli + cursor-cli | 0.5 | 1 | 1 | 2 |
| agy-cli + gpt-5.6-terra | 0.5 | 1 | 0 | 3 |
| agy-cli + gpt-6-luna | 0.625 | 2 | 1 | 3 |
| agy-cli + muse-api | 0.75 | 2 | 2 | 2 |
| agy-cli + muse-cli | 0.875 | 4 | 2 | 3 |
| claude-cli + cursor-cli | 0.5 | 1 | 1 | 2 |
| claude-cli + gpt-5.6-terra | 0.75 | 2 | 0 | 2 |
| claude-cli + gpt-6-luna | 0.875 | 3 | 1 | 2 |
| claude-cli + muse-api | 0.75 | 2 | 2 | 2 |
| claude-cli + muse-cli | 0.875 | 4 | 2 | 3 |
| cursor-cli + gpt-5.6-terra | 0.5 | 0 | 0 | 2 |
| cursor-cli + gpt-6-luna | 0.375 | 0 | 0 | 2 |
| cursor-cli + muse-api | 0.75 | 1 | 1 | 0 |
| cursor-cli + muse-cli | 0.375 | 1 | 1 | 3 |
| gpt-5.6-terra + gpt-6-luna | 0.875 | 2 | 0 | 2 |
| gpt-5.6-terra + muse-api | 0.5 | 0 | 0 | 2 |
| gpt-5.6-terra + muse-cli | 0.625 | 2 | 0 | 3 |
| gpt-6-luna + muse-api | 0.625 | 1 | 1 | 2 |
| gpt-6-luna + muse-cli | 0.75 | 3 | 1 | 3 |
| muse-api + muse-cli | 0.625 | 2 | 2 | 3 |

**Tie-break:** not enabled: 0 of the judges meet the PASS-authority gates (three are needed so that every vote carries authority)
**Failover:** not enabled: 0 judge(s) meet the PASS-authority gates; a backup must earn the same authority as the judge it replaces
**Sample:** 4 NON_PASS case(s) observed; 73 are needed with zero false PASS to bound the false-PASS rate at 0.05. Small-sample results cannot enable either option.


## 7b. Current-prompt comparison, Muse tiers and the contributor policy (2026-10-18)

**Prompt version.** The production verifier prompt changed between the first screens (2026-10-17) and
these (prompt fingerprint `5d53daf386…`), and it adds a verdict, `UNVERIFIABLE_INPUT` ("the input is not
enough to judge"). The analyzer refuses to mix prompt versions, so every judge below was re-run on the
current prompt; the 2026-10-17 tables above are historical. `UNVERIFIABLE_INPUT` counts as non-PASS,
so on a PASS case it is a false FAIL (cautious), never a false PASS.

Same 8 cases (4 PASS, 4 NON_PASS), current prompt, evidence in `docs/evidence/judge-screen-20261017/`:

| Judge | Correct | False PASS | Cost for the 8 cases | Usage class |
| --- | ---: | ---: | --- | --- |
| gpt-5.6-terra (incumbent, Codex CLI screen) | 6/8 | 0 | 0.0437 USD | CLI screen |
| gpt-6-luna (Codex CLI screen) | 6/8 | 0 | 0.0021 USD | CLI screen |
| Cursor CLI | 5/8 | 2 | not reported | exploratory CLI |
| Claude Code CLI, tools off | 4/8 | 2 | not reported | exploratory CLI |
| muse-spark-1.2 API, standard | 4/8 | 4 | about 0.11 USD | api-observed |
| muse-spark-1.2-contributor API | 6/8 | 2 | 0.0075 USD | api-observed |
| muse-spark-1.3 API, standard | 4/8 | 2 | 0.122 USD | api-observed |
| muse-spark-1.3-contributor API | 3/8 | 3 | 0.0064 USD | api-observed |
| muse-wonder-1.0 API | 4/8 | 2 | 0.498 USD | api-observed |
| agy | not re-run | | | seat quota exhausted until the weekly reset |

Only the two Codex-served GPT judges had no false PASS. Every other judge passed the same two
`follow-up-required` cases that the GPT judges rejected, and no judge, including those two, meets the
PASS-authority gates (four NON_PASS cases bound the false-PASS rate only below about 0.49; 73 are
needed for 0.05). Tie-break and failover therefore stay not enabled (`analyze_judge_ensemble`). The
1.2 versus 1.3 and standard versus contributor differences are within what eight cases can show;
the same model changed from 6/8 to 4/8 with the prompt change alone.

### Muse prices (Meta's pricing page, read 2026-10-18)

Per million tokens (<https://dev.meta.ai/docs/pricing-rate-limits>):

| Model | Cached input | Input | Output | Mode |
| --- | ---: | ---: | ---: | --- |
| muse-spark-1.3, 1.2, 1.1 | 0.15 | 1.25 | 4.25 | standard |
| muse-spark-1.3-contributor, 1.2-contributor | 0.002 | 0.10 | 0.20 | contributor (trains) |
| muse-wonder-1.0 | 0.20 | 4.00 | 20.00 | standard only |

Contributor mode is 12.5 times cheaper on input and 21 times on output; measured on these eight
prompts the 1.2 model cost 0.0075 USD against 0.11 USD standard. Contributor grants Meta permission to
use "the prompts, code, files, and context you send, plus the model responses you get back" to train
future models; the page states no opt-out or retention policy for the API. Wonder is the model the Muse
CLI serves; through the API it costs about four times Spark standard on this workload.

### Where training on the data is not a security concern, and where it is

All 17 repositories in the lane fleet are public (checked with GitHub's visibility field on
2026-10-18). A verifier prompt is built from a pushed PR: its diff, the linked issue, the CI summary.
That content is already published, so contributor-tier training adds no confidentiality exposure for it.

| Work | Contributor tier |
| --- | --- |
| Verification of a pushed PR in a public repository (diff, issue, CI summary) | Allowed once the judge has earned authority; quality, not security, is the open question |
| The judge-screen corpus (built from pushed PRs in public repositories) | Allowed |
| Experiment evaluator prompts (A/B/C/D diffs are unpushed worktree changes) | **Refused**: not yet published |
| Anything unpublished or local (audits, personal notes, local projects, the Brain), private or internal repositories, secrets or credential values, personal data | **Refused** |

The guard is mechanical: `--allow-contributor-tier` is refused unless GitHub confirms every case
repository is public and every prompt input matches the shipped immutable corpus or a published
verifier-input manifest for the named run (`require_contributor_tier_inputs`; tests pin it). An
unknown repository visibility or unverifiable prompt input counts as refusal.
Residual risks: CI logs in a public repository can still carry text a masking rule missed; a
repository that later turns private would need the flag withdrawn; and the policy cannot see what Meta
retains. These are reasons to keep the cheap tier behind the quality gates, not to refuse it.

### What this says about the verifier pool

The production keepalive pool stays Claude and Codex, with Cursor and Muse work verified by either of
them at random (Workflows#4049/#4053); a live canary on a Cursor PR logged the pick (Codex). Cursor,
Muse (API and CLI) and agy are screened here but are not in the PASS pool: on this evidence none has
earned it, and the Muse contributor tier is the cheapest way to keep measuring. Adding a judge to the
pool needs the preconditions in section 6 plus the approval corpus; the corpus is the bottleneck.

### Muse Spark 1.3 on the 2026-10-17 prompt (historical)

Meta's models page names 1.3 as the latest Muse Spark, so the API judge was screened again on the same 8
cases (`muse-spark-1-3-screen.json`): 4 of 8 correct, 2 false PASS, 0 schema errors, modelled cost
0.12 USD for 22,365 input and 22,171 output tokens (api-observed usage at the verified price). 1.2 scored 6 of
8 with 2 false PASS on the same cases at that prompt version; the current-prompt figures are in the table
above (1.3: 4 of 8, 1.2: 4 of 8). Neither qualifies for PASS authority, and the 1.2 to 1.3 change on
eight cases is a reminder of how little a screen of this size can rank.

## 8. Next steps and how each is measured

| Step | Pass number | Check date |
| --- | --- | --- |
| Grow the corpus toward 75 adjudicated cases (weekly harvest already runs) | adjudicated cases >= 75 with >= 70 NON_PASS | when the harvest reaches it |
| Re-run the screen on the larger corpus for every candidate that cleared this one | each candidate's false PASS = 0 and false-PASS bound <= 0.05 | after the corpus grows |
| Enter verified Muse API pricing | `config/model_registry.json` carries a priced `muse` entry | after Meta's price page is read |
| Decide tie-break / failover | `analyze_judge_ensemble` recommendation reads "candidate", not "not enabled" | after the above |


### CLI prompt transport qualification

Cursor receives the verifier prompt over stdin. Agy uses its installed CLI's
`--input-format stream-json --output-format stream-json` protocol: one NDJSON
user message with `message.role` and `message.content`, then EOF. Prompts never
enter argv. The local `agy --help` confirms the input/output flags, and its
installed decoder names the user message and content fields. Unit controls pin
the request and final result envelope and stop on stream tool events. This is
transport validation with fakes; no live judge call or provider quality approval
is claimed by the repair.
