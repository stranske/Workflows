"""Maint 68 sync labels have one definition: .github/labels-core.yml (cohesion review B9).

Maint 68 used to force-create seven labels and create-if-missing five more, each with its
own literal colour and description, so a consumer label had up to three writers (Maint 68,
Maint 69 Sync Labels, Maint 83 bootstrap). Maint 68 now only checks that the labels it
applies exist, and Maint 69 Sync Labels (daily) is the drain when one is missing.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAINT_68 = ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml"
MAINT_69_LABELS = ROOT / ".github/workflows/maint-69-sync-labels.yml"
LABELS_CORE = ROOT / ".github/labels-core.yml"

FORMERLY_FORCE_CREATED = (
    "sync",
    "automated",
    "sync:delivery-staging",
    "sync:delivery-ready",
    "agents:format",
    "agents:formatted",
    "agents:optimize",
    "agents:apply-suggestions",
)


def _core_names() -> list[str]:
    return [entry["name"] for entry in yaml.safe_load(LABELS_CORE.read_text(encoding="utf-8"))]


def _label_step() -> dict:
    workflow = yaml.safe_load(MAINT_68.read_text(encoding="utf-8"))
    return next(step for step in workflow["jobs"]["sync"]["steps"] if step.get("id") == "labels")


def test_formerly_force_created_labels_are_defined_once_in_labels_core() -> None:
    names = _core_names()
    for label in FORMERLY_FORCE_CREATED + ("workflow:source-sync",):
        assert names.count(label) == 1, label


def test_maint_68_label_step_creates_nothing() -> None:
    run = str(_label_step()["run"])
    assert "gh label create" not in run
    assert "--force" not in run
    assert "--color" not in run


def test_maint_68_force_create_list_is_empty() -> None:
    """Pass number for B9: no `gh label create` anywhere in Maint 68's consumer sync job."""
    workflow = yaml.safe_load(MAINT_68.read_text(encoding="utf-8"))
    runs = [str(step.get("run", "")) for step in workflow["jobs"]["sync"]["steps"]]
    creates = [line for run in runs for line in run.splitlines() if "gh label create" in line]
    assert creates == []


def test_every_label_maint_68_applies_is_checked_and_core_defined() -> None:
    text = MAINT_68.read_text(encoding="utf-8")
    applied: set[str] = set()
    for match in re.finditer(r'--(?:add-)?label "([^"]+)"', text):
        applied.update(part.strip() for part in match.group(1).split(","))
    run = str(_label_step()["run"])
    checked = set(re.findall(r'^\s+"([a-z:-]+)"$', run, flags=re.MULTILINE))
    consumer_pr_labels = {"sync", "automated", "workflow:source-sync", "sync:delivery-staging"}
    assert consumer_pr_labels <= applied
    assert consumer_pr_labels | {"sync:delivery-ready"} <= checked
    assert checked <= set(_core_names())


def test_label_sync_runs_daily_as_the_drain() -> None:
    workflow = yaml.safe_load(MAINT_69_LABELS.read_text(encoding="utf-8"))
    triggers = workflow[True]
    assert triggers.get("schedule"), "Maint 69 Sync Labels must run on a schedule to drain"
    assert ".github/labels-core.yml" in triggers["push"]["paths"]


def _run_label_step(tmp_path: Path, present: list[str]) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1 $2" = "label list" ]; then printf "%s\\n" '
        + " ".join(f'"{label}"' for label in present)
        + "; exit 0; fi\n"
        'echo "unexpected gh call: $*" >&2; exit 9\n',
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "consumer").mkdir()
    (tmp_path / "workflows" / ".github").mkdir(parents=True)
    (tmp_path / "workflows" / ".github" / "labels-core.yml").write_bytes(LABELS_CORE.read_bytes())
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", str(_label_step()["run"])],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TARGET_REPOSITORY": "o/r"},
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_label_check_passes_when_all_present(tmp_path: Path) -> None:
    result = _run_label_step(
        tmp_path,
        [
            "sync",
            "automated",
            "workflow:source-sync",
            "sync:delivery-staging",
            "sync:delivery-ready",
        ],
    )
    assert result.returncode == 0, result.stderr
    assert "Required sync labels: 5; present: 5; missing: 0" in result.stdout


def test_label_check_fails_loudly_and_names_the_drain(tmp_path: Path) -> None:
    result = _run_label_step(tmp_path, ["sync", "automated", "workflow:source-sync"])
    assert result.returncode == 1
    assert "present: 3; missing: 2" in result.stdout
    assert "sync:delivery-staging sync:delivery-ready" in result.stdout
    assert "Maint 69 Sync Labels" in result.stdout
