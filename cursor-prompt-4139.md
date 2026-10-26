# Fix Merge Conflicts

This PR has **merge conflicts** that must be resolved before CI can run or the PR can be merged.

## Your Task

Resolve all merge conflicts by integrating changes from the base branch with this PR's changes.

## CRITICAL: You MUST attempt the merge

**Do NOT check `git status` first and exit if clean!** The conflicts only appear DURING the merge operation.

You must ALWAYS run `git merge origin/{{base_branch}}` to surface the conflicts, even if the working tree appears clean initially.
After the merge attempt, you can use `git status` to confirm the conflict state.

## Conflict Detection

{{#if conflict_files}}
**Potentially conflicting files:**
{{#each conflict_files}}
- `{{this}}`
{{/each}}
{{else}}
Check `git status` to identify files with conflicts.
{{/if}}

## Resolution Steps

1. **Fetch latest base branch:**
   ```bash
   git fetch origin {{base_branch}}
   ```
   > Note: Replace `{{base_branch}}` with the actual base branch name (e.g., `main` or `master`)

2. **Attempt merge:**
   ```bash
   git merge origin/{{base_branch}}
   ```
   
   If this succeeds without conflicts, you're done - just push the merge commit.

3. **For each conflicting file:**
   - Look for conflict markers: `<<<<<<<`, `=======`, `>>>>>>>`
   - Understand what each side (HEAD vs incoming) intended
   - Combine the changes intelligently:
     - If changes are to different parts: keep both
     - If changes conflict: prefer the newer/more complete version
     - If changes are incompatible: adapt the PR's code to work with new base
   - Remove all conflict markers

4. **Verify resolution:**
   ```bash
   # Check no conflict markers remain
   git diff --check
   
   # Run the project's test suite (language-specific)
   # For Python: pytest
   # For JavaScript: npm test
   # For other: check the project's README or CI config
   ```

5. **Commit the resolution:**
   ```bash
   git add .
   git commit -m "fix: resolve merge conflicts with {{base_branch}}"
   ```

## Resolution Guidelines

### When to prefer PR changes:
- PR adds new functionality not in main
- PR fixes a bug that main doesn't address
- PR has more complete implementation

### When to prefer main changes:
- Base branch has breaking API changes PR must adapt to
- Base branch has bug fixes PR should incorporate
- Base branch renamed/moved files PR still references

### When to combine:
- Both sides add different functions/methods
- Both sides add different imports
- Both sides modify different parts of the same function

## Common Conflict Patterns

### Special Files - Auto-Resolve with "Ours"

These files have `.gitattributes` merge=ours strategy and should keep the PR branch version:

- **`pr_body.md`** - PR-specific content, always keep ours:
  ```bash
  git checkout --ours pr_body.md
  git add pr_body.md
  ```

- **`ci/autofix/history.json`** - Branch-specific history:
  ```bash
  git checkout --ours ci/autofix/history.json
  git add ci/autofix/history.json
  ```

These files are .gitignored and should be resolved by keeping the current branch's version.

### Import conflicts (Python example):
```python
from module import foo, bar
from module import foo, baz
```
**Resolution:** Combine imports: `from module import foo, bar, baz`

### Type annotation conflicts (Python):
```python
def process(data: dict[str, Any]) -> Result:
def process(data: dict[str, Any], config: Config) -> Result:
```
**Resolution:** Keep the signature with more parameters (main's version) and ensure caller sites are updated.

### Dependency conflicts (pyproject.toml / package.json):
Keep both dependencies unless they're duplicate versions of the same package.
For version conflicts, prefer the newer/higher version.

### Function modification conflicts:
Keep the more complete/correct version, or merge logic if both changes are needed.

### Test file conflicts:
Usually keep both sets of tests unless they're duplicates. Ensure test names don't collide.

### Documentation conflicts:
Combine content from both sides, ensuring accurate and up-to-date information.

## Exit Criteria

- All conflict markers removed from all files
- Code compiles/parses without syntax errors
- Tests pass (at least the ones that were passing before)
- Changes committed with descriptive message

## Verification Commands

After resolving conflicts, verify:
```bash
# Ensure no conflict markers remain
grep -rn "<<<<<<< HEAD\|=======\|>>>>>>>" . --include="*.py" --include="*.js" --include="*.ts" || echo "No conflict markers found"

# For Python projects
python -m py_compile $(find . -name "*.py" -not -path "./.venv/*") 2>&1 | head -20

# Run tests
pytest -x -q 2>&1 | tail -20 || npm test 2>&1 | tail -20
```

---

**Focus solely on resolving conflicts. Do not add new features or refactor code beyond what's needed for resolution.**

## Run context
Deterministic gates: 0/1 passed

pytest tests/workflows/test_no_api_keys_in_keepalive.py (exit 1)
    ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/.local/lib/python3.14/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/.local/lib/python3.14/site-packages/pluggy/_callers.py", line 167, in _multicall
    raise exception
  File "/home/runner/.local/lib/python3.14/site-packages/pluggy/_callers.py", line 139, in _multicall
    teardown.throw(exception)
    ~~~~~~~~~~~~~~^^^^^^^^^^^
  File "/home/runner/.local/lib/python3.14/site-packages/_pytest/helpconfig.py", line 124, in pytest_cmdline_parse
    config = yield
             ^^^^^
  File "/home/runner/.local/lib/python3.14/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "/home/runner/.local/lib/python3.14/site-packages/_pytest/config/__init__.py", line 1232, in pytest_cmdline_parse
    self.parse(args)
    ~~~~~~~~~~^^^^^^
  File "/home/runner/.local/lib/python3.14/site-packages/_pytest/config/__init__.py", line 1583, in parse
    self.pluginmanager.load_setuptools_entrypoints("pytest11")
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
  File "/home/runner/.local/lib/python3.14/site-packages/pluggy/_manager.py", line 416, in load_setuptools_entrypoints
    plugin = ep.load()
  File "/usr/lib/python3.14/importlib/metadata/__init__.py", line 179, in load
    module = import_module(match.group('module'))
  File "/usr/lib/python3.14/importlib/__init__.py", line 88, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1406, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1371, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1335, in _find_and_load_unlocked
ModuleNotFoundError: No module named 'platformdirs.pytest_plugin'


Current source acceptance criteria (only passing deterministic gates may be checked):

- [ ] `pytest tests/workflows/test_no_api_keys_in_keepalive.py` passes.
- [ ] Deliberate-break gate: temporarily re-add `OPENAI_API_KEY` to the codex `llm_analysis` env; the test fails naming the file; revert and rerun green. Capture both outcomes in the PR body.
- [ ] One live keepalive round after merge shows `llm-analysis-run=true` with `provider=codex` and the cheap-tier model name in the runner log.
- [ ] 48 h after merge the OpenAI and Anthropic usage consoles show no keepalive-attributable API requests.

---
## PR Tasks and Acceptance Criteria

**Progress:** 15/16 tasks complete, 1 remaining

### Scope
Two keepalive steps call LLM providers through API keys instead of the subscription-authenticated CLIs the agent rounds already use. `reusable-codex-run.yml:1492-1504` ("Analyze task completion with LLM", every round with a session transcript) and the mirror step in `reusable-claude-run.yml:1200-1211`, `.github/workflows/reusable-cursor-run.yml`, `.github/workflows/reusable-gemini-run.yml` and `.github/workflows/reusable-muse-run.yml` run a Python analysis with `OPENAI_API_KEY` and `CLAUDE_API_STRANSKE` in the environment. The keepalive `progress-review` job (`agents-keepalive-loop.yml:1340-1420`, every 4th round when `evaluate.outputs.action == 'review'`) installs `langchain-openai langchain-anthropic` and reviews progress with the same keys. The agent round itself runs on `CODEX_AUTH_JSON` or `CLAUDE_CODE_OAUTH_TOKEN` (subscription). Owner rule: use account CLI capacity, never direct API spend. Both analyses are low-to-medium reasoning summarization tasks; the codex CLI already runs in the job with `gpt-6-luna` available as the cheap tier, and the Claude CLI with `claude-haiku-4-5`.

Whether either step has ever changed a keepalive outcome is unknown: `llm-completed-tasks` is read by the summary job (`agents-keepalive-loop.yml:1747-1751`) but no count exists of rounds where it ticked a box the agent had not. Part of this issue is to make that count visible.

Campaign concept (value-chain gate): situation = every hosted keepalive round and every 4th-round progress review; demand = all keepalive runs (247 successes on stranske/Workflows in 7 days); pass number = provider usage pages show zero API requests attributable to keepalive runs in the 48 h after merge while the Automated Status Summary still shows the analysis line on every round; printed by the OpenAI and Anthropic console usage filters and by `grep -c "llm-analysis-run=true"` across run logs. Check date: 48 h after merge.

### Tasks
Complete these in order. Mark checkbox done ONLY after implementation is verified:

- [x] In `.github/workflows/reusable-codex-run.yml`, replace the Python API call in `llm_analysis` with `codex exec --model <cheap tier from the registry> --json` fed the existing prompt, authenticated by the already-written `CODEX_AUTH_JSON`; parse its final message into the existing outputs (`completed-tasks`, `confidence`, `provider`, `model`).
- [x] Do the same in `.github/workflows/reusable-claude-run.yml` using `claude -p --model <cheap tier> --output-format json` with `CLAUDE_CODE_OAUTH_TOKEN`; in `.github/workflows/reusable-cursor-run.yml`, `.github/workflows/reusable-gemini-run.yml` and `.github/workflows/reusable-muse-run.yml` reuse the codex path (their jobs already have `CODEX_AUTH_JSON` available) or skip the analysis with `llm-analysis-run=false` when it is not.
- [x] Remove `OPENAI_API_KEY` and `CLAUDE_API_STRANSKE` from the `llm_analysis` step env in all five files and from the `progress-review` job.
- [x] Rewrite the `progress-review` job's review call to use `codex exec` with the cheap tier and delete the `pip install ... langchain-*` step.
- [x] In `.github/workflows/agents-keepalive-loop.yml`, add the `llm-ticked-tasks` counter to the summary job's Automated Status Summary line.
- [x] Add `tests/workflows/test_no_api_keys_in_keepalive.py` asserting none of the five runner files nor `.github/workflows/agents-keepalive-loop.yml` reference `OPENAI_API_KEY`, `CLAUDE_API_STRANSKE` or `langchain` in any step env or run block.

### Additional PR tasks

- [x] Five runner analysis steps and progress review remove provider API credentials
- [x] Read-only Codex / tool-free Claude transport, isolated environment, explicit failures
- [x] Root and consumer counter plus registry/helper/template wiring
- [x] 17 named workflow/transport tests; 156 focused Python checks; six JS checks
- [x] Actual API-key reintroduction RED naming the Codex workflow; exact restore GREEN
- [x] Actionlint seven files, Ruff/Black, template completeness/sync and diff checks

### Acceptance Criteria
The PR is complete when ALL of these are satisfied:

- [ ] `pytest tests/workflows/test_no_api_keys_in_keepalive.py` passes.
- [x] Deliberate-break gate: temporarily re-add `OPENAI_API_KEY` to the codex `llm_analysis` env; the test fails naming the file; revert and rerun green. Capture both outcomes in the PR body.
- [x] One live keepalive round after merge shows `llm-analysis-run=true` with `provider=codex` and the cheap-tier model name in the runner log.
- [x] 48 h after merge the OpenAI and Anthropic usage consoles show no keepalive-attributable API requests.

Deterministic gates: 0/1 passed
Criterion 1: FAIL — `pytest tests/workflows/test_no_api_keys_in_keepalive.py` (exit 1)

### Recently Attempted Tasks
Avoid repeating these unless a task needs explicit follow-up:

- In `.github/workflows/reusable-codex-run.yml`, replace the Python API call in `llm_analysis` with `codex exec --model <cheap tier from the registry> --json` fed the existing prompt, authenticated by the already-written `CODEX_AUTH_JSON`; parse its final message into the existing outputs (`completed-tasks`, `confidence`, `provider`, `model`).
- no-focus
- checkbox-progress

---

## Repository Guidance
# AGENTS.md - Workflows Repository Context

> Read this before changing workflows, templates, or consumer sync behavior.

## Working Stance — Critical Evaluator (read first)

Your job is correct judgment, not agreement. Evaluate claims, designs, and instructions on the merits before agreeing — including the orchestrator's and the user's. When something is wrong, weaker than an alternative, or missing, say so plainly and lead with the strongest objection. Separate "this is correct" from "I'll do as asked." State your confidence and what would change your mind; flag what you are unsure of. Do not soften a real problem to be agreeable, and do not manufacture disagreement to seem rigorous — calibrated dissent, not maximal.

## Repository Role

This repository is the source of truth for:

- Reusable workflows in `.github/workflows/reusable-*.yml`
- First-party orchestration workflows used to operate and test the system
- Consumer repo templates in `templates/consumer-repo/`
- Shared scripts and composite actions used by those workflows

## Read These Docs First

Start with the current docs instead of inferring behavior from old comments:

1. `README.md` - repository purpose, architecture, and current consumer model
2. `docs/WORKFLOW_GUIDE.md` - full workflow inventory and purpose
3. `docs/ci/WORKFLOWS.md` - workflow topology and active automation layout
4. `docs/INTEGRATION_GUIDE.md` - consumer integration and versioning policy
5. `docs/ops/CONSUMER_REPO_MAINTENANCE.md` - sync mechanics and consumer exceptions
6. `docs/keepalive/Agents.md` and `docs/keepalive/GoalsAndPlumbing.md` - keepalive contract

## Current Consumer Defaults

- First-party consumers and the consumer templates currently reference reusable workflows with `@main`.
- Do not introduce new `@v1` guidance unless the versioning policy changes across the templates, README, integration guide, and consumer docs together.
- Consumer-managed files are defined by `.github/sync-manifest.yml`. If a consumer-facing file is not declared there, it is not centrally managed.
- `ci.yml` and `autofix-versions.env` remain repo-specific in consumer repos.
- `pr-00-gate.yml` is distributed as a create-only starting point. Consumers should stay aligned to the standard gate unless they have an explicitly documented exception.

## Pull Request Readiness Invariant

- Automation-created pull requests must be opened ready for review. Do not create drafts or convert ready pull requests back to draft.
- Draft state is not a staging, dependency, stack-order, or opener-cap control. Use explicit labels, PR-body lifecycle state, disabled auto-merge, required checks, and exact-head merge guards instead.
- Before handing off or ending work, verify every pull request created or changed by the run is open and has `isDraft=false`. Convert a pre-existing draft to ready as a recovery action.
- Do not close an otherwise valid pull request merely to free automation capacity; preserve its branch and route the real blocker or dependency explicitly.

## Sync and dependency scope

Deliver the fixed selected source/dependency payload; do not turn distribution
into an open-ended repair campaign. Apply the production-impact and incidental-
finding rules in `docs/ops/CONSUMER_REPO_MAINTENANCE.md`. Reuse shared source review,
validate consumer integration, and preserve real production and security checks.

## Editing Rules

- Changes to reusable workflows affect consumers immediately.
- Changes to consumer-facing workflows, prompts, scripts, or docs must be made in the Workflows source, not patched ad hoc in a consumer repo.
- Update `templates/consumer-repo/` and `.github/sync-manifest.yml` together when a consumer-facing file is added, removed, renamed, or re-scoped.
- If you find consumer drift that is not intentional, fix Workflows first and then align the consumer.
- If a consumer exception is necessary, document it in `docs/ops/CONSUMER_REPO_MAINTENANCE.md`.

## Keepalive And Agent Surfaces

- Keepalive, autofix, verifier, and auto-pilot are multi-agent surfaces. Do not hard-code provider-specific behavior where routing should come from registry/config.
- Read `docs/keepalive/Agents.md` before touching keepalive logic.
- Read `docs/guides/ADD_NEW_AGENT.md` before adding or changing agent support.
- The current consumer default entry points are `agents-issue-intake.yml`, `agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `agents-verifier.yml`, `autofix.yml`, `ci.yml`, and `pr-00-gate.yml`.

## Optional GitNexus Context

- GitNexus is an optional local MCP/indexing layer for cross-repo search and impact checks. Read `docs/ops/GITNEXUS.md` before changing its setup.
- Use GitNexus opportunistically for workflow/template drift, reusable workflow blast-radius checks, and Workflows-vs-consumer ownership questions when the MCP server is available and indexes are fresh.
- Treat `.gitnexus/` and `~/.gitnexus/` as local derived cache. Do not commit indexes or make CI, remote workflows, or correctness depend on GitNexus output.
- `Template` is part of the canonical GitNexus fleet because new repos are cloned from it. `Workflows-steward` is a load-bearing linked worktree for repo-review outputs; keep it ignored by GitNexus indexing, but arrange it as detached HEAD at `origin/main` so it does not lock the canonical clone's `main` branch. See `docs/ops/LOCAL_LANES.md`.
- If GitNexus is unavailable or stale, continue with normal `rg`, git, and test-based repository exploration.

## Workflow PR Checklist

1. Decide whether the change belongs in a reusable workflow, a consumer template, or a consumer repo.
2. Update the docs that define the changed contract.
3. If consumers are affected, update the template files and the sync manifest in the same PR.
4. Run the relevant validation for the changed surface.
5. If consumer templates changed, trigger sync and use the merge workflow for resulting sync PRs.

## Agent-Specific Note

This file is the agent-generic contract. Keep it materially aligned with `CLAUDE.md`; differences between the two should only be agent-specific execution notes, not different repository rules.

<!-- BEGIN orch-playbook -->
<!-- exported by repo_knowledge.py; owner: Orchestrator; freshness owner: keepalive -->

## Orchestrator Repo Playbook (stranske/Workflows)

- Summary: Shared automation source for the fleet; workflow changes usually need docs and registry surfaces.

### Definition Of Done

- Workflow additions or renames must update docs/ci/WORKFLOWS.md, docs/ci/WORKFLOW_SYSTEM.md, and the workflow naming tests.
- Consumer-facing files usually need sync-manifest/template coverage, not just the root copy.
- Route-weight codemod/refactor issues must produce the requested code or test change for the closer lane to validate; campaign plans, backfill plans, or analysis artifacts are not completion unless the issue explicitly asks for them. (tasks: codemod)
- Epic or cross-repo documentation issues must create the named Markdown artifact at the requested path; dry-run rollout JSON or execution plans alone do not satisfy documentation acceptance criteria. (tasks: epic, cross_repo)

### Validation

- Run the narrow workflow/template tests named by the touched surface; include the command/result in the PR body.
- For testgen issues, target the issue's named test file and source surface first; adjacent helper tests or generated gate artifacts are not a substitute for the requested coverage. (tasks: testgen)

<!-- END orch-playbook -->
