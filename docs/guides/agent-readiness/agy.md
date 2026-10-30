# Readiness evaluation: `agy` (Antigravity CLI 1.4.0, evaluated 2026-10-17)

**Verdict: Ready for local use only.**
**Hosted CI:** not ready. The only documented headless credential is a Gemini API key, which is
direct API spend, and the subscription sign-ins need a browser and an OS keyring. Nothing here has
been tried on a clean Linux runner.
**Local use:** already running as the local lane for the Gemini agent in the Orchestrator, with
defects that were found and worked around (section 3). Supervised, workspace-guarded use only.

Evidence classes: **P** production use, **R** real trial, **F** fixture check, **W** documentation or
wiring. Unless noted, vendor-documentation statements are W.

## 1. What it is

`agy` is Google's Antigravity command-line agent. It is the successor to the Gemini CLI for
personal accounts (a secondary source reports the Gemini CLI stopped serving free, Pro and Ultra
accounts after 18 June 2026; not verified against a primary source). It is a multi-provider
router: `agy models` currently lists Gemini 4 Argon, Gemini 3.8 Flash, Claude Opus 5.5 and Sonnet
5.5, and GPT-OSS 120B, each in low/medium/high tiers (R, 2026-10-17, a non-billing server call that
also proves the local sign-in is valid).

In Workflows the existing `gemini` agent uses the older `@google/gemini-cli` with a `GEMINI_API_KEY`
secret (W). That runner is the closest precedent for how `agy` would run in CI, and it is the
API-key path in section 2, row 1.

## 2. Stage 0 questions

| # | Question | Blocker? | Hosted CI | Local | Evidence | Notes / probe |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Unattended authentication on a clean Linux runner with a repo-secret credential | **Yes** | **Possible, untested.** Documented route is a Gemini API key: set `modelProvider` to `gemini` in the CLI's `settings.json` **and** export `GEMINI_API_KEY`; the environment variable alone has no effect. `AGY_ADC_AUTH=true` with Application Default Credentials is documented for headless enterprise use. | Works: cached sign-in from the OS keychain | W (hosted), P (local) | Probe: on a clean `ubuntu-latest` container, write the settings file, export a throwaway key, run `agy models` then a one-line `-p` prompt. Startup only checks the key is non-empty, so an invalid key fails at the first conversation, not at launch. |
| 2 | What the credential bills; acceptable for unattended use | **Yes** | **Direct API spend** on the API-key route ("requests go directly to the Gemini API"; the CLI "never establishes an account session"). ADC bills the Google Cloud project. Neither draws on a Free/Pro/Ultra subscription. | The logged-in seat draws subscription or credit quota; the Orchestrator describes it as a metered seat with compute units | W | This repeats the Muse lesson: the subscription meter and the API meter are different, and only the vendor's usage ledger settles it. Probe: before/after reading of the usage page around one key-authenticated call. |
| 3 | Headless print mode with bounded runtime, machine-readable output, non-zero exit on failure | **Yes** | Present | Present, in use | W, P | `-p`/`--print`; `--output-format text|json|stream-json`; `--json-schema`; `--print-timeout` (default 5 minutes); JSON carries `status`, `duration_seconds`, `usage`. Unknown model exits non-zero. **Permission denials are soft: exit 0 plus a stderr notice**, so a run can "succeed" having been denied the shell. The Orchestrator passes `--dangerously-skip-permissions`. |
| 4 | Sandbox available, usable on Linux, or confinable by the runner | **Yes** | **Unknown.** `--sandbox` (default off) enables terminal sandbox restrictions; no Linux statement found | **No read-only mode.** `--add-dir` is always a write grant. The Orchestrator wraps runs in a macOS `sandbox-exec` profile because the CLI has none of its own | W, P | Probe: on a Linux container run with `--sandbox` and with `--add-dir` to one directory; try to write outside it and read a sibling checkout. Compare with the bubblewrap probe the Muse runner uses. |
| 5 | Reliability: stalls, silent success without work, empty output | **Yes if reproducible** | Unknown | Several defect classes seen in four months (section 3, including two false-success cases); none reproduced by this evaluation on 1.4.0 | P, W | The costliest class is silent success: the run narrates completion while the real checkout is unchanged. Any hosted runner must assert that the working tree or commit actually changed. |
| 6 | Commits on its own; commit identity | No | Unknown | Has a shell tool; the CLI sets `GIT_EDITOR=false` so a bare `git commit` fails fast; shell commands default to Ask and are soft-denied unless granted | W | Probe: run one real commit canary and read `commits/<sha>` for the author, as was needed for Muse (which committed as another vendor). |
| 7 | Model selector stability; fails loudly on an unknown model | No | Fails loudly on an unknown slug (documented) | Catalog churn is high: Flash moved 3.6 to 3.7 (retirement notice, 2026-09) and is now 3.8; the Pro slot was removed in favour of Argon; effort tiers are encoded in the model id | P, R | Pin by slug and validate against `agy models` at dispatch time (the Orchestrator does). The docs page lists `--effort low|medium|high`; the installed help lists `low|medium|high|xhigh|max`, so the two disagree. |
| 8 | Capacity model readable without spending | No | Unknown | `agy models` is a non-billing server call and validates auth; no remaining-quota read found | R | Probe: check whether `agy` exposes a usage or credits subcommand beyond the interactive `/config`. |
| 9 | Documented position on unattended or automated use | Record | No statement found for CI or hosted runners. A forum reply (author role not stated; not a policy) says running the official binary headless from another tool is supported for individual local use on the same Pro quota, and not as a shared relay or in a rapid polling loop | Same | W | Record only. A hosted runner serving a fleet is closer to "shared" than "individual local use", so hosted use needs an official answer before anything is built. |
| 10 | Install on Linux: method, integrity, libc, pinning | No | One-line installer script reported to verify a checksum and place `agy` in the user's local bin; requires glibc 2.28 or newer; musl (Alpine) unsupported; version pinning unknown | n/a | W (secondary sources) | Probe: download-then-run the installer in a container, then `agy --version`; check for an auto-update that could change behaviour mid-run (`agy update` exists). |

