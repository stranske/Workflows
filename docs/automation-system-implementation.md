# Automation system implementation notes

This document consolidates implementation guidance for:
- GitHub App token-only automation (replace PATs)
- Codex GitHub Action integration
- Keepalive closed-loop iteration (no manual Codex website “Update Branch” clicking)
- Autofix that handles mypy + pytest (and more)
- Post-merge verifier + follow-up issue creation
- Security controls (prompt injection hardening, environments, CODEOWNERS)

---

## 1) What “Codex” means in your setup

You currently interact with multiple “Codex-shaped” things:

### Codex cloud (web) + @codex mentions
- This is the cloud agent experience where you can tag @codex on PRs and interact in rounds.
- It is convenient for interactive back-and-forth, but the “continue on branch” behavior may require manual clicks (Update Branch, create branch, merge branch) depending on how the integration is configured.

### Codex CLI (local)
- Runs on your machine. It can authenticate via ChatGPT plan login or via API key.
- Still “command-line” in the strict sense, but it has an interactive TUI.

### Codex GitHub Action (recommended for loops)
- Runs in GitHub Actions and installs/uses the Codex CLI internally.
- You provide an OpenAI API key secret and a prompt or prompt-file.
- This is the best primitive for “keepalive becomes a real loop”.

Key detail: the GitHub Action requires `openai-api-key` and commonly uses a `prompt-file` stored in the repo.

---

## 2) Why keepalive loops break: GitHub recursion protection and “mixed token behavior”

GitHub Actions has a safety feature:
- If your workflow makes changes using `GITHUB_TOKEN`, those changes generally do not trigger other workflows (except workflow_dispatch and repository_dispatch).
- This is intentional to prevent accidental infinite recursion.

What you experienced as “mixed token behavior” usually comes from:
- Some operations happen as your human/PAT identity (triggers downstream workflows),
- Some operations happen as `github-actions[bot]` via `GITHUB_TOKEN` (does not trigger downstream workflows),
- So the system behaves inconsistently: sometimes it loops, sometimes it dead-ends.

Solution pattern:
- Use a GitHub App installation token (or a PAT) for *the actions that must trigger other workflows*.
- Prefer GitHub App: short-lived tokens, scoped permissions, not tied to a human.

---

## 3) GitHub App: what it is (and what it is not)

### It is NOT:
- A Python file in a repo.
- A script you commit.
- Something you “pip install”.

### It IS:
- A first-class GitHub entity created in the GitHub UI under Developer settings.
- It has:
  - an App ID
  - permissions (contents, PRs, issues, actions, etc)
  - optional webhooks/events (not required if you only use it to mint tokens in Actions)
  - private keys you generate and download

### Why it’s better than PATs
- PATs are long-lived and human-bound.
- GitHub App installation tokens are short-lived and permission-scoped.
- You can rotate private keys without touching every workflow that uses it.

---

## 4) Step-by-step: create a GitHub App (UI walk-through)

1. Open GitHub in your browser.
2. Go to:
   - User account: Settings -> Developer settings -> GitHub Apps
   - OR organization settings: Organization Settings -> Developer settings -> GitHub Apps
3. Click “New GitHub App”.

### Core fields (reasonable defaults)
- GitHub App name: `agents-workflows-bot` (or similar)
- Homepage URL: your Workflows repo URL
- Webhook:
  - If you are not using webhooks, you can keep webhook “inactive” (or provide a dummy URL and uncheck Active). GitHub’s UI varies, but the goal is: no webhook processing needed.

### Repository permissions (minimal set for this system)
- Metadata: Read-only (always)
- Contents: Read & write (commit/push to PR branches, read files)
- Pull requests: Read & write (comment on PR, edit PR body if needed)
- Issues: Read & write (create follow-up issues, update issues)
- Actions: Read & write (dispatch workflows, read workflow runs)

Create the app.

### Generate a private key (this is the part you asked about)
1. In the app settings page, find “Private keys”.
2. Click “Generate a private key”.
3. A `.pem` file downloads to your machine. That file’s contents are the secret.

### Install the App on repositories
- From the app page: “Install App”
- Install to the repos you want automated:
  - Workflows
  - Workflows-Integration-Tests
  - Travel-Plan-Permission
  - Portable-Alpha-Extension-Model
  - Trend_Model_Project

