# Adding a New Coding Agent to Workflows

This guide is the complete checklist for bringing a new coding agent (another LLM CLI) into the
Workflows pipeline so it participates in keepalive, autofix, the belt, issue intake and the
consumer repositories on the same footing as Codex and Claude. It was rewritten after Cursor and
Muse were added in October 2026, because the earlier version described the happy path and omitted
the places where those two integrations actually broke.

Read it with these companions:

- [Agent Runner Implementation Guide](AGENT_RUNNER_IMPLEMENTATION.md) — the mechanics every
  `reusable-<agent>-run.yml` must get right (commit detection, push retry, fail-closed guards).
- [Agent Runner Output Contract](../contracts/agent-runner-output.md) — required inputs and outputs.
- [Agent Readiness Evaluation](agent-readiness/README.md) — how to decide whether an agent should be
  integrated at all, with a template and one worked evaluation.
- [Keepalive Agents Guidance](../keepalive/Agents.md) and
  [Multi-Agent Routing](../keepalive/MULTI_AGENT_ROUTING.md).

## How to use this guide

The work is a ladder. Each stage ends with an **exit check** that produces evidence, and each piece
of evidence names its **class** so nobody later mistakes one for another:

| Evidence class | Meaning | Grades usefulness? |
| --- | --- | --- |
| Production use | The agent did real work in the situation it was built for | Yes |
| Real trial | A throwaway canary on live infrastructure (real CI, real repo, real secrets) | Yes, for that path |
| Fixture check | A unit test or scripted check against controlled input | No |
| Wiring check | Configuration, registry or static analysis says it should work | No |

A stage is **done** only when its exit check has produced a number or artifact you can quote (a
commit SHA, a run id, a check conclusion). "The PR merged", "the checklist is ticked" and "the
workflow exists" are wiring checks, not delivery. Say which stage you reached, not that the agent is
"integrated".

Hard-won rules that apply to every stage:

1. **Never print credentials.** Provision secrets by piping them into `gh secret set` from a
   script that prints only key names and validation verdicts. Never echo a line of a credentials
   file, not even to list its labels.
2. **Check what a key bills before using it.** The same vendor can issue keys that draw on a
   subscription and keys that meter pay-as-you-go. Prove which one you hold from the vendor's usage
   ledger before putting it in a secret.
3. **A gate you add must be able to clear.** See the latched-gate check in the repository
   guidance: name what decrements it, whether that can run while the gate is closed, and what it
   prints when drained.
4. **Deliver what the consumers actually run.** Consumers run their own copies of several scripts
   (see Stage 5). A change that only lands in Workflows does not reach them.
5. **CI is slow (30–60 minutes for the Python jobs).** Batch fixes into one push; every push
   restarts Gate. A `Gate / gate` entry that says "cancelled" is usually a stale run on the previous
   commit.

## Stage 0 — Readiness evaluation (before any code)

Answer these in writing, using [the template](agent-readiness/TEMPLATE.md). Any "no" or "unknown"
on rows marked **blocker** means the agent is not ready for hosted use; record what would change the
answer instead of building around it.

| Question | Why it matters | Blocker? |
| --- | --- | --- |
| Can the CLI authenticate **unattended on a clean Linux runner** with a credential that fits in a repo secret? | Hosted CI has no browser, no OS keyring and no human | **Blocker** |
| What does that credential **bill** (subscription, prepaid pool, pay-as-you-go)? Is the billing acceptable for unattended use? | Subscription logins and API keys are often different meters | **Blocker** |
| Does it have a **headless print mode** with a bounded runtime, machine-readable output and a non-zero exit on failure? | The runner contract needs outputs and exit codes | **Blocker** |
| Can it run **sandboxed** (or can the runner confine it) and is the sandbox usable on a Linux CI runner? | Agents with shell access can write anywhere the runner can | **Blocker** |
| Does it **commit** on its own, and under what identity? | Determines commit detection and attribution | No, but needed |
| Does it stall or return success without doing work? | False success is the costliest failure mode | **Blocker** if reproducible |
| Is there a **stable model selector** and does the CLI fail loudly on an unknown one? | Silent fallbacks change cost and quality | No |
| Is there a documented, supported position on unattended or automated use? | Policy can change what is allowed | Record it |
| What is the **capacity model** (windows, seats, credits) and can it be read without spending? | Routing and rotation need a capacity signal | No |