## 3. History of defects seen

From the Orchestrator's recorded fixes for this CLI and from the upstream changelog.

| When | Symptom | Class | Fixed upstream? |
| --- | --- | --- | --- |
| 2026-06-15 | Print mode wrote only inside its workspace; without `--add-dir <cwd>` it used an internal scratch workspace, left the real directory empty and narrated success | **False success** | Worked around by always passing an absolute `--add-dir`; no upstream fix recorded |
| 2026-06-17 | In a repository the CLI had not seen, it tried to create its project state under the home directory and failed with "no active conversation" when writable roots were restricted | Isolation | Worked around with the hidden `--gemini_dir` flag |
| 2026-06-22 | Version 1.0.10 exited 0 with no output unless an explicit model was given ("neither PlanModel nor RequestedModel specified") | **False success** | Worked around by always passing `--model`; later changelogs make `--model` accept a base name |
| (changelog 1.3.6) | The agent hung indefinitely when the model connection stalled | **Hang** | Yes: no data for 5 minutes now cancels and retries |
| (changelog 1.3.6) | Shell commands hung on an invisible editor (`git commit` without `-m`) | Hang | Yes: `GIT_EDITOR`, `HGEDITOR`, `JJ_EDITOR` set to `false` |
| (changelog 1.3.6) | Headless runs and subagent questions | Hang | Yes: headless `-p` runs skip subagent questions |
| (changelog 1.4.0) | "Eligibility check failed" refused every message until restart if the service was briefly unavailable or rate-limited at launch | Auth | Yes: retried |
| (changelog 1.3.3) | Expired or revoked sign-in mid-session gave an unclear error | Auth | Yes: "Authentication expired" |

The Orchestrator's own measurement of this seat, as printed by its value-chain monitor on
2026-10-17, is `agy-runtime-isolation`: invocation 53, usable 0, acted_on 866, outcome 4 (plus 11
excluded, 46 set aside as never merging, 805 still open), 8 FAIL verdicts, first break
**unmeasured**. That row measures the isolation workaround, not agy's quality, and it does not show
the lane delivering outcomes. Do not cite it as evidence that agy works.

## 4. Limitations and how to re-test them