### Store the App credentials as GitHub secrets (no CLI required)
In Workflows repo:
- Settings -> Secrets and variables -> Actions -> New repository secret
Add:
- `WORKFLOWS_APP_ID` = the App ID shown on the GitHub App page
- `WORKFLOWS_APP_PRIVATE_KEY` = paste the full PEM file contents

Notes:
- Yes, this is “a secret”. The difference is: it is not a permanent API token.
- The key is used only to mint short-lived installation tokens during workflow runs.

---

## 5) Minting an installation token in a workflow

Recommended: `actions/create-github-app-token@v1`.

Example snippet (use in any workflow/job that must push commits or dispatch workflows):

```yaml
- name: Mint GitHub App installation token
  id: app_token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.WORKFLOWS_APP_ID }}
    private-key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}
```
Then use it:
  - For checkout (so git push works cleanly):

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
    token: ${{ steps.app_token.outputs.token }}
```

For gh CLI:

```yaml
  - name: Example gh call
  env:
    GH_TOKEN: ${{ steps.app_token.outputs.token }}
  run: |
    gh pr comment ${{ github.event.pull_request.number }} --body "hello from bot"
```

## 6) Codex GitHub Action: how to run it (and why this avoids the CLI)

Codex GitHub Action runs inside Actions:
  - It installs Codex CLI
  - It runs codex exec using your prompt
  - It exposes outputs like final-message
Basic usage pattern:

```yaml
- name: Run Codex
  id: run_codex
  uses: openai/codex-action@v1
  with:
    openai-api-key: ${{ secrets.OPENAI_API_KEY }}
    prompt-file: .github/codex/prompts/keepalive_next_task.md
    output-file: codex-output.md
    safety-strategy: drop-sudo
    sandbox: workspace-write
```

Important operational rules:
  - Put Codex late in the job so earlier steps set up the workspace (deps, caches).
  - Keep prompts in-repo (prompt-file), so you control what Codex receives.
  - Use restrictive sandbox/safety defaults and loosen only when necessary.

## 7) “Keepalive becomes a loop”: the two mechanics that make it actually iterate

You want:
Gate green -> keepalive runs -> commits to PR branch -> Gate reruns -> repeat.

To get that reliably:

Mechanic A: Trigger keepalive on workflow_run of Gate
  - Your “Gate” workflow finishes
  - A keepalive workflow runs on that completion
  - It inspects the PR state and decides whether to run Codex

Mechanic B: Push commits using GitHub App token
  - The commit/push must be performed under an identity that can trigger workflows.
  - App installation token is the preferred identity.
If you push using GITHUB_TOKEN, you often get dead loops.

## 8) Proposed workflow skeletons (keepalive + autofix)

### 8.1 keepalive loop skeleton

```yaml
name: Agents Keepalive Loop

on:
  workflow_run:
    workflows: ["Gate"]
    types: [completed]

permissions:
  contents: write
  pull-requests: write
  actions: write

concurrency:
  group: keepalive-${{ github.event.workflow_run.id }}
  cancel-in-progress: false

jobs:
  keepalive:
    runs-on: ubuntu-latest
    steps:
      - name: Mint GitHub App token
        id: app_token
        uses: actions/create-github-app-token@v1
        with:
          app-id: ${{ secrets.WORKFLOWS_APP_ID }}
          private-key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}

      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ steps.app_token.outputs.token }}

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi

      - name: Build keepalive prompt (example placeholder)
        run: |
          # Replace with your real script that:
          # - determines PR number from workflow_run payload
          # - fetches PR body
          # - finds next unchecked task
          # - writes a small context appendix file
          echo "TODO: generate prompt context" > .github/codex/prompts/_context.md

      - name: Run Codex (keepalive next task)
        id: run_codex
        uses: openai/codex-action@v1
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          prompt-file: .github/codex/prompts/keepalive_next_task.md
          output-file: codex-output.md
          safety-strategy: drop-sudo
          sandbox: workspace-write

      - name: Commit & push changes (if any)
        run: |
          git config user.name "agents-workflows-bot[bot]"
          git config user.email "agents-workflows-bot[bot]@users.noreply.github.com"
          if [ -n "$(git status --porcelain)" ]; then
            git add -A
            git commit -m "keepalive: next iteration"
            git push
          else
            echo "No changes to commit."
          fi
