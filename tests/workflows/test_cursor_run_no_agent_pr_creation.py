"""Keep Cursor on the existing PR and retain work when that PR closes mid-run."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-cursor-run.yml"


def test_cursor_cannot_create_prs_and_every_push_requires_an_open_target():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["cursor"]["steps"]
    run_index = next(i for i, step in enumerate(steps) if step.get("id") == "run_cursor")
    for token in ("GH_TOKEN", "GITHUB_TOKEN", "WORKFLOWS_TOKEN"):
        assert steps[run_index]["env"].get(token) == "", f"Run Cursor must clear {token}"

    gate_index = next(i for i, step in enumerate(steps) if step.get("id") == "target_pr")
    gate = steps[gate_index]
    assert run_index < gate_index
    assert "always()" in gate["if"]
    assert gate["env"]["PR_NUMBER"] == "${{ inputs.pr_number }}"
    assert "github.rest.pulls.get" in gate["with"]["script"]
    assert "pull.state === 'open'" in gate["with"]["script"]
    pushes = [i for i, step in enumerate(steps) if "git push " in step.get("run", "")]
    assert pushes, "Expected the existing workflow push paths"
    for push_index in pushes:
        assert gate_index < push_index
        assert "steps.target_pr.outputs.push_allowed == 'true'" in steps[push_index].get("if", "")


def test_source_issue_comment_permissions_and_prompt_mirror():
    callers = [
        WORKFLOW,
        ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
    ]
    for path in callers:
        assert yaml.safe_load(path.read_text())["permissions"]["issues"] == "write", path
    for name, job in (
        ("agents-keepalive-loop.yml", "run-cursor"),
        ("agents-autofix-loop.yml", "autofix-cursor"),
    ):
        caller = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        assert caller["permissions"].get("issues") != "write", name
        permissions = caller["jobs"][job]["permissions"]
        assert permissions["issues"] == "write", name
        # Explicit job permissions must preserve everything required by the callee.
        for scope, access in yaml.safe_load(WORKFLOW.read_text())["permissions"].items():
            assert permissions[scope] == access, (name, scope)
    prompt = Path(".github/codex/prompts/keepalive_next_task.md")
    instruction = (
        b"Do not create branches or pull requests; commit only to the checked-out PR branch."
    )
    for base in (ROOT, ROOT / "templates/consumer-repo"):
        assert instruction in (base / prompt).read_bytes()
    # Reusable workflows are consumed directly from Workflows, not copied.
    assert not (ROOT / "templates/consumer-repo/.github/workflows" / WORKFLOW.name).exists()


@pytest.mark.parametrize(
    "scenario",
    [
        "open",
        "merged",
        "closed",
        "duplicate",
        "no-commits",
        "no-issue",
        "no-pr",
        "api-error",
        "transient-then-open",
        "not-found",
        "comment-error",
    ],
)
def test_target_pr_guard_executes_with_real_unpushed_commits(tmp_path, scenario):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Cursor fixture")
    git("config", "user.email", "cursor@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "PR checkout", "--allow-empty")
    start = git("rev-parse", "HEAD")
    shas = []
    if scenario != "no-commits":
        for message in ("leftover one", "leftover two"):
            git("-c", "core.hooksPath=/dev/null", "commit", "-qm", message, "--allow-empty")
            shas.append(git("rev-parse", "HEAD"))

    # Execute the actual workflow JavaScript, including the real source resolver.
    helper = tmp_path / ".workflows-lib/.github/scripts/source_context.js"
    helper.parent.mkdir(parents=True)
    helper.symlink_to(ROOT / ".github/scripts/source_context.js")
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["cursor"]["steps"]
    script = next(step for step in steps if step.get("id") == "target_pr")["with"]["script"]
    harness = r"""
