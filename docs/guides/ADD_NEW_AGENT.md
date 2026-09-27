# Adding a New Automation Agent to Workflows

This checklist covers every step required to bring a new automation agent (for example, another LLM runner) into the Workflows repository so it participates in the full keepalive/autofix/orchestrator pipeline alongside Codex and Claude.

## 1. Prepare the Agent Identity & Credentials
1. **Create or designate a GitHub service account** for the agent. Grant it `write` access to the repos it will touch.
2. **Generate credentials**:
   - Long-lived PAT for branch pushes (store as `OWNER_PR_PAT`/`SERVICE_BOT_PAT` equivalents if needed).
   - Any provider-specific auth (for example, OAuth token or JSON config for the agent CLI).
   - Optional: GitHub App private key/ID if the agent will mint tokens directly.
3. **Add secrets** to the Workflows repo (and consumer repos as needed). Follow the naming pattern the runner expects (for example `AGENTNAME_AUTH_JSON`, `AGENTNAME_OAUTH_TOKEN`).
4. **Record the automation login** (GitHub username) and any reviewer/bot handles the workflow must recognize.

## 2. Register the Agent in `.github/agents/registry.yml`
1. Copy the structure used for `codex`/`claude` and add a new key under `agents:` with:
   - `runner_workflow`: path to the reusable runner workflow you will add.
   - `required_secrets`/`required_secrets_mode`: secrets the runner needs.
   - `branch_prefix`, `automation_logins`, `readiness_candidates`, and `preflight` hints.
   - `capabilities`: mark which surfaces the agent supports (`pr_keepalive`, `pr_autofix`, `belt`, `verifier_checkbox`, etc.).
2. If the agent needs custom metadata (prompt overrides, CLI args), surface it via `agent_registry.js` helpers so workflows can read it without hard-coding names.
3. A keepalive-capable agent should name its routed job `Keepalive next task (Agent)` and its reusable worker step `Run Agent`, using the capitalized registry key. If either name differs, set `keepalive_worker_job` and `keepalive_worker_step` in that agent's registry entry so failed-run evidence remains attempt-bound without a provider list.

## 3. Supply the Runner Workflow & CLI Support
1. Create a reusable workflow in `.github/workflows/` (for example `reusable-newagent-run.yml`) modeled after the Codex/Claude runners:
   - Mint the Workflows GitHub App token for repo checkout/push (falls back to `GITHUB_TOKEN` automatically).
   - Checkout both the target repo and `.workflows-lib` scripts; reuse `.github/actions/setup-api-client`.
   - Install/prepare the agent CLI (Node, Python, Docker, etc.).
   - Expose inputs for prompt files, sandbox/safety flags, runtime caps, PR context, appendices, etc.
   - Emit outputs (`final-message`, `changes-made`, `commit-sha`, error classification) that match the existing runner contract so orchestrator/keepalive can process results uniformly.
2. Store any agent-specific prompts/scripts under `.github/<agent>/prompts` or `scripts/` if needed. Avoid duplicating shared logic.

## 4. Wire the Agent into the Pipeline
1. **Labels & Templates**
   - Add `agent:newagent` (or similar) to `docs/LABELS.md`, `.github/labels*.yml`, and issue templates so Auto-Pilot can assign the agent.
   - Add a `runner:newagent` label so auto-pilot users can request the agent without triggering the issue intake workflow.
2. **Keepalive / Orchestrator**
   - Ensure `reusable-16-agents.yml` (agents toolkit) automatically sees the agent via the registry (no code changes should be needed if it loops over the registry).
   - Update `agents-70-orchestrator.yml` options, if necessary, to mention the new agent in readiness tables or toggles.
3. **Keepalive prompts & guards**
   - Confirm `scripts/keepalive_*` helpers read prompts/tokens via `agent_registry.js`. If a new prompt template is needed, add it and gate by `agentKey`.
   - Verify `agents-bot-comment-autolabel` and other guard workflows include the new agent’s automation login when relevant (for example, inline comment handlers).
4. **Belt / maint workflows**
   - If the agent will use the Codex belt (dispatch/worker/conveyor), ensure the registry entry marks `belt: true` and the belt workflows honor the routing. Add new wrappers only if absolutely required.

## 5. Documentation & Checklist Updates
1. Update `docs/WORKFLOW_GUIDE.md` to describe the new runner, orchestrator behavior, and any token requirements.
2. Mark the relevant row in `docs/workflow-updates/workflow-checklist.md` as reviewed (or add a new row).
3. If keepalive contracts change, update `docs/keepalive/Agents.md` and related references (`MULTI_AGENT_ROUTING.md`, `GoalsAndPlumbing.md`).
4. Link to this checklist from any planning docs for future contributors.

## 6. Testing & Validation
1. Run `scripts/validate_yaml.py`, `actionlint`, and any targeted unit tests (`npm test -- agent_registry` etc.).
2. Dry-run the reusable workflow via `workflow_dispatch` using a sandbox branch to confirm:
   - Repo checkouts succeed (App token fallback works).
   - CLI installs correctly and respects `skip_permissions`/sandbox flags.
   - Outputs (`changes-made`, `final-message`) populate for orchestrator consumption.
3. Execute a small end-to-end flow (label an issue with `agent:newagent`, run orchestrator/keepalive) in a non-critical repo and verify:
   - Preflight tables show the agent.
   - Keepalive dispatches the correct runner.
   - Autofix/belt/verifier hooks honor the new agent routing.

## 7. Rollout & Monitoring
1. Add the new secrets to each consumer repo that plans to use the agent.
2. Communicate the rollout plan (Slack/Docs) so maintainers know which labels trigger the new agent.
3. Monitor the next few runs (keepalive loop summaries, agents-guard, belt logs) for auth or prompt issues.
4. File follow-up docs or automation improvements as the new agent matures.

Following this checklist ensures the new agent is discoverable via the registry, routed through every automation surface (Auto-Pilot, keepalive, autofix, belt, verifier), and fully documented for future maintainers.