```

Notes:
  - This skeleton omits PR-number extraction and tasklist parsing because your repo already has scripts and conventions. The Issue(s) in Issues.txt call for wiring those specifics in.
  - The important part is: Codex runs on a checked-out PR branch and you push the resulting commit.

### 8.2 autofix loop skeleton

Same pattern, but:
  - Trigger when Gate conclusion != success
  - Prompt contains failure summary (mypy/pytest logs)

## 9) Single label policy: how to do it without losing features

You want one label only.

Recommended:
  - Keep only agent:codex as the trigger label.
  - Put mode flags in PR body (or a small config block that Agents 63 bootstrap adds), e.g.:

```text
<!-- agent-config
keepalive: true
autofix: true
max_iterations: 4
-->
```

The loop reads that config and decides behavior:
  - Gate success -> if keepalive true -> advance tasks
  - Gate failure -> if autofix true -> attempt fix

## 10) Verifier after merge: stop accepting “agent said so” as proof

Workflow:
  - On merge, checkout main at that merge commit.
  - Run:
    - tests
    - mypy
    - any smoke checks
  - Optionally run Codex in review/verifier mode to produce a structured report.
  - If verifier says “not met”, open a follow-up issue immediately.

This is the piece that prevents “agents closed the loop but reality disagrees”.

## 11) Prompt injection safety: do more than “human approved Issues.txt”

Human approval helps, but also:
  - Only run agent workflows for trusted events (not forks).
  - Prefer prompt-file that lives in repo.
  - Add allowlists for who can trigger Codex action.
  - Sanitize any user-provided text you include in the prompt appendix.
  - Use environments + CODEOWNERS to protect .github/workflows/** and other sensitive areas.

## 12) How this affects your existing @codex habit

If you keep using @codex mentions on PRs, you can continue doing so.
The Codex GitHub Action path is separate:
  - It runs via GitHub Actions using OPENAI_API_KEY.
  - It does not depend on your ChatGPT web session.
  - It is the better primitive for “closed loop iteration” because it runs in the same branch checkout that can be committed and pushed.

## 13) Reference prompts (starter templates)

Create these files:
  - .github/codex/prompts/keepalive_next_task.md
  - .github/codex/prompts/autofix_from_ci_failure.md
  - .github/codex/prompts/verifier_acceptance_check.md
Example: keepalive prompt template

```markdown

# Keepalive: execute the next unchecked task

You are working on a GitHub PR branch checked out in a CI runner.

Rules:
- Make the smallest change that advances the next unchecked task.
- Run the project’s standard checks locally before finishing.
- Update the PR task list by checking off completed items (if you have a script to do so, use it).
- Do NOT modify .github/workflows/** unless explicitly instructed in this repo’s agent policy.

Context:
- See .github/codex/prompts/_context.md for the PR task list excerpt and repo-specific notes.

Commands to run (adjust to repo):
- python -m pytest
- python -m mypy src
- python -m ruff check .
```

## 14) UI-only: how to add these files without command line

To add Issues.txt:
  - Open the Workflows repo on GitHub
  - Click “Add file” -> “Create new file”
  - Name it Issues.txt
  - Paste the Issues.txt content
  - Commit to a new branch and open a PR (recommended)
To add the docs file:
  - “Add file” -> “Create new file”
  - Name it docs/automation-system-implementation.md
  - Paste the doc content
  - Commit to the same branch/PR

```markdown

---

## What to do next (no CLI, no mystery rituals)

1) **Create a branch PR in Workflows repo** that adds:
- `Issues.txt`
- `docs/automation-system-implementation.md`

2) **Run Agents 63** on that `Issues.txt` to materialize the issues.

3) Start with the smallest high-leverage implementation order:
- **GitHub App token minting** (Issue 1)  
- **Reusable Codex runner wrapper** (Issue 2)  
- **Keepalive loop** (Issue 3)  
Then autofix + verifier.

And yes: the “keepalive becomes a real loop” part is absolutely implementable with the GitHub Action + App token pattern. Codex Action is explicitly designed to run Codex from workflows with prompt files and safe sandboxing.   
The App token solves the recursion problem GitHub documents with `GITHUB_TOKEN`. 
::contentReference[oaicite:4]{index=4}
```


