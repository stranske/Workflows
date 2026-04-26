from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")
REPO_HELPER = "scripts/list_registered_consumer_repos.py"
REPO_MANIFEST = ".github/workflows/maint-68-sync-consumer-repos.yml"


def test_sparse_checkout_callers_include_registered_repo_manifest():
    offenders = []

    for workflow_path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = workflow_path.read_text(encoding="utf-8")
        if REPO_HELPER not in text or "sparse-checkout:" not in text:
            continue
        if REPO_MANIFEST not in text:
            offenders.append(str(workflow_path))

    assert offenders == []
