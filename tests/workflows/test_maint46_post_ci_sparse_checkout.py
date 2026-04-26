from pathlib import Path

import yaml


def test_maint46_sparse_checkout_includes_post_ci_import_dependencies():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout helpers")
    sparse_checkout = checkout["with"]["sparse-checkout"]

    assert "tools/post_ci_summary.py" in sparse_checkout
    assert "tools/__init__.py" in sparse_checkout
    assert "tools/ci_failure_triage.py" in sparse_checkout
