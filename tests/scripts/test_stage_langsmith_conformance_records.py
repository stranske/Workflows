"""Cohesion review B14: conformance runs inside maint-80 over its own downloads.

The pass condition is that the conformance JSON is byte-identical to what the
retired maint-81 produced from the same artifact contents.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from scripts import langsmith_fleet
from scripts import stage_langsmith_conformance_records as stage

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "langsmith_fleet_registry.json"
NOW = "2026-05-30T01:00:00+00:00"
PA = "stranske/Portable-Alpha-Extension-Model"

VALID_PA = {
    "schema_version": langsmith_fleet.SCHEMA_VERSION,
    "repo": PA,
    "surface": "scenario-analysis",
    "operation": "scenario-run",
    "run_id": "pa-run-1",
    "status": "success",
    "github_issue": f"{PA}#1802",
    "recorded_at": "2026-05-30T00:00:00Z",
    "domain": {"scenario_id": "base", "config_hash": "sha256:abc", "seed": 7, "metric_delta": 0.1},
}


def _artifact_repos() -> list[tuple[str, str]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [
        (e["repo"], e.get("artifact_name") or "langsmith-fleet.ndjson")
        for e in registry["repos"]
        if (e.get("evidence_mode") or "artifact") == "artifact"
    ]


def _artifact_contents() -> dict[str, str]:
    """Same input for both layouts: PA valid, one other repo malformed, the rest absent."""
    repos = [repo for repo, _ in _artifact_repos()]
    other = next(repo for repo in repos if repo != PA)
    return {
        PA: json.dumps(VALID_PA) + "\n",
        other: json.dumps({"schema": "legacy", "repo": other}) + "\n",
    }


def _conformance(workdir: Path, fmt: str) -> bytes:
    # Both workflows run from the checkout root with records under .metrics-tmp/fleet;
    # langsmith_fleet reads its schema and allowlist relative to that root.
    for name in ("config", "docs"):
        if not (workdir / name).exists():
            (workdir / name).symlink_to(ROOT / name, target_is_directory=True)
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "langsmith_fleet_conformance.py"),
            "--registry",
            str(REGISTRY),
            "--records-root",
            ".metrics-tmp/fleet",
            "--format",
            fmt,
            "--now",
            NOW,
        ],
        check=True,
        capture_output=True,
        cwd=workdir,
    ).stdout


def test_conformance_json_is_byte_identical_to_the_maint81_layout(tmp_path: Path) -> None:
    names = dict(_artifact_repos())
    contents = _artifact_contents()

    # Retired maint-81: unzip into <owner__repo>/, then copy the named file to the top.
    maint81 = tmp_path / "maint81"
    for repo, text in contents.items():
        out_dir = maint81 / ".metrics-tmp" / "fleet" / stage.records_dir_name(repo)
        nested = out_dir / "unzipped"
        nested.mkdir(parents=True)
        (nested / names[repo]).write_text(text, encoding="utf-8")
        shutil.copyfile(nested / names[repo], out_dir / names[repo])

    # maint-80: unzip into extracted/<owner_repo>/, then stage for conformance.
    maint80 = tmp_path / "maint80"
    extracted = maint80 / ".metrics-tmp" / "fleet" / "extracted"
    for repo, text in contents.items():
        nested = extracted / stage.extracted_dir_name(repo) / "langsmith-fleet"
        nested.mkdir(parents=True)
        (nested / names[repo]).write_text(text, encoding="utf-8")
    staged = maint80 / ".metrics-tmp" / "fleet"
    assert (
        stage.main(
            [
                "--registry",
                str(REGISTRY),
                "--extracted-root",
                str(extracted),
                "--records-root",
                str(staged),
            ]
        )
        == 0
    )

    folded = _conformance(maint80, "json")
    assert folded == _conformance(maint81, "json")
    assert _conformance(maint80, "markdown") == _conformance(maint81, "markdown")
    report = json.loads(folded)
    statuses = {row["repo"]: row["status"] for row in report["rows"]}
    assert statuses[PA] == "valid"
    assert "invalid" in statuses.values() and "missing" in statuses.values()


def test_stage_reports_missing_without_creating_a_file(tmp_path: Path) -> None:
    registry = {
        "repos": [
            {"repo": "o/present", "artifact_name": "langsmith-fleet.ndjson"},
            {"repo": "o/absent", "artifact_name": "langsmith-fleet.ndjson"},
            {"repo": "o/direct", "evidence_mode": "langsmith-direct"},
        ]
    }
    extracted = tmp_path / "extracted"
    (extracted / "o_present" / "a" / "b").mkdir(parents=True)
    (extracted / "o_present" / "a" / "b" / "langsmith-fleet.ndjson").write_text("deep\n")
    (extracted / "o_present" / "a" / "langsmith-fleet.ndjson").write_text("shallow\n")
    records = tmp_path / "records"
    outcome = stage.stage_records(registry, extracted, records)
    assert outcome == {"o/present": "staged", "o/absent": "missing"}
    assert (records / "o__present" / "langsmith-fleet.ndjson").read_text() == "shallow\n"
    assert not (records / "o__absent").exists()


def test_stage_handles_a_run_with_no_downloads(tmp_path: Path) -> None:
    outcome = stage.stage_records(
        {"repos": [{"repo": "o/r", "artifact_name": "x.ndjson"}]},
        tmp_path / "never-created",
        tmp_path / "records",
    )
    assert outcome == {"o/r": "missing"}


def _steps(name: str) -> list[dict]:
    doc = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
    return [step for job in doc["jobs"].values() for step in job.get("steps", [])]


def test_maint80_builds_conformance_from_its_own_downloads() -> None:
    steps = _steps("maint-80-langsmith-metrics-dashboard.yml")
    names = [step.get("name") for step in steps]
    build = steps[names.index("Build fleet conformance report")]
    assert names.index("Validate fleet artifacts") < names.index("Build fleet conformance report")
    assert "--extracted-root .metrics-tmp/fleet/extracted" in build["run"]
    assert "langsmith_fleet_conformance.py" in build["run"]
    # no second cross-repo download
    assert "gh api" not in build["run"] and "downloadArtifact" not in build["run"]
    upload = steps[names.index("Upload conformance report")]
    assert upload["with"]["name"] == "langsmith-fleet-conformance-${{ github.run_id }}"
    assert upload["with"]["retention-days"] == 30
    enforce = steps[names.index("Enforce conformance")]
    assert "inputs.enforce_conformance == true" in enforce["if"]
    assert not (ROOT / ".github/workflows/maint-81-langsmith-fleet-conformance.yml").exists()


def test_routine_observability_retention_is_bounded() -> None:
    for name in (
        "maint-80-langsmith-metrics-dashboard.yml",
        "health-84-langsmith-observability.yml",
    ):
        for step in _steps(name):
            if "actions/upload-artifact@" in step.get("uses", ""):
                assert step["with"]["retention-days"] == 30, (name, step.get("name"))


def test_discovery_errors_make_missing_rows_unknown_and_block_enforcement() -> None:
    steps = _steps("maint-80-langsmith-metrics-dashboard.yml")
    names = [step.get("name") for step in steps]
    build = steps[names.index("Build fleet conformance report")]["run"]
    assert "if [ -s .metrics-tmp/fleet/fleet_errors.log ]; then" in build
    assert "LANGSMITH_FLEET_DISCOVERY_ERRORS=true" in build
    assert "may be UNKNOWN" in build
    enforce = steps[names.index("Enforce conformance")]["if"]
    assert "env.LANGSMITH_FLEET_DISCOVERY_ERRORS != 'false'" in enforce
