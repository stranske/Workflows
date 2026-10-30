"""Integration template sparse checkouts must include every helper module the step scripts load.

`github-api-with-retry.js` requires sibling modules (`error_classifier`,
`github-rate-limited-wrapper.js`). The failure report in Workflows-Integration-Tests
died with "Cannot find module './error_classifier'" while the checkout listed only
the entry file and `token_load_balancer.js`.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "templates/integration-repo/.github/workflows"
TEMPLATES = sorted(TEMPLATE_DIR.glob("*.yml"))
CHECKOUT_PATH = "workflows"
SCRIPT_REQUIRE = re.compile(r"require\(\s*['\"]\./" + CHECKOUT_PATH + r"/([^'\"]+)['\"]")
RELATIVE_REQUIRE = re.compile(r"require\(\s*['\"]\./([^'\"/]+)['\"]")


def _closure(entry: str) -> set[str]:
    seen: set[str] = set()
    todo = [entry]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        source = ROOT / path
        assert source.is_file(), f"required helper {path} does not exist"
        for name in RELATIVE_REQUIRE.findall(source.read_text(encoding="utf-8")):
            sibling = str(Path(path).parent / (name if name.endswith(".js") else f"{name}.js"))
            if (ROOT / sibling).is_file():
                todo.append(sibling)
    return seen


def _jobs(workflow: dict):
    for job_name, job in (workflow.get("jobs") or {}).items():
        yield job_name, job.get("steps") or []


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda path: path.name)
def test_sparse_checkout_covers_required_helper_closure(path: Path) -> None:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    checked = 0
    for job_name, steps in _jobs(workflow):
        entries: list[str] = []
        for step in steps:
            options = step.get("with") or {}
            if options.get("path") == CHECKOUT_PATH:
                entries = str(options.get("sparse-checkout", "")).split()
        for step in steps:
            for entry in SCRIPT_REQUIRE.findall(str((step.get("with") or {}).get("script", ""))):
                checked += 1
                missing = [
                    helper
                    for helper in sorted(_closure(entry))
                    if not any(
                        helper == e or helper.startswith(e.rstrip("/") + "/") for e in entries
                    )
                ]
                assert not missing, f"{path.name} jobs.{job_name}: sparse checkout lacks {missing}"
    assert checked >= 1, f"{path.name}: no step loads a helper from ./{CHECKOUT_PATH}"