const fs = require('fs');
const { execFileSync } = require('child_process');
const { script, scenario } = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = { outputs: {}, comments: [], reads: [], notices: [], warnings: [], summary: '' };
const core = {
  setOutput: (key, value) => { result.outputs[key] = value; },
  info: () => {},
  notice: value => result.notices.push(value),
  warning: value => result.warnings.push(value),
  summary: {
    addRaw: value => { result.summary += value; return core.summary; },
    write: async () => {},
  },
};
const github = {
  rest: {
    pulls: { get: async args => {
      result.reads.push(args);
      if (scenario === 'api-error') throw new Error('PR lookup unavailable');
      if (scenario === 'transient-then-open' && result.reads.length === 1) {
        throw Object.assign(new Error('Bad gateway'), { status: 502 });
      }
      if (scenario === 'not-found') throw Object.assign(new Error('Not Found'), { status: 404 });
      return { data: {
        state: ['open', 'transient-then-open'].includes(scenario) ? 'open' : 'closed',
        merged: scenario === 'merged',
        body: scenario === 'no-issue' ? '' : 'Closes #4562',
      } };
    } },
    issues: {
      listComments: () => {},
      createComment: async args => {
        if (scenario === 'comment-error') throw new Error('comment rejected');
        result.comments.push(args);
      },
    },
  },
  paginate: async () => scenario === 'duplicate'
    ? [{ body: '<!-- cursor-target-closed:42:123 -->' }] : [],
};
const exec = { getExecOutput: async (file, args) => ({
  // Inherit stderr so restricted runners need only the captured stdout pipe.
  stdout: execFileSync(file, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }),
}) };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
(async () => {
  try {
    await new AsyncFunction('require', 'github', 'context', 'core', 'exec', script)(
      require, github, { repo: { owner: 'stranske', repo: 'Workflows' }, runId: 123 }, core, exec,
    );
  } catch (error) { result.error = error.message; }
  process.stdout.write(JSON.stringify(result));
})();
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": script, "scenario": scenario}),
        env={
            **os.environ,
            "PR_NUMBER": "" if scenario == "no-pr" else "42",
            "START_SHA": start,
            "GITHUB_SERVER_URL": "https://github.com",
            "RECOVERY_ARTIFACT": "cursor-blocked-delivery-123-1",
            "LOOKUP_ATTEMPTS": "3",
            "LOOKUP_DELAY_MS": "0",
        },
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    result = json.loads(completed.stdout)
    opened = scenario in {"open", "transient-then-open"}
    assert result["outputs"]["push_allowed"] == ("true" if opened else "false")
    read = {"owner": "stranske", "repo": "Workflows", "pull_number": 42}
    expected_reads = {"no-pr": 0, "api-error": 3, "transient-then-open": 2}.get(scenario, 1)
    assert result["reads"] == [read] * expected_reads
    if scenario in {"api-error", "not-found"}:
        # Exhausted (or non-transient) lookups fail the step and withhold pushes.
        assert result["error"] == (
            "PR lookup unavailable" if scenario == "api-error" else "Not Found"
        )
        assert result["comments"] == []
        assert any("blocking=target_pr_unknown" in w for w in result["warnings"])
        return
    assert "error" not in result
    if scenario == "comment-error":
        assert result["outputs"]["outcome"] == "skipped: target PR merged/closed mid-run"
        assert result["comments"] == []
        assert any("Source issue #4562 notification failed" in w for w in result["warnings"])
        return
    if opened or scenario == "no-pr":
        assert result["comments"] == []
        assert result["summary"] == ""
        return
    assert result["outputs"]["outcome"] == "skipped: target PR merged/closed mid-run"
    assert "https://github.com/stranske/Workflows/actions/runs/123" in result["summary"]
    for sha in shas:
        assert sha in result["summary"]
    assert start not in result["summary"]
    assert "Recovery artifact: `cursor-blocked-delivery-123-1`" in result["summary"]
    if scenario == "no-commits":
        assert "- None." in result["summary"]
    if scenario in {"duplicate", "no-issue"}:
        assert result["comments"] == []
        if scenario == "no-issue":
            assert result["warnings"]
    else:
        assert len(result["comments"]) == 1
        assert result["comments"][0] == {
            "owner": "stranske",
            "repo": "Workflows",
            "issue_number": 4562,
            "body": result["summary"],
        }


def _steps():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["cursor"]["steps"]


