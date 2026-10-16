"""Consumer runner module invocations require the complete copy-synced library."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "templates/consumer-repo/.github/workflows"


def test_consumer_runner_lib_invocations_have_manifest_entries() -> None:
    manifest = yaml.safe_load((ROOT / ".github/sync-manifest.yml").read_text(encoding="utf-8"))
    callers = []
    workflow_paths = sorted(
        path for path in WORKFLOWS.rglob("*") if path.suffix in {".yml", ".yaml"}
    )
    assert workflow_paths, "No consumer template workflows found"
    for path in workflow_paths:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if re.search(
                    r"\bpython(?:3(?:\.\d+)?)?\s+-m\s+scripts\.runner_lib\b", step.get("run", "")
                ):
                    callers.append(path.relative_to(ROOT).as_posix())

    if not callers:
        return

    entries = {entry["source"]: entry for entry in manifest.get("scripts", [])}
    sources = sorted((ROOT / "scripts/runner_lib").rglob("*.py"))
    assert sources, "Consumer workflows invoke scripts.runner_lib but the library is absent"
    for path in sources:
        source = path.relative_to(ROOT).as_posix()
        assert source in entries, f"Missing sync manifest entry for {source}; invoked by {callers}"
        entry = entries[source]
        assert entry.get("target", source) == source, f"Incorrect sync target for {source}"
        assert entry.get("source_tree", "root") == "root", f"Incorrect source tree for {source}"
        assert entry.get("delivery", "copy") == "copy", f"Missing copy delivery for {source}"
        assert not entry.get("sync_mode"), f"{source} must overwrite stale consumer copies"
        assert not entry.get("include_repos"), f"{source} must reach all consumers"
        assert not entry.get("skip_repos"), f"{source} must reach all consumers"
