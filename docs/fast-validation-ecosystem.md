<a id="fast-validation-ecosystem-for-codex-development"></a>

# Local validation for editor users

<a id="overview"></a>
<a id="validation-tools"></a>
<a id="1-dev_checksh---ultra-fast-development-validation"></a>
<a id="2-validate_fastsh---intelligent-adaptive-validation"></a>
<a id="3-quick_checksh---legacy-quick-validation"></a>
<a id="4-check_branchsh---comprehensive-validation"></a>
<a id="5-fix_common_issuessh---auto-fix-common-problems"></a>
<a id="recommended-workflows"></a>
<a id="1-active-development-workflow"></a>
<a id="2-pre-commit-workflow"></a>
<a id="3-pre-push-workflow"></a>
<a id="4-codex-integration-workflow"></a>
<a id="performance-optimization"></a>
<a id="speed-comparison"></a>
<a id="optimization-tips"></a>
<a id="file-level-optimizations"></a>
<a id="customization"></a>
<a id="environment-variables"></a>
<a id="configuration-files"></a>
<a id="best-practices"></a>

Use the [local validation guide](validation/overview.md#quick-reference) to choose
a command for changed files, outgoing commits or a full branch check. Its
[command examples](validation/overview.md#common-workflows) show how to select
the commit range and when to use `--fix`.

<a id="git-hooks-integration"></a>
<a id="setup"></a>
<a id="installed-hooks"></a>
<a id="bypassing-hooks"></a>
<a id="performance-issues"></a>
<a id="hook-issues"></a>

For pre-commit and pre-push checks, follow the [Git hooks guide](git-hooks/overview.md#installation).
It includes the configured hooks and how to run each stage by hand.

<a id="integration-with-ides"></a>
<a id="vs-code"></a>
<a id="command-palette-integration"></a>

## Run a check from VS Code

Open the repository root as your workspace. Add this task to the `tasks` array
in `.vscode/tasks.json`, then select **Tasks: Run Task → Check changed files**.

```json
{
  "label": "Check changed files",
  "type": "shell",
  "command": "./scripts/dev_check.sh",
  "args": ["--changed"],
  "options": { "cwd": "${workspaceFolder}" },
  "problemMatcher": []
}
```

<a id="error-handling"></a>
<a id="common-issues-and-solutions"></a>
<a id="debugging-validation"></a>
<a id="troubleshooting"></a>

If a tool or hook fails, see [validation troubleshooting](validation/overview.md#troubleshooting)
or [hook troubleshooting](git-hooks/overview.md#troubleshooting).