def _step(step_id):
    return next(step for step in _steps() if step.get("id") == step_id)


def _git(cwd, *args):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Cursor fixture")
    _git(path, "config", "user.email", "cursor@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "base", "--allow-empty")
    return _git(path, "rev-parse", "HEAD")


def test_pr_number_is_required_and_validated_before_cursor_executes():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    contract = workflow[True]["workflow_call"]["inputs"]["pr_number"]
    assert contract["required"] is True and "default" not in contract
    steps = _steps()
    ids = [step.get("id") for step in steps]
    validate = ids.index("target_input")
    assert validate < ids.index("run_cursor")
    first_checkout = next(
        i for i, step in enumerate(steps) if step.get("uses", "").startswith("actions/checkout@")
    )
    assert validate < first_checkout
    for step_id in ("cursor_base", "credential_isolation", "run_cursor", "target_pr"):
        assert "steps.target_input.outcome == 'success'" in _step(step_id)["if"], step_id
    assert "steps.credential_isolation.outcome == 'success'" in _step("run_cursor")["if"]
    for value, ok in [
        ("42", True),
        ("1", True),
        ("", False),
        ("0", False),
        ("-3", False),
        ("abc", False),
        ("12a", False),
        ("042", False),
        ("4 2", False),
    ]:
        completed = subprocess.run(
            ["bash", "-eo", "pipefail", "-c", steps[validate]["run"]],
            env={**os.environ, "PR_NUMBER": value},
            capture_output=True,
            text=True,
            check=False,
        )
        assert (completed.returncode == 0) is ok, (value, completed.stdout)
    for caller, job in (
        (ROOT / ".github/workflows/agents-keepalive-loop.yml", "run-cursor"),
        (ROOT / ".github/workflows/agents-autofix-loop.yml", "autofix-cursor"),
    ):
        assert "pr_number" in yaml.safe_load(caller.read_text())["jobs"][job]["with"], caller
    template = yaml.safe_load(
        (
            ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
        ).read_text()
    )
    cursor_jobs = [
        job for job in template["jobs"].values() if "reusable-cursor-run.yml" in job.get("uses", "")
    ]
    assert cursor_jobs and all("pr_number" in job["with"] for job in cursor_jobs)


def test_persisted_checkout_credentials_are_unusable_by_cursor(tmp_path):
    steps = _steps()
    ids = [step.get("id") for step in steps]
    isolation = ids.index("credential_isolation")
    assert ids.index("cursor_base") < isolation < ids.index("run_cursor")
    # Authenticated pre-run fetches keep the persisted checkout token.
    checkouts = [s for s in steps[:isolation] if s.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 2
    assert all(s["with"].get("persist-credentials", True) is not False for s in checkouts)
    # Post-run pushes keep their explicit-token URL.
    pushes = [s for s in steps[isolation:] if "git push " in s.get("run", "")]
    assert pushes
    for push in pushes:
        assert push["env"]["PUSH_TOKEN"].startswith("${{ steps.auth_token.outputs.push_token")
        assert 'REMOTE_URL="https://x-access-token:${PUSH_TOKEN}@github.com/' in push["run"]
        assert "git push origin" not in push["run"]

    workspace = tmp_path / "workspace"
    _init_repo(workspace)
    _init_repo(workspace / ".workflows-lib")
    header = "AUTHORIZATION: basic c2VjcmV0"
    _git(workspace, "config", "--local", "http.https://github.com/.extraheader", header)
    cred_file = tmp_path / "git-credentials-1234.config"
    cred_file.write_text(f'[http "https://github.com/"]\n\textraheader = {header}\n')
    lib = workspace / ".workflows-lib"
    _git(lib, "config", "--local", f"includeIf.gitdir:{lib}/.git.path", str(cred_file))
    _git(lib, "config", "--local", "http.https://github.com/.extraheader", header)
    for repo in (workspace, lib):
        assert header in _git(
            repo, "config", "--includes", "--get-all", "http.https://github.com/.extraheader"
        )

    subprocess.run(
        ["bash", "-eo", "pipefail", "-c", steps[isolation]["run"]],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    for repo in (workspace, lib):
        leftover = subprocess.run(
            ["git", "config", "--includes", "--get-regexp", r"^http\..*\.extraheader$"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert leftover.returncode == 1 and header not in leftover.stdout, repo
        assert "includeif" not in _git(repo, "config", "--local", "--list").lower()
    assert not cred_file.exists()
    # Rerunning on clean checkouts (or without .workflows-lib) still succeeds.
    subprocess.run(
        ["bash", "-eo", "pipefail", "-c", steps[isolation]["run"]],
        cwd=workspace,
        check=True,
        capture_output=True,
    )


def test_blocked_delivery_preserves_commits_and_working_tree(tmp_path):
    step = _step("preserve_blocked")
    assert "steps.target_pr.outputs.push_allowed != 'true'" in step["if"]
    ids = [s.get("id") for s in _steps()]
    assert ids.index("target_pr") < ids.index("preserve_blocked") < ids.index("commit")
    upload = next(
        s
        for s in _steps()
        if s.get("uses", "").startswith("actions/upload-artifact@")
        and "preserve_blocked" in s.get("if", "")
    )
    assert upload["with"]["name"] == "${{ steps.preserve_blocked.outputs.artifact }}"
    assert _step("target_pr")["env"]["RECOVERY_ARTIFACT"] == step["env"]["RECOVERY_ARTIFACT"]

    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.txt").write_text("base\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "tracked")
    start = _git(repo, "rev-parse", "HEAD")
    (repo / "agent.txt").write_text("committed by agent\n")
    _git(repo, "add", "agent.txt")
    _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "agent commit")
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "staged.txt").write_text("staged\n")
    _git(repo, "add", "staged.txt")
    (repo / "tracked.txt").write_text("base\nunstaged edit\n")
    (repo / "new dir").mkdir()
    (repo / "new dir" / "untracked file.txt").write_text("untracked\n")
    (repo / ".workflows-lib").mkdir()
    (repo / ".workflows-lib" / "ignored.txt").write_text("tooling\n")
    (repo / ".git/info/exclude").write_text(".workflows-lib\n")
    branches = _git(repo, "branch", "--list")

    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        cwd=repo,
        env={
            **os.environ,
            "START_SHA": start,
            "RECOVERY_ARTIFACT": "cursor-blocked-delivery-123-1",
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        check=True,
        capture_output=True,
        text=True,
    )
    out = runner_temp / "cursor-blocked-delivery"
    assert "artifact=cursor-blocked-delivery-123-1" in output.read_text()
    receipt = (out / "receipt.txt").read_text()
    assert "artifact=cursor-blocked-delivery-123-1" in receipt
    assert "unpushed_commits=1" in receipt and "untracked_files=1" in receipt
    assert "cursor-blocked-delivery-123-1" in summary.read_text()
    # Nothing was pushed, branched or reset in the workspace.
    assert _git(repo, "branch", "--list") == branches
    assert _git(repo, "rev-parse", "HEAD") == head

    # Recover everything into a fresh clone at the starting commit.
    restore = tmp_path / "restore"
    subprocess.check_call(["git", "clone", "-q", str(repo), str(restore)])
    _git(restore, "checkout", "-q", start)
    _git(restore, "fetch", "-q", str(out / "commits.bundle"), "HEAD")
    assert _git(restore, "rev-parse", "FETCH_HEAD") == head
    _git(restore, "checkout", "-q", "FETCH_HEAD")
    _git(restore, "apply", "--index", str(out / "staged.patch"))
    _git(restore, "apply", str(out / "unstaged.patch"))
    subprocess.check_call(["tar", "-xzf", str(out / "untracked.tar.gz")], cwd=restore)
    assert (restore / "staged.txt").read_text() == "staged\n"
    assert "staged.txt" in _git(restore, "diff", "--cached", "--name-only")
    assert (restore / "tracked.txt").read_text() == "base\nunstaged edit\n"
    assert (restore / "new dir" / "untracked file.txt").read_text() == "untracked\n"
    assert not (restore / ".workflows-lib").exists()
