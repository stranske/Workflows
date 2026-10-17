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
