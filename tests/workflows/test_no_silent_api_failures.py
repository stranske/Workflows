"""Prevent github-script REST failures from being silently reintroduced.

Issue #3017 distinguishes a deliberate warning-only API operation from a
workflow mutation that must fail the job.  The former requires an explicit
in-script ``# best-effort:`` marker; the latter must call ``core.setFailed``.
The complete current disposition is recorded in
``docs/workflows/silent-api-failure-triage.md``.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW_DIRS = (
    Path(".github/workflows"),
    Path("templates/consumer-repo/.github/workflows"),
)
API_CALL = re.compile(r"github\.(?:rest\.[A-Za-z_][\w.]*|request)\s*\(")
BEST_EFFORT = re.compile(r"#\s*best-effort:\s*\S")


def test_api_call_pattern_includes_request_dispatches() -> None:
    """The inventory must cover non-REST github-script calls too."""

    script = "await github.request('POST /repos/{owner}/{repo}/dispatches')"
    assert API_CALL.search(script) is not None
    assert API_CALL.pattern[0] == "g"


def _candidate_steps() -> list[tuple[Path, str, str, str]]:
    """Return github-script bodies that catch REST errors without failing."""

    candidates: list[tuple[Path, str, str, str]] = []
    for workflow_dir in WORKFLOW_DIRS:
        for workflow_path in sorted(workflow_dir.glob("*.y*ml")):
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
            for job_name, job in (workflow.get("jobs") or {}).items():
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    if "actions/github-script" not in str(step.get("uses", "")):
                        continue
                    script = str((step.get("with") or {}).get("script", ""))
                    if (
                        "catch" in script
                        and API_CALL.search(script)
                        and "core.setFailed" not in script
                    ):
                        candidates.append(
                            (
                                workflow_path,
                                job_name,
                                str(step.get("name", "unnamed github-script step")),
                                script,
                            )
                        )
    return candidates


def test_scripted_api_blocks_either_fail_or_are_annotated() -> None:
    """Every warning-only REST catch must say why it is safe to tolerate."""

    unannotated = [
        f"{path}:{job}:{name}"
        for path, job, name, script in _candidate_steps()
        if not BEST_EFFORT.search(script)
    ]
    assert not unannotated, (
        "github-script REST catches must fail with core.setFailed or carry a "
        "# best-effort: rationale; see docs/workflows/silent-api-failure-triage.md:\n"
        + "\n".join(unannotated)
    )


MAINT72_REPLAY = """
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const reads = [], writes = [], failures = [], messages = [];
const repos = {
  async getContent({path, ref}) {
    reads.push([path, ref]);
    const status = input.reads[path];
    if (status !== 200) {
      throw Object.assign(new Error(`HTTP ${status}`), {status});
    }
    const content = path === '.gitignore' ? input.ignore : '';
    return {data: {sha: '1234567890abcdef', content: Buffer.from(content).toString('base64')}};
  },
  async deleteFile({path}) { writes.push(['delete', path]); },
  async createOrUpdateFileContents({path, sha}) {
    writes.push([sha ? 'update' : 'create', path]);
  },
};
const core = {
  notice(message) { messages.push(message); },
  error(message) { messages.push(message); },
  setFailed(message) { failures.push(message); },
};
const replay = new AsyncFunction('github', 'core', 'require', 'console', 'process', input.script);
replay(
  {rest: {repos}}, core, () => ({existsSync: () => false}),
  {log(message) { messages.push(message); }},
  {env: {REPO_FULL: 'stranske/trip-planner', DRY_RUN: input.dryRun ? 'true' : 'false'}},
).then(() => process.stdout.write(JSON.stringify({reads, writes, failures, messages})));
"""


def _replay_maint72(body_status: int, ignore_status: int, ignore: str, dry_run: bool) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to replay the github-script step")
    workflow = WORKFLOW_DIRS[0] / "maint-72-fix-pr-body-conflicts.yml"
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]
    step = next(
        step for step in jobs["fix-repos"]["steps"] if step["name"] == "Check and fix pr_body.md"
    )
    completed = subprocess.run(
        [node, "-e", MAINT72_REPLAY],
        input=json.dumps(
            {
                "script": step["with"]["script"],
                "reads": {"pr_body.md": body_status, ".gitignore": ignore_status},
                "ignore": ignore,
                "dryRun": dry_run,
            }
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["reads"] == [["pr_body.md", "main"], [".gitignore", "main"]]
    return result


@pytest.mark.parametrize(
    ("body_status", "ignore_status", "dry_run", "unreadable", "status"),
    [
        pytest.param(403, 503, True, "pr_body.md", 403, id="both-reads-unavailable"),
        pytest.param(200, 403, False, ".gitignore", 403, id="tracked-body-unreadable-ignore"),
        pytest.param(503, 404, False, "pr_body.md", 503, id="unreadable-body-missing-ignore"),
    ],
)
def test_maint72_read_failure_prevents_recovery(
    body_status: int, ignore_status: int, dry_run: bool, unreadable: str, status: int
) -> None:
    result = _replay_maint72(body_status, ignore_status, "pr_body.md\n", dry_run)
    assert not result["writes"]
    assert result["failures"] and unreadable in result["failures"][0]
    assert f"HTTP {status}" in result["failures"][0]
    assert not any("already configured correctly" in message for message in result["messages"])
    assert not any("Would " in message or "Fixed -" in message for message in result["messages"])


@pytest.mark.parametrize(
    ("body_status", "ignore_status", "ignore", "dry_run", "message", "writes"),
    [
        pytest.param(
            404, 200, "pr_body.md\n", True, "already configured correctly", [], id="clean"
        ),
        pytest.param(200, 200, "*.pyc\n", True, "Would delete pr_body.md", [], id="preview"),
        pytest.param(
            200,
            200,
            "pr_body.md\n",
            True,
            "Would delete pr_body.md from main",
            [],
            id="native-tracked-preview",
        ),
        pytest.param(
            200,
            200,
            "*.pyc\n",
            False,
            "Fixed -",
            [["delete", "pr_body.md"], ["update", ".gitignore"]],
            id="write-opt-in",
        ),
        pytest.param(
            404, 404, "", True, "Would create .gitignore", [], id="missing-ignore-preview"
        ),
    ],
)
def test_maint72_known_reads_preserve_recovery(
    body_status: int,
    ignore_status: int,
    ignore: str,
    dry_run: bool,
    message: str,
    writes: list[list[str]],
) -> None:
    result = _replay_maint72(body_status, ignore_status, ignore, dry_run)
    assert result["failures"] == []
    assert result["writes"] == writes
    assert any(message in line for line in result["messages"])
