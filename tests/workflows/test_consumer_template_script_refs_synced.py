"""Every repo-local script a consumer-template workflow runs must reach consumers.

Workflows#3955-era finding: pr-00-gate.yml runs `python scripts/ledger_validate.py` for any PR with a
belt ledger, but the script was in neither the consumer template nor the sync manifest, so the
required `summary` check failed on belt PRs in 15 of 16 consumers. This test makes that class
of gap a CI failure instead of a surprise in a consumer.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates/consumer-repo"
MANIFEST = ROOT / ".github/sync-manifest.yml"

# Referenced on purpose without being synced, each with the reason it is safe.
OPTIONAL_BY_DESIGN = {
    # pr-00-gate.yml guards it with hashFiles(...) and prints "not present; skipped".
    "scripts/check_issue_consistency.py": "guarded by hashFiles, skipped when absent",
}
SKIP_PREFIXES = (".belt-tools/", ".workflows-lib/", "workflows-scripts/", ".workflows/")
CMD = re.compile(
    r"(?:python3?|node|bash|sh)\s+(?:-u\s+)?(?:\./)?"
    r"((?:scripts|tools|\.github/scripts|\.github/codex|\.github/actions)/[A-Za-z0-9_./-]+"
    r"\.(?:py|js|sh|mjs|cjs))"
)
MODULE = re.compile(r"python3?\s+-m\s+(scripts(?:\.[A-Za-z0-9_]+)+)")


def _manifest_targets() -> set[str]:
    targets: set[str] = set()
    for entries in yaml.safe_load(MANIFEST.read_text()).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and "source" in entry:
                targets.add(entry.get("target") or entry["source"])
    return targets


def _synced(path: str, targets: set[str]) -> bool:
    if (TEMPLATE / path).exists() or path in targets:
        return True
    return any(t.endswith("/") and path.startswith(t) for t in targets)


def _references() -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for workflow in sorted((TEMPLATE / ".github/workflows").glob("*.yml")):
        text = workflow.read_text()
        for match in CMD.finditer(text):
            refs.setdefault(match.group(1), set()).add(workflow.name)
        for match in MODULE.finditer(text):
            base = match.group(1).replace(".", "/")
            # a module is either a package directory or a single .py file
            refs.setdefault(base + ".py", set()).add(workflow.name)
    return {p: w for p, w in refs.items() if not p.startswith(SKIP_PREFIXES) and "${" not in p}


def test_every_script_a_consumer_workflow_runs_is_synced_or_optional_by_design():
    targets = _manifest_targets()
    missing = {}
    for path, workflows in _references().items():
        if path in OPTIONAL_BY_DESIGN or _synced(path, targets):
            continue
        # python -m scripts.pkg.mod may be a package directory rather than mod.py
        if path.endswith(".py") and _synced(path[:-3] + "/", targets):
            continue
        missing[path] = sorted(workflows)
    assert not missing, f"scripts run by consumer workflows but never delivered: {missing}"


def test_the_ledger_validator_is_delivered_to_consumers():
    assert "scripts/ledger_validate.py" in _manifest_targets()
    assert (ROOT / "scripts/ledger_validate.py").is_file()
