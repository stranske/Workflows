import json
import pathlib
import re

import yaml
from scripts.generate_consumer_renovate_ownership import OWNER_EXCLUDED_REPOS
from scripts.list_registered_consumer_repos import extract_repos

WORKFLOW_ROOT = pathlib.Path(".github/workflows")
SYNC_MANIFEST = pathlib.Path(".github/sync-manifest.yml")
SYNC_WORKFLOW = WORKFLOW_ROOT / "maint-68-sync-consumer-repos.yml"
OWNERSHIP_PRESET = pathlib.Path("renovate-presets/consumer-managed-paths.json")
ACTIVE_DEPENDENCY_BOT_WORKFLOWS = (
    WORKFLOW_ROOT / "maint-auto-label-dep-prs.yml",
    WORKFLOW_ROOT / "maint-auto-lock-deps.yml",
)
RETIRED_CONSUMER_AUTOMERGE = pathlib.Path(
    "templates/consumer-repo/.github/workflows/dependabot-automerge.yml"
)


def _renovate_disabled_paths(repo: str) -> set[str]:
    preset = json.loads(OWNERSHIP_PRESET.read_text(encoding="utf-8"))
    paths: set[str] = set()
    for rule in preset["packageRules"]:
        if repo in rule["matchRepositories"]:
            paths.update(rule["matchFileNames"])
    return paths


def _workflow_source(path: pathlib.Path) -> str:
    assert path.exists(), f"Expected workflow file to exist: {path}"
    return path.read_text(encoding="utf-8")


def test_dependency_bot_workflows_gate_on_pr_author_not_trigger_actor():
    for workflow in ACTIVE_DEPENDENCY_BOT_WORKFLOWS:
        source = _workflow_source(workflow)
        assert "github.event.pull_request.user.login" in source
        assert "github.actor == 'dependabot[bot]'" not in source
        assert "github.actor == 'renovate[bot]'" not in source


def test_auto_label_concurrency_is_scoped_to_pr_number():
    workflow = yaml.safe_load(_workflow_source(WORKFLOW_ROOT / "maint-auto-label-dep-prs.yml"))
    assert workflow["concurrency"] == {
        "group": "${{ github.workflow }}-${{ github.event.pull_request.number }}",
        "cancel-in-progress": True,
    }


def test_auto_lock_separates_pr_resolution_from_publication():
    workflow = yaml.safe_load(_workflow_source(WORKFLOW_ROOT / "maint-auto-lock-deps.yml"))
    trigger = workflow[True]["pull_request"]
    assert trigger["branches"] == ["main"]
    assert set(trigger["paths"]) == {
        "pyproject.toml",
        "requirements.txt",
        "tools/requirements-llm.txt",
    }
    assert workflow["permissions"] == {"contents": "read"}
    resolve = workflow["jobs"]["regenerate-lock"]
    assert "permissions" not in resolve
    assert "github.event.pull_request.head.repo.full_name == github.repository" in resolve["if"]
    for bot in ("renovate", "dependabot"):
        assert f"'{bot}[bot]' && startsWith(github.head_ref, '{bot}/')" in resolve["if"]
    assert resolve["steps"][0]["with"] == {
        "ref": "${{ github.event.pull_request.head.sha }}",
        "persist-credentials": False,
    }
    artifact = resolve["steps"][-1]
    assert artifact["if"] == "steps.check.outputs.needs_update == 'true'"
    assert artifact["with"]["path"] == "requirements.lock"
    writer = workflow["jobs"]["publish-lock"]
    assert writer["needs"] == "regenerate-lock"
    assert writer["if"] == "needs.regenerate-lock.outputs.needs_update == 'true'"
    assert writer["permissions"] == {"contents": "write", "pull-requests": "read"}
    checkout, client, download, publish = writer["steps"]
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    assert client["with"] == {"github_token": "${{ github.token }}"}
    assert download["with"]["name"] == artifact["with"]["name"]
    assert publish["uses"].startswith("actions/github-script@")


def test_retired_consumer_dependabot_automerge_template_stays_removed():
    assert not RETIRED_CONSUMER_AUTOMERGE.exists()

    manifest = yaml.safe_load(SYNC_MANIFEST.read_text(encoding="utf-8")) or {}
    removal_targets = {entry.get("target") for entry in manifest.get("removals", [])}
    assert ".github/workflows/dependabot-automerge.yml" in removal_targets


def test_consumer_renovate_cannot_edit_maint68_owned_workflows():
    """Consumer Renovate must not touch workflow files Maint 68 overwrites.

    Both paths below produced consumer Renovate PRs (Inv-Man-Intake#838,
    Manager-Database#1347) that were closed unmerged because the next sync
    reverts them.
    """
    consumers = [
        repo
        for repo in extract_repos(SYNC_WORKFLOW)
        if repo != "stranske/Workflows" and repo.casefold() not in OWNER_EXCLUDED_REPOS
    ]
    assert consumers

    for repo in consumers:
        disabled = _renovate_disabled_paths(repo)
        assert ".github/workflows/agents-guard.yml" in disabled
        assert ".github/workflows/maint-76-claude-code-review.yml" in disabled


def test_claude_review_action_digest_is_pinned_in_managed_source():
    manifest = yaml.safe_load(SYNC_MANIFEST.read_text(encoding="utf-8")) or {}
    path = ".github/workflows/maint-76-claude-code-review.yml"
    assert any(entry.get("source") == path for entry in manifest.get("workflows", []))
    source = _workflow_source(pathlib.Path("templates/consumer-repo") / path)
    assert re.search(r"uses: anthropics/claude-code-action@[0-9a-f]{40} # v1\b", source)


def test_consumer_owned_ci_workflow_stays_renovate_eligible():
    """`ci.yml` is `sync_mode: create_only`, so each consumer owns its copy.

    `autofix.yml` is deliberately absent from this assertion: the live manifest
    (`.github/sync-manifest.yml`) declares it with no `sync_mode`, which makes it
    overwrite-managed in every consumer, and the template ships pinned
    `actions/checkout` / `actions/github-script` SHAs that a consumer Renovate
    would bump and Maint 68 would then revert. Adding a hand-written exemption
    for it would stop the preset being manifest-derived. It stays Renovate-
    eligible in this repo, which is asserted below.
    """
    consumers = [
        repo
        for repo in extract_repos(SYNC_WORKFLOW)
        if repo not in {"stranske/Workflows", "stranske/Template"}
        and repo.casefold() not in OWNER_EXCLUDED_REPOS
    ]
    assert consumers

    for repo in consumers:
        assert ".github/workflows/ci.yml" not in _renovate_disabled_paths(repo)


def test_workflows_repo_keeps_full_renovate_coverage():
    """The canonical source files are never disabled — no blanket workflow ignore."""
    disabled = _renovate_disabled_paths("stranske/Workflows")
    assert disabled == set()

    preset = json.loads(OWNERSHIP_PRESET.read_text(encoding="utf-8"))
    patterns = {p for rule in preset["packageRules"] for p in rule["matchFileNames"]}
    assert ".github/workflows/**" not in patterns
