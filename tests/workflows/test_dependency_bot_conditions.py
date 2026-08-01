import json
import pathlib

import yaml
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


def test_auto_lock_documents_pull_request_head_ref_trust_boundary():
    source = _workflow_source(WORKFLOW_ROOT / "maint-auto-lock-deps.yml")
    assert "pull_request, not pull_request_target" in source
    assert "github.head_ref is not an untrusted-code privileged checkout" in source


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
    consumers = [repo for repo in extract_repos(SYNC_WORKFLOW) if repo != "stranske/Workflows"]
    assert consumers

    for repo in consumers:
        disabled = _renovate_disabled_paths(repo)
        assert ".github/workflows/agents-guard.yml" in disabled
        assert ".github/workflows/maint-76-claude-code-review.yml" in disabled


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
