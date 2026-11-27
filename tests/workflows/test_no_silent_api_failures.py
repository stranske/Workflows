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
const { createHash } = require('node:crypto');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const reads = [], writes = [], failures = [], messages = [], changes = [];
const {scenario, sha, branch} = input;
const throwHttp = (status) => { throw Object.assign(new Error(`HTTP ${status}`), {status}); };
const blob = (content) => {
  const bytes = Buffer.from(content);
  return createHash('sha1').update('blob ' + bytes.length + '\\0').update(bytes).digest('hex');
};
const snapshot = new Map(input.tree.map((entry) => [entry.path, entry]));
const commits = { [sha]: { tree: {sha: 'base-tree'} } };
const trees = { 'base-tree': input.tree };
let liveHead = null;
let activePull;
let baseReads = 0;
const repos = {
  async getBranch({branch}) {
    if (branch !== 'main') throw new Error('unexpected base');
    if (scenario === 'branch-denied') throwHttp(403);
    baseReads++;
    const observed = scenario === 'base-drift' && baseReads > 2 ? 'new-base' : sha;
    return {data: {protected: input.protected, commit: {sha: observed}}};
  },
  async getContent({path, ref}) {
    reads.push([path, ref]);
    const status = input.reads[path];
    if (status !== 200) throwHttp(status);
    return {data: {
      type: 'file', encoding: 'base64', sha: snapshot.get(path).sha,
      content: path === '.gitignore' ? Buffer.from(input.ignore).toString('base64') : '',
    }};
  },
  async deleteFile({path, branch}) {
    if (input.protected || branch !== 'main') throw new Error('unexpected direct delete');
    writes.push(['delete', path]);
    if (scenario === 'direct-failure') throwHttp(403);
  },
  async createOrUpdateFileContents({path, sha, branch}) {
    if (input.protected || branch !== 'main') throw new Error('unexpected direct edit');
    writes.push([sha ? 'update' : 'create', path]);
  },
};
const git = {
  async getRef({ref}) {
    if (ref !== 'heads/' + branch) throw new Error('unexpected ref');
    if (!liveHead) throwHttp(404);
    return {data: {ref: 'refs/heads/' + branch, object: {sha: liveHead}}};
  },
  async getCommit({commit_sha}) { return {data: commits[commit_sha]}; },
  async getTree({tree_sha}) { return {data: {tree: trees[tree_sha], truncated: false}}; },
  async createTree({base_tree, tree}) {
    if (base_tree !== 'base-tree') throw new Error('unexpected base tree');
    changes.splice(0, changes.length, ...tree);
    writes.push(['tree']);
    const entries = new Map(snapshot);
    for (const {path, mode, type, sha, content} of tree) {
      if (sha === null) entries.delete(path);
      else entries.set(path, {path, mode, type, sha: blob(content)});
    }
    trees['new-tree'] = [...entries.values()];
    return {data: {sha: 'new-tree'}};
  },
  async createCommit({message, tree, parents}) {
    writes.push(['commit']);
    commits['new-commit'] = {message, tree: {sha: tree}, parents: parents.map(sha => ({sha}))};
    return {data: {sha: 'new-commit'}};
  },
  async createRef({ref, sha}) {
    if (ref !== 'refs/heads/' + branch) throw new Error('attempt to publish unrelated ref');
    if (liveHead) throwHttp(422);
    writes.push(['ref', ref]);
    liveHead = sha;
    if (scenario === 'lost-ref-receipt') throwHttp(502);
  },
};
const pulls = {
  async list({head, state}) {
    if (head !== input.repo.split('/')[0] + ':' + branch || state !== 'all') {
      throw new Error('unbounded PR search');
    }
    return {data: activePull ? [activePull] : []};
  },
  async create({head, base, draft, body}) {
    if (head !== branch || base !== 'main' || draft !== false) throw new Error('unexpected PR');
    if (activePull) throwHttp(422);
    if (scenario === 'pull-forbidden' && writes.length === 3) {
      writes.push(['rejected-pull']);
      throwHttp(403);
    }
    writes.push(['pull', base, head]);
    activePull = {
      number: 1, state: 'open', draft, body, base: {ref: base},
      head: {ref: head, repo: {full_name: input.repo}, sha: liveHead},
      html_url: 'https://example.invalid/cleanup/1', labels: [],
    };
    if (scenario === 'lost-pull-receipt') throwHttp(502);
    return {data: activePull};
  },
};
const issues = {
  async addLabels({issue_number, labels}) {
    if (issue_number !== 1 || !activePull) throw new Error('unexpected cleanup PR label');
    writes.push(['labels', ...labels]);
    activePull.labels.push(...labels.map(name => ({name})));
    return {data: activePull.labels};
  },
};
if (scenario === 'foreign-ref') {
  liveHead = 'foreign';
  commits.foreign = {message: 'another writer'};
}
const core = {
  notice(message) { messages.push(message); },
  error(message) { messages.push(message); },
  setFailed(message) { failures.push(message); },
};
const github = {rest: {repos, git, pulls, issues}, paginate: async (read, params) => (await read(params)).data};
const requireStep = (path) => path === 'fs' ? {existsSync: () => false} : require(path);
const execute = () => new AsyncFunction('github', 'core', 'require', 'console', 'process', input.script)(
  github, core, requireStep, {log(message) { messages.push(message); }},
  {env: {REPO_FULL: input.repo, DRY_RUN: input.dryRun ? 'true' : 'false'}},
);
(async () => {
  if (scenario === 'concurrent') await Promise.all([execute(), execute()]);
  else {
    await execute();
    if (['repeat', 'pull-forbidden', 'closed-pull', 'drifted-pull-tree'].includes(scenario)) {
      if (scenario === 'closed-pull') activePull.state = 'closed';
      if (scenario === 'drifted-pull-tree') trees['new-tree'].push({
        path: 'other', sha: 'other', mode: '100644', type: 'blob',
      });
      await execute();
    }
  }
  process.stdout.write(JSON.stringify({reads, writes, failures, messages, changes}));
})();
"""


def _replay_maint72(
    body_status: int,
    ignore_status: int,
    ignore: str,
    dry_run: bool,
    protected: bool = False,
    scenario: str = "",
    fixture: dict | None = None,
) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to replay the github-script step")
    workflow = WORKFLOW_DIRS[0] / "maint-72-fix-pr-body-conflicts.yml"
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]
    step = next(
        step for step in jobs["fix-repos"]["steps"] if step["name"] == "Check and fix pr_body.md"
    )
    targets = {"pr_body.md": body_status, ".gitignore": ignore_status}
    if fixture is None:
        fixture = {
            "repo": "stranske/trip-planner",
            "sha": "3111111111111111111111111111111111111111",
            "tree": [
                {"path": path, "mode": "100644", "type": "blob", "sha": f"{i:040x}"}
                for i, (path, status) in enumerate(targets.items(), 1)
                if status == 200
            ],
        }
    completed = subprocess.run(
        [node, "-e", MAINT72_REPLAY],
        input=json.dumps(
            {
                **fixture,
                "script": step["with"]["script"],
                "reads": targets,
                "ignore": ignore,
                "dryRun": dry_run,
                "protected": protected,
                "scenario": scenario,
                "branch": "maintenance/maint72-pr-body",
            }
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert all(ref == fixture["sha"] for _, ref in result["reads"])
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


@pytest.mark.parametrize(
    ("scenario", "failed_attempts", "expected_refs", "expected_pulls"),
    [
        ("", 0, 1, 1),
        ("repeat", 0, 1, 1),
        ("concurrent", 0, 1, 1),
        ("lost-ref-receipt", 0, 1, 1),
        ("lost-pull-receipt", 0, 1, 1),
        ("pull-forbidden", 1, 1, 1),
        ("branch-denied", 1, 0, 0),
        ("base-drift", 1, 0, 0),
        ("foreign-ref", 1, 0, 0),
        ("closed-pull", 1, 1, 1),
        ("drifted-pull-tree", 1, 1, 1),
    ],
)
def test_maint72_protected_apply_opens_one_exact_ready_pull(
    scenario: str, failed_attempts: int, expected_refs: int, expected_pulls: int
) -> None:
    result = _replay_maint72(200, 200, "pr_body.md\n", False, True, scenario)
    operations = [kind for kind, *_ in result["writes"]]
    assert operations.count("ref") == expected_refs
    assert operations.count("pull") == expected_pulls
    assert operations.count("labels") == expected_pulls
    assert not set(operations) & {"delete", "update", "create"}
    assert len(result["failures"]) == failed_attempts
    if expected_pulls:
        assert result["changes"] == [
            {"path": "pr_body.md", "mode": "100644", "type": "blob", "sha": None}
        ]
        assert any("Cleanup PR ready for normal review" in line for line in result["messages"])


def test_maint72_protected_apply_updates_both_files_in_one_commit() -> None:
    result = _replay_maint72(200, 200, "*.pyc\n", False, True)
    assert result["failures"] == []
    assert [path["path"] for path in result["changes"]] == ["pr_body.md", ".gitignore"]
    assert result["changes"][1]["content"].startswith("*.pyc\n")
    assert result["changes"][1]["content"].endswith("\npr_body.md\n")
    assert [kind for kind, *_ in result["writes"]] == ["tree", "commit", "ref", "pull", "labels"]


def test_maint72_failed_direct_apply_does_not_claim_repair() -> None:
    result = _replay_maint72(200, 200, "pr_body.md\n", False, scenario="direct-failure")
    assert len(result["failures"]) == 1
    assert not any("Fixed -" in line for line in result["messages"])