| Limitation | Affects | What evidence would clear it | Cheapest probe |
| --- | --- | --- | --- |
| No headless credential that draws on a subscription; the documented headless route bills the API or a cloud project | Hosted CI | A documented headless credential tied to a plan quota, or an explicit decision that API or project billing is acceptable | Before/after usage-ledger reading around one key-authenticated call |
| Subscription sign-ins need a browser and an OS keyring; credential portability to a runner is undocumented | Hosted CI | A documented file or token credential that survives a clean container | Sign in once in a container, inspect only the credential file's field names and lifetime (never values) |
| No read-only mode; `--add-dir` always grants write; no Linux sandbox documented | Hosted and local | A Linux sandbox that blocks writes outside the workspace, verified by an escape attempt | Run with `--sandbox` in a container and attempt to write and read outside the granted directory |
| History of silent success (empty workspace, empty output) | Hosted and local | A release series with no recurrence, plus a runner-side assertion that the tree changed | Run the commit canary 20 times; count runs with exit 0 and no changed files |
| Soft permission denials exit 0 | Hosted | Documented non-zero exit option for denials, or runner-side detection | Run a denied-shell prompt headless; read the exit code and stderr |
| High model-catalog churn and effort-tier inconsistencies between docs and help | Hosted and local | Stable aliases that survive a quarter | Track `agy models` weekly; fail the runner on an unknown slug |
| No official statement on CI or fleet use | Hosted | An explicit vendor statement permitting hosted CI use | Ask in the vendor's developer channel; record the answer here |
| Commit identity and commit behaviour unverified | Hosted | A real commit canary with the author read back | One canary on Workflows |
| Capacity not readable without spending | Routing | A usage subcommand or API | Look for a credits or usage command in each release's changelog |

## 5. Re-evaluation triggers

Re-run section 2 when any of these happens:

1. A changelog line mentions a headless login, a token or file credential, service accounts, or a
   plan-quota route for `-p`.
2. A changelog line mentions a Linux sandbox or a read-only mode.
3. The vendor publishes a statement on automated or CI use.
4. Two consecutive minor versions pass the silent-success probe above.
5. The Gemini CLI path used by the existing `gemini` runner is retired for the credential type it
   uses; that forces a decision about the `gemini` agent regardless.

## 6. Recommendation

- **Now:** keep `agy` as a supervised local lane with the existing guards (absolute `--add-dir`,
  explicit `--model`, runtime-state redirection, a workspace that never holds the home directory or
  control plane). Do **not** add `reusable-agy-run.yml`, a registry entry, labels or consumer
  secrets.
- **When blockers 1, 2 and 4 clear:** start at Stage 1 of the
  [add-an-agent guide](../ADD_NEW_AGENT.md), with a Linux-container probe of section 2 rows 1, 4
  and 5, and a billing ledger reading, before any workflow file is written.
- **Parity cost to expect:** the full set of surfaces in the guide's Stage 4 table, a settings-file
  write step in the runner (an environment variable alone is not enough), a runner-side
  assertion that the working tree changed, and a decision about whether API or project billing is
  acceptable for unattended rounds.

## 7. Making better local use of the capacity