Exit check: a completed evaluation file committed under `docs/guides/agent-readiness/`, with a
verdict (ready / ready for local use only / not ready) and the conditions that would change it.

## Stage 1 — Identity and credentials

1. Decide whether the agent commits as a shared automation account or its own service account. Grant
   write access to the repositories it will touch. Record the automation login in the registry.
2. Create the credential the CLI will use unattended (API key, OAuth token or auth JSON). Store it
   under the runner's expected secret name (for example `AGENTNAME_API_KEY`). Never reuse a
   personal-account key whose billing you have not verified (rule 2 above).
3. Add the secret to the Workflows repository and to **every consumer repository** that will run the
   agent. Verify presence with `gh secret list` afterwards; do not read values back.
4. The service PAT that runs the dispatch gate (`SERVICE_BOT_PAT`) must be able to read repository
   Actions **variables**, in addition to PR-comment read/write. `should-dispatch` reads the legacy
   variable store and fails closed on a 403, which silently blocks every dispatch in a repository
   whose PAT lacks that permission. Probe it per repository: `GET
   /repos/<owner>/<repo>/actions/variables/<any-name>` must return 404, not 403. This was the root
   cause of Cursor and Muse rounds never starting in the three newest consumer repositories. Do not
   weaken the fail-closed rule; fix the token.
5. If the credential has a lifetime (OAuth access token without refresh, key rotation), schedule a
   check and record the expected lifetime in the registry entry's comments.

Exit check (real trial): a `workflow_dispatch` or canary run in which the preflight step reports the
secret present and the CLI starts. Wiring check alone does not pass this stage.

## Stage 2 — Registry entry

`.github/agents/registry.yml` is the single source for which agents exist. Add a key with:

- `runner_workflow`, `required_secrets` (and `required_secrets_mode` if any-of), `branch_prefix`
  (must end with `/issue-`), `automation_logins`, `readiness_candidates`.
- `preflight` (`assign_user`, `command_phrase`, `enabled`). `enabled` controls the readiness probe
  and issue-intake invitation. Keep it **off** until an authenticated issue-intake canary has
  reached the agent's real runner; keepalive execution alone does not qualify it.
- `capacity` (window and limit) so rotation has a signal.
- `capabilities`: `pr_keepalive`, `pr_autofix`, `belt`, `verifier_checkbox`. Set a capability to
  `true` only when the matching wiring in Stage 4 exists; `tests/workflows/test_belt_agent_registry.py`
  and the autofix parity test enforce this for belt and autofix.
- Optional `keepalive_worker_job` / `keepalive_worker_step` if the routed job and step names differ
  from `Keepalive next task (Agent)` and `Run Agent`.

The consumer template copy, `templates/consumer-repo/.github/agents/registry.yml`, must stay
byte-identical to the root file (a test enforces it).

## Stage 3 — Runner workflow

Create `.github/workflows/reusable-<agent>-run.yml` by deriving it from the closest existing runner
(Cursor and Muse were derived from Codex/Claude). It must:

- Accept the standard inputs (prompt file, mode, PR number and ref, appendix, skip-permissions,
  extra CLI args, capability-evidence fields) and emit every output in the output contract.
  Add a `duration-seconds` output if the CLI reports no token usage, so cost can still be tracked.
- Authenticate from the agent's secret **only in the run step's environment**. Never export it
  through `GITHUB_ENV`, never echo it.
- **Fail closed, with a named error, before the agent runs**: missing secret; CLI install or start
  failure; sandbox probe failure on Linux; prompt-integrity guard failure. The run step must check
  the outcome of those steps explicitly (it runs under `always()`), and a step that was *skipped* is
  not a success — require the CLI step's outcome to equal `success`.
- Install the CLI by downloading the installer to a file and then running it, never by piping a
  download into a shell. Pin a version where the vendor allows.
- Probe the sandbox if the CLI needs one (for example bubblewrap): on Ubuntu runners the user
  namespace restriction may need relaxing, so probe, relax, probe again, and fail with a named error
  rather than letting the run continue unsandboxed.
