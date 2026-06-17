import pathlib

import yaml

WORKFLOW_ROOT = pathlib.Path(".github/workflows")
SYNC_MANIFEST = pathlib.Path(".github/sync-manifest.yml")
ACTIVE_DEPENDENCY_BOT_WORKFLOWS = (
    WORKFLOW_ROOT / "maint-auto-label-dep-prs.yml",
    WORKFLOW_ROOT / "maint-auto-lock-deps.yml",
)
RETIRED_CONSUMER_AUTOMERGE = pathlib.Path(
    "templates/consumer-repo/.github/workflows/dependabot-automerge.yml"
)


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