Hosted CI is closed to `agy` for now, but a supervised local seat can still be used better. Evidence
labels: **measured** (read from the Orchestrator's own ledger or the CLI, 2026-10-17), **documented**
(vendor or Orchestrator notes), **unknown**.

### What is known about the seat

- **Plan and meter** (documented): a prepaid, compute-metered plan with a five-hour refresh and a
  higher weekly ceiling. Google publishes no numeric quota. The meter weighs request complexity, tools
  used and accumulated conversation length.
- **Fixed overhead per call** (measured): a one-word prompt reported 12,844 input tokens, so every
  call carries a large fixed context cost. Many small calls are therefore expensive on a
  compute-metered seat; batching related questions into one call is cheaper.
- **Use** (measured, ledger estimates, not true headroom): about 138 starts and 145 estimated units in
  7 days against a locally assumed 280-unit weekly soft cap; in 14 days, roughly 43% of five-hour
  blocks had no agy use at all, and mean use was 2.6 of an assumed 8 units per block. Whether the real
  limits allow far more is **unknown**: the soft caps are the Orchestrator's own estimates, and an
  actual rate-limit or shed history has not been measured.
- **Routing** (measured in the router): agy is primary for epic, cross-repo and runtime-AC work, and a
  fallback for testgen, review and codemod. Drain mode biases routing toward agy in the last 90 minutes
  of a block, but only for six kinds of work, and nothing queues extra work to fill an idle block.

### Options, in the order worth trying

| # | Option | Why it fits agy | Risk and mitigation | Cheapest test |
| --- | --- | --- | --- | --- |
| 1 | **Third judge in local verification** (and the judge screen). `agy-cli` is already a backend of `tools/run_judge_backend_screen.py` | A different model family than the incumbents, with schema-constrained output (`--json-schema`) | Silent success and soft permission denials: the backend uses `--mode plan`, an explicit model, a scratch workspace, and treats an empty response as an error | Screen it on the frozen corpus with the other judges and read the ensemble analysis |
| 2 | **Use-it-or-lose-it drain queue**: a scheduled job that, in the last 90 minutes of a block with spare units, dispatches queued read-style jobs | Measured 2026-10-17 over 14 days: 67 completed blocks, 30 idle, 62 under the 8-unit soft cap, 174 units used against 365 unused (ledger estimates; the cap itself is an assumption) | Queue only report-producing jobs; apply any change through diff review | Count blocks that enter drain with fewer than 8 units over one week before building anything |
| 3 | **Long-context read-only audits** of a repository or a cross-repo question | Large context window, and the router already sends epic and cross-repo work here | No read-only mode: run against a disposable copy and require a clean `git status` afterwards | Audit one repository with known defects and score recall against the existing findings |
| 4 | **Evaluator arm** in the A/B/C/D experiment harness | Verified in code and data 2026-10-17: agy is the last top-up evaluator and is preferred as a neutral when its seat is in drain. It is **not** excluded from the ranking: the pooled `gemini` judge was `ready` at weight 0.61, earned by older models. That is corrected by the model epoch below | Its own scratch directory per arm | Score agreement with the other evaluators (the existing reliability measure), after the epoch reset |
| 5 | **Testgen** at the Flash tier | Cheap tier, machine ground truth from the testgen gate | Gate decides, never the model's own claim | Compare gate pass rate on 10 jobs against the incumbent |
| 6 | **Batched structured calls** with stream-json input and `--json-schema` | Amortises the fixed per-call overhead above | Reject empty or schemaless results | 20 jobs; count empty-result failures and units per job |
| 7 | **Its Claude and GPT-OSS models as an extra pool** when the Claude or Codex pools are exhausted | The router exposes them under one login | **Unknown** whether they draw the same meter, and provenance must record the model that actually served | One run per model, compare metered units |
| 8 | Plugins or MCP exposing **read-only** repository tools | `agy plugin validate --strict --json` gives a CI-checkable report | Tools widen write reach: expose only read-only ones | Validate a plugin, query one read-only tool |

`agy remote-control` is an attended, browser-driven mode and is not an unattended option.

### Argon is a new model: no inherited record

`gemini-4-argon-high` has run since 2026-10-16 (62 runs when measured). The Orchestrator learned
weights per **agent**, not per model: gemini's `review` (n=120) and `implement` (n=101) cells pooled
2.5 Pro, 3.1 Pro and three Flash generations, and the judge-reliability summary pooled 416 evaluator
scores. A change adds `config/model_epochs.json` (Orchestrator#685): both route-weight learners and the
judge-reliability summary count only runs at or after the agent's model epoch, so Argon starts from the
hand-set priors and earns its own record. Previewed on live data, gemini's evaluator weight goes from
0.61 to 0.0 until Argon has its own evidence, and readiness needs only 6 comparisons across 2
experiments. Experiments have slowed to 1 in the last 14 days (136 in 60), so waiting for Argon to be
fielded would take weeks; the pilots below replay archived work instead. Strengths of Argon are
**unknown**: no pilot below assumes any.

### Pilots (zero-owner-time, each ends in one number)

Shared rules: use the drain window only; disposable copy of the target (clean `git status` afterwards);
every item run twice in the pilot, once per call and once batched with `--json-schema` (option 6), so
units per item and empty-result failures are measured on the same work; the seat's own estimated
units come from the capacity ledger; a 429 or shed ends the pilot and is recorded, not retried.

| Pilot | Work and ground truth | Pass number (printed by the pilot's report) | Verdict it produces |
| --- | --- | --- | --- |
| 1. Judge screen (built) | The frozen 8-case corpus, then the 75-case approval corpus as it grows | `analyze_judge_ensemble` recommendation for agy | Today: not eligible (2 false PASS, 2 invalid) |
| 2. Drain measurement (done) | Ledger over 14 days | Blocks under cap / completed blocks = 62 / 67 | Idle capacity exists on the local estimate; re-run after pilots 3 and 5 to see real use |
| 3. Read-only audit | One repository whose earlier audit findings are filed and confirmed; the finding set is the answer key | Recall of the key; share of cited `file:line` that resolve; the same two numbers for the incumbent audit agent on the same repository | Argon is a candidate audit lane only if its recall is not below the incumbent's and its citations resolve |
| 5. Test generation | 10 jobs the testgen gate already scores | Gate pass rate against the incumbent on the same jobs | Candidate testgen lane if not below the incumbent |
| 4. Evaluator replay | Archived experiments whose consensus ranking exists | Argon's `judge_reliability` row: `ready`, weight, mean error vs consensus | Counts in rankings again only when `ready`, at its earned weight |

**First pilot run (2026-10-17, `tools/agy_pilot.py`, evidence `docs/evidence/judge-screen-20261017/agy-pilot-1.json`).**
Exploratory: 5 seeded defects across two modules; a third module yielded no validated mutants. Tokens are as the backend reported them.

| Backend | Pilot | Mode | Result | Tokens per item |
| --- | --- | --- | --- | ---: |
| agy (`gemini-4-argon-medium`) | audit | single / batched | recall 1.0, precision 1.0 / recall 1.0, precision 1.0 | 14,588 / 7,855 |
| agy | testgen | single / batched | kill rate 1.0, clean pass 1.0 / kill rate 0.4, clean pass 0.5 | 16,552 / 9,716 |
| Claude CLI, tools off | audit | single / batched | recall 1.0, precision 1.0 / same | 4,472 / 3,037 |
| Claude CLI, tools off | testgen | single / batched | kill rate 1.0 / kill rate 1.0 | 9,570 / 7,280 |

Reading it: on this small corpus agy matched Claude on audit and on single-module test generation, so
neither pilot is ruled out. Batching nearly halved agy's tokens per item, but batched test generation
broke (half the files failed on clean code), so batching is safe for audit here and **not** for test
generation without more evidence. agy costs about 2 to 3 times Claude's tokens per item, mostly the
fixed per-call overhead. Six defects cannot separate the two on quality; the next run needs more
modules (the harness needs target modules whose own tests are strong enough to validate mutants).

**Second pilot run (2026-10-17): more modules, test generation, and the evaluator replay.**
Evidence: `agy-pilot-2-agy.json`, `agy-pilot-2-claude.json`, `agy-judge-replay-*.json` in `docs/evidence/judge-screen-20261017/`.
Exploratory. Nine modules were scored, with 25 planted mutants across all nine module entries in each committed second-pilot evidence file. The test-generation rows below were first scored while the sandbox lacked sibling modules (every backend lost points on modules that import them); they were rescored after the sandbox was given copies of the sibling modules, and the rescored figures are the ones shown.

| Backend | Pilot | Single call | Batched | Tokens per item (single / batched) |
| --- | --- | --- | --- | ---: |
| agy (`gemini-4-argon-medium`) | audit recall (precision 1.0) | 1.00 | 0.96 | 15,005 / 4,905 |
| agy | testgen kill rate (clean pass 0.89 single, 0.78 batched) | 0.88 | 0.72 | 21,290 / 10,005 |
| Claude CLI, tools off | audit recall (precision 1.0) | 0.92 | 0.92 | 6,130 / 4,199 |
| Claude CLI | testgen kill rate (clean pass 1.00 single, 0.56 batched) | 1.00 | 0.56 | 19,991 / not reported (4 batches unusable) |

Evaluator replay (pilot 4): 8 archived experiments, one selected archived judge prompt and anonymized ordering per experiment. The candidate sees the first prompt whose judge has a real score; the replay does not measure sensitivity across all archived prompt permutations.

| Judge | Mean error vs real-judge consensus | Rank agreement |
| --- | ---: | ---: |
| agy | 1.479 | 0.838 |
| Claude CLI | 1.471 | 0.747 |
| Real judges, each against the others | 1.337 | n/a |

Reading it: agy matches or beats Claude on audit and tracks the real judges as closely as Claude does,
with better rank agreement. On test generation agy is below Claude single-call (0.88 against 1.00) but
holds up better when batched (0.72 against 0.56, where 4 of Claude's batches returned nothing usable). Batching cuts agy's audit cost to a
third at a 4-point recall cost. These are small samples and say nothing yet about Argon's strengths
beyond this work. The replay writes nothing to the Orchestrator's records: agy is not a ready judge until
it is fielded and scored in real experiments.

**A harness defect found on the way.** A review round changed the agy backend to stream mode with an
input shape agy does not accept, and a fixture test using an invented response shape kept passing while
every real call came back empty. The backend now speaks agy 1.4.0's real shape
(`{"event":"user","message":{"content":...}}` in, `{"event":"result","result":{...}}` out), a denied tool
action is an error not an answer, and a test pins the real shape through a fake executable.

**The seat's weekly quota is real, and we reached it (2026-10-18).** After the two pilot rounds and the
replays, agy answered `Individual quota reached ... Resets in 132h` (HTTP 429, RESOURCE_EXHAUSTED). This
replaces the earlier "real limits unknown" with a measurement: roughly 60 pilot and replay calls of 10k to
22k input tokens each, on top of normal Orchestrator use, exhausted the weekly allowance. The harness used
to report this as an "empty response"; it now names it, stops spending, and records the remaining items as
unusable. Larger pilots (30 replayed experiments, 8 audit modules) wait for the reset; plan them as part
of the drain queue (option 2) so they spend only leftover capacity.

Option 6 (batching) is not a separate project: its number is units per item, batched against single,
reported by pilots 3 and 5.

**Third pilot run (2026-10-30): no pass number was measured.**
Evidence: `docs/evidence/agy-pilots-20261030/` (`judge-replay-agy.json`, `judge-replay-claude.json`,
`run-record.json`). This is a run record, not replay or seeded-defect evidence: no backend returned a
scored answer.

| Pilot | Planned work | Pass number | agy result | Claude yardstick | Met? |
| --- | --- | --- | --- | --- | --- |
| 4. Evaluator replay | 32 archived experiments (the 8 from 2026-10-17 plus 24 evenly spaced from the 135 with at least 3 scored real judges, at least 3 members and a prompt of at most 60k characters) | agy mean error vs consensus no more than 1.5 times the real judges' leave-one-out error | 0 of 32 usable: quota error on the first call, other 31 not sent | 0 of 32 usable: the CLI login had expired | Not measured |
| 3. Read-only audit | 10 modules, 28 validated seeded defects | agy recall not below Claude's, citations resolving | Not run: quota | Not run | Not measured |
| 5. Test generation | The same 10 modules | agy kill rate not below Claude's | Not run: quota | Not run | Not measured |

- **Quota consumed by this run: one agy call.** That call returned `Individual quota reached ...
  Resets in 8h6m57s` (RESOURCE_EXHAUSTED) at about 18:40 UTC, so the seat was already out before the
  pilots started. The harness stopped there and did not retry. The weekly reset expected around
  2026-10-23 had happened, so other use, probably normal Orchestrator routing, used up the allowance
  again within a week. Whether the 8-hour reset is the five-hour block or the weekly ceiling is
  **unknown**. Either way, the larger pilots cannot rely on a reset alone. They need capacity set
  aside for them, such as the drain queue (option 2) or a pause in agy routing before the run.
- **Claude yardstick: 32 calls, 0 tokens.** The standalone Claude CLI was logged out (`claude auth
  status`: not logged in). The backend reported only "Claude CLI error", which hid the cause, the same
  failure class as the earlier quota-reported-as-empty defect. It now names the CLI's own message, and
  a test pins this.
- **Ready for the next run (no model calls needed):** the module set was validated locally (seed 7,
  3 mutants per module, each kept only if the module's own tests fail on it). The 9 earlier modules
  plus `coverage_trend` give 10 modules and 28 defects. `stable_pass_cases`,
  `verifier_standards_model` and `verifier_compare_run_receipt` produced no validated mutants. The
  experiment list is in `run-record.json`. Re-run order: replay, then audit, then testgen, with the
  Claude CLI logged in first.

### Rule checks

- **Subscription over API spend:** every option uses the subscription login. One risk to close first:
  AI credits are described as overage-only, so confirm the account cannot auto-spend credits.
- **Never write outside the workspace:** the guards that actually hold are the Orchestrator's
  macOS sandbox profile and the refusal of any broad workspace. They are refused when nested or when the
  sandbox tool is missing. Read-only jobs should use a disposable copy rather than trust the CLI.
- **The `gemini` key spans two different things.** The Orchestrator's router lists `gemini` among the
  agents hosted keepalive may run, and in Workflows the hosted `gemini` runner is the older Gemini CLI
  on an API key, whereas the local seat is `agy` on a subscription login. They bill differently and
  fail differently. Give the local seat its own name before any routing or ledger decision depends on
  the distinction.

Pilot execution safety: generated Python runs only in the deny-by-default macOS sandbox with a minimal environment, scratch-only writes, runtime-only reads and no network. Unsupported hosts or isolation startup failures fail closed. agy prompts use stdin stream events; any reported tool activity makes the call unusable. The archived first pilot predates these controls and is exploratory evidence, not a production qualification.