- Detect commits the agent made itself (unpushed commits) at both early-exit points, route staging
  through `scripts/stage_agent_changes.py`, and push with retry (see the runner guide).
- Decide commit identity deliberately. Some CLIs commit under another vendor's identity (Muse's
  1.4.9 committed as "Claude" and was later fixed upstream), which makes author-based attribution
  credit the wrong agent. Check `gh api repos/<repo>/commits/<sha> --jq .commit.author` on the first
  real commit, and normalise unpushed commits to the agent's identity if the CLI does not.
- Add the new runner to the tables that pin the set of runners (Stage 6).

## Stage 4 — Wire the agent into the pipeline

The pipeline has **static per-agent jobs**: GitHub resolves reusable-workflow references at
startup, so there is no registry-driven fan-out. Adding an agent means adding its analogue wherever
Cursor and Muse have one. Use this table as the checklist; each row names a real file.

| Surface | File(s) | What to add |
| --- | --- | --- |
| Keepalive loop job | `.github/workflows/agents-keepalive-loop.yml` | `run-<agent>` job (explicit secret map, not `secrets: inherit`), auth switch cases, `needs` entries, every result/exit-code `||` chain |
| Consumer keepalive + autofix | `templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml` | `run-<agent>` and `autofix-<agent>` jobs, `HAS_<AGENT>_AUTH`, auth switch cases, metrics `needs`, result selection |
| Autofix loop | `.github/workflows/agents-autofix-loop.yml` | `autofix-<agent>` job, **and** the agent key in the `supportedAgents` allow-list (a job without the allow-list entry can never run; Cursor's job was dead for months this way) |
| Delegation policy | `.github/scripts/agent_delegation_policy.js` (+ template copy) | default registry entry; runner map |
| Keepalive secrets map | `.github/scripts/keepalive_loop.js` (+ template copy) | `HAS_<AGENT>_AUTH` → secret name |
| Auto-pilot | `.github/workflows/agents-auto-pilot.yml` (+ template copy) | `HAS_<SECRET>` availability flag |
| Bot-comment routing | `.github/scripts/bot-comment-handler.js` | legacy `agent:<key>` route |
| Runner provider set | `scripts/runner_lib/core.py` | add the key to `PROVIDERS` and, if it takes prompts, `PROMPT_PROVIDERS`. **Consumers run their own copy** (Stage 5) |
| Artifact filtering | `scripts/stage_agent_changes.py` | the agent's root output filename patterns |
| Durability attribution | `scripts/export_keepalive_durability.py` | `KNOWN_AGENT_LABELS` |
| Merge origin labels | `.github/scripts/merge_manager.js` (+ template copy) | registry-driven since 2026-10-17; verify the belt worker's `from:<agent>` label is recognised |
| Labels | `.github/labels-core.yml`, `.github/labels.yml`, `scripts/cleanup_labels.py`, `docs/LABELS.md` | `agent:<key>`, `runner:<key>`, `from:<key>` (quote descriptions that contain a colon) |
| Health | `.github/workflows/health-<agent>-auth-check.yml` | presence check that names a missing secret and never echoes it; no billable call |
| Belt | registry `belt: true` only | the belt is registry-driven; the round runs in the keepalive `run-<agent>` job. **It requires** `scripts/ledger_validate.py` and `scripts/belt_ledger_completion.py` in the consumer, or every belt PR fails the required `summary` check |
| Issue intake | registry `preflight.enabled` | only after an authenticated issue-intake canary; intake routes by the issue's `agent:<key>` label regardless |
| Verifier | registry `verifier_checkbox` | leave `false` unless the agent is a qualified verification judge |

Known by-design exclusions (do not "fix" these when comparing against Codex and Claude):

- The verifier judges, the repo-review rounds (`scripts/repo_review_*`) and the `@codex` / `@claude`
  comment-command detection are Codex- and Claude-specific. Hosted Cursor and Muse rounds are
  dispatched without a comment.
- `AGENT_ALTERNATES` in `keepalive_loop.js` maps only Codex ⇄ Claude for the independent-verification
  step. For other agents the verification step runs on the same agent unless the repository sets
  `verifier_agent`. This is a known gap, not a design choice (tracked in Workflows#4041); check it
  before relying on independent verification for a new agent.

## Stage 5 — Deliver to consumer repositories

The template sync (Maint 68/71) delivers template changes only after its canary-promotion gate
passes, and it has been stalled for stretches. Plan for **owner-directed direct delivery**: one pull
request per consumer repository, never a force-push.

What reaches consumers, and in what form:

- **Template files** (`templates/consumer-repo/...`): workflows, registry, scripts, docs.
- **Root-sourced scripts** listed in `.github/sync-manifest.yml` (for example `scripts/runner_lib/`,
  `scripts/ledger_validate.py`). Consumers run their **own copy** of these. A change to
  `scripts/runner_lib/core.py` (for example adding a provider) changes nothing in a consumer until it
  is delivered. The symptom of forgetting is `should-dispatch: error: argument --provider: invalid
  choice`.
- **Everything such a script imports.** `ledger_validate.py` imports `belt_ledger_completion.py`;
  delivering only the first changed the failure rather than fixing it.

Procedure:

1. List the files, and for each consumer confirm the consumer's copy is **byte-identical to an
   earlier Workflows version** before overwriting it (drift-safe). Skip and report divergent copies.
2. Open one ready (non-draft) pull request per consumer containing only those files, with the
   `workflow-source` declaration the repository requires.
3. Read the **full diff of what you deliver**, not just your own line. Delivering the current
   template also delivers whatever else it carries (Cursor intake enablement rode along with a Muse
   registry change and was rightly questioned in review).
4. Merge when the required checks pass. Expect: branch protection that requires conversation
   resolution (answer each thread with an honest disposition and resolve it; do not assert a finding
   is valid or invalid without checking), a merge guard in some repositories with a review floor,
   and branches that fall behind and must be updated.
5. If a regenerated artifact depends on the manifest (the Renovate ownership preset), regenerate it
   in the same change and check that the **commit** contains it. A sparse checkout can silently
   skip `git add` for paths outside its definition.
6. **Verify by reading each consumer's `main`**, not the pull request status: the files exist, the
   registry entry has the capability, and the secrets exist (`gh secret list`).

Add every new script a consumer workflow runs, and everything it imports, to the sync manifest.
`tests/workflows/test_consumer_template_script_refs_synced.py` fails if a consumer workflow runs or
imports something that is neither in the template nor the manifest.

## Stage 6 — Tests and tables that pin the agent set

Adding an agent changes tables that tests pin on purpose. Expect to edit:

- `tests/workflows/test_workflow_naming.py` (workflow name table and inventory docs)
- `tests/workflows/test_artifact_retention.py` (artifact names and retention)
- `tests/workflows/test_no_untrusted_interpolation.py` (reviewed interpolations)
- `tests/workflows/test_agents_guard_registry_enabled.py` (the exact list of enabled agents)
- `tests/workflows/test_belt_agent_registry.py` and `test_muse_runner_routing.py`-style routing
  tests (every capability the registry claims has a matching job)
- `tests/docs/test_workflow_source_docs.py` (routing doc covers every enabled agent)
- `tests/scripts/test_sync_manifest_compiler.py` (manifest entry count) and
  `tests/scripts/test_generate_consumer_renovate_ownership.py` (regenerate the preset)
- `docs/ci/WORKFLOW_OUTPUTS.md`, `docs/ci/WORKFLOWS.md`, `docs/ci/WORKFLOW_SYSTEM.md` (output and
  workflow inventories)

The test-quality gate rejects a new test file without literal expected assertions; include some.
For each new test, demonstrate it fails against the broken state and passes against the fix.

## Stage 7 — Documentation

Update, in the same change set as the wiring:

- `docs/WORKFLOW_GUIDE.md`, `docs/LABELS.md` (and the template copy), `docs/keepalive/Agents.md`,
  `docs/keepalive/MULTI_AGENT_ROUTING.md`, `docs/ci/*` inventories.
- **Consumer-facing setup**: `templates/consumer-repo/docs/SETUP_CHECKLIST.md` (secrets table,
  checklist, and a per-agent secret section including any billing caution) and the consumer README.
- This guide's parity matrix (below) and a readiness evaluation under `agent-readiness/`.

Do not put local machine paths, personal usernames, email addresses, device codes or any credential
in these documents. Refer to credential locations generically ("the CLI's credential file").

## Stage 8 — Prove the paths with canaries

Run each path on a throwaway issue and pull request that is closed unmerged after the proof. Name
the pass number before you start.

| Path | Canary | Pass number (real trial) |
| --- | --- | --- |
| Keepalive | PR labelled `agent:<key>`, `agents:keepalive`, `agents:max-runs:1`, tasks in its source issue | A commit by the agent adding the requested files; the loop reports `Agent: <Name>` |
| Belt | Issue labelled `agent:<key>` + `agents:auto-pilot` | The belt creates `<prefix>NNN` and opens the PR; the agent commits; `ledger validation` passes |
| Autofix | A PR with a deliberately failing test | The agent's autofix job runs and pushes a fix |
| Issue intake | Issue labelled `agent:<key>` | The intake reaches the agent's real runner and produces a commit |

Run the canary first on Workflows itself, where the secrets and a working PAT already exist, then in
one consumer repository. Read the run logs for the agent job's exit code and push step rather than
trusting a green check. Record the commit SHA and the commit author.

## Stage 9 — Rollout, monitoring and the parity review

- Provision secrets to every consumer, then monitor the first rounds (loop summaries, guard,
  belt logs) for authentication and prompt issues.
- Repeat the **parity review** whenever an agent is added or its capabilities change. A mechanical
  starting point (list operational files that name Codex or Claude but not the new agent):

  ```bash
  git grep -n -i -E "(codex[^\n]{0,40}claude|claude[^\n]{0,40}codex)" -- \
    '.github/workflows/*.yml' '.github/scripts/*.js' 'scripts/*.py' \
    'templates/consumer-repo/.github/workflows/*.yml' '.github/agents/*' \
    | grep -v -i -E "<newagent>|__tests__"
  ```

  Triage each hit as a real gap or a documented exclusion (Stage 4).
- For the local Orchestrator (a separate repository), the equivalent surfaces are the adapter,
  the capacity seat, the router's backup set, execution profiles, the auth check, dispatcher
  environment scrubbing and the architecture document and diagram, which are a contract and must be
  updated together.

## Parity matrix (as of 2026-10-17)

Evidence class in parentheses: **P** production use, **R** real trial, **W** wiring/fixture only,
**—** absent, **n/a** by design.

| Surface | Codex† | Claude† | Cursor | Muse |
| --- | --- | --- | --- | --- |
| Registry entry and runner workflow | W | W | W | W |
| Keepalive (hosted PR rounds) | P | P | P (Workflows PR #3890), R (consumer canary) | R (Workflows and consumer canaries) |
| Autofix wired (registry, loop, template) | W | W | W (completed 2026-10-17) | W |
| Autofix proven by a canary | P | P | — | — |
| Belt (issue → PR) | P | P | R (consumer canary) | R (consumer canary) |
| Issue intake (`preflight.enabled`) | W | W | R (qualified 2026-10-16) | — (deferred; intake routes by label regardless) |
| Verifier judge (`verifier_checkbox`) | W | W | n/a | n/a |
| Independent verification alternate | W (⇄ Claude) | W (⇄ Codex) | — (known gap, #4041) | — (known gap, #4041) |
| Health check | W (expiry) | W (inline token detect) | W (presence) | W (presence, CLI, sandbox) |
| Labels `agent:` `runner:` `from:` | W | W | W | W |
| Consumer secrets provisioned | P | P | W (all repos) | W (all repos) |
| Hosted-CI auth model | auth JSON | OAuth token | API key | subscription login's console key |
| Local Orchestrator seat | P | P | P | W (backup-only, subscription login) |
| Local opener/closer lane | P | P | — | W (built, off) |
| Repo-review rounds | n/a (Codex+Claude by design) | n/a | n/a | n/a |
| `@agent` comment commands | P | P | n/a | n/a |

† The Codex and Claude cells reflect their long-running use as documented elsewhere in this repository and were not re-measured in this review. The Orchestrator's value-chain monitor has no per-agent integration row, so none of these cells is graded from a monitor measurement; each is graded by the evidence class shown.
