"""Maint 77 must preserve the durable lifecycle of its evidence issue."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/maint-77-model-registry-freshness.yml")


def test_model_registry_evidence_issue_is_labeled_durable_on_create_and_refresh() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert source.count('--add-label "automated"') == 1
    assert source.count('--add-label "tracker:durable"') == 1
    assert source.count('--label "automated,tracker:durable"') == 1


EDIT_ONLY = ["issue list", "issue edit"]
EDIT_AND_COMMENT = ["issue list", "issue edit", "issue comment"]


@pytest.mark.parametrize(
    (
        "freshness_rc",
        "advisory",
        "discovery_rc",
        "added",
        "expected_rc",
        "expected_message",
        "calls",
    ),
    [
        (0, False, 0, [], 0, "findings cleared", []),
        # Round-3 M2: a cadence finding that has not changed rewrites the body only;
        # 21 weekly comments on the same overdue date (since 2026-08) announced nothing.
        (0, True, 0, [], 0, "findings persist", EDIT_ONLY),
        (1, False, 0, [], 0, "findings persist", EDIT_AND_COMMENT),
        (0, False, 1, ["new-model"], 0, "findings persist", EDIT_AND_COMMENT),
        (0, True, 1, ["new-model"], 0, "findings persist", EDIT_AND_COMMENT),
        (0, False, 1, [], 0, "findings persist", EDIT_ONLY),  # removal only
        (2, False, 0, [], 2, "configuration error", []),
        (0, False, 2, [], 2, "configuration error", []),
    ],
    ids=[
        "clear",
        "advisory",
        "structural",
        "catalog-addition",
        "advisory-and-addition",
        "catalog-removal",
        "freshness-error",
        "catalog-error",
    ],
)
def test_tracking_issue_uses_rechecked_findings(
    tmp_path: Path,
    freshness_rc: int,
    advisory: bool,
    discovery_rc: int,
    added: list[str],
    expected_rc: int,
    expected_message: str,
    calls: list[str],
) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["tracking-issue"]["steps"]
    reports = next(step for step in steps if step.get("id") == "reports")
    writer = next(step for step in steps if step["name"].startswith("Open or refresh"))
    fixture = tmp_path / "python3"
    fixture.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  tools/check_model_registry_freshness.py) printf "%s\\n" "$FRESHNESS_JSON"; exit "$FRESHNESS_RC" ;;\n'
        '  tools/discover_model_catalog.py) echo "the tracker must not re-fetch" >&2; exit 9 ;;\n'
        '  *) exec "$TEST_PYTHON" "$@" ;;\n'
        "esac\n"
    )
    fixture.chmod(0o755)
    gh = tmp_path / "gh"
    gh.write_text(
        '#!/bin/sh\nprintf "%s %s\\n" "$1" "$2" >> "$GH_LOG"\n'
        'if [ "$2" = list ]; then printf "2905\\n"; fi\n'
    )
    gh.chmod(0o755)
    gh_log = tmp_path / "gh.log"
    outputs = tmp_path / "output"
    summary = tmp_path / "summary"
    outputs.touch()
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "TEST_PYTHON": sys.executable,
        "GITHUB_OUTPUT": str(outputs),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GH_LOG": str(gh_log),
        "FRESHNESS_JSON": json.dumps({"advisory": ["review overdue"] if advisory else []}),
        "FRESHNESS_RC": str(freshness_rc),
        "DISCOVERY_JSON": json.dumps(
            {
                "drift": discovery_rc == 1,
                "providers": [{"provider": "openai", "added_candidates": added}],
            }
        ),
        "DISCOVERY_RC": str(discovery_rc),
    }
    # The tracker reads the freshness job's own discovery report (downloaded artifact).
    (tmp_path / "catalog-discovery.json").write_text(
        env["DISCOVERY_JSON"] if discovery_rc < 2 else "not json", encoding="utf-8"
    )
    result = subprocess.run(
        ["bash", "-e", "-c", reports["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    decision = dict(line.split("=", 1) for line in outputs.read_text().splitlines())
    condition = writer.get("if")
    if condition is not None:
        assert condition == "steps.reports.outputs.has_findings == 'true'"
    if result.returncode == 0 and (condition is None or decision.get("has_findings") == "true"):
        shell = (
            writer["run"]
            .replace("${{ github.server_url }}", "https://github.com")
            .replace("${{ github.repository }}", "stranske/Workflows")
            .replace("${{ github.run_id }}", "37269067774")
        )
        env["NOTIFY"] = decision.get("notify", "")
        subprocess.run(["bash", "-e", "-c", shell], cwd=tmp_path, env=env, check=True)
        body = (tmp_path / "issue_body.md").read_text()
        assert "What clears each finding" in body
    assert writer["env"]["NOTIFY"] == "${{ steps.reports.outputs.notify }}"
    made = gh_log.read_text().splitlines() if gh_log.exists() else []
    assert result.returncode == expected_rc
    assert made == calls
    assert expected_message in result.stdout
    if expected_rc == 0:
        assert expected_message in summary.read_text()


def test_scheduled_runs_record_baselines_through_the_maint_79_merge_path() -> None:
    """The observed catalog becomes the baseline via an auto-merged PR, never a push."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    jobs = workflow["jobs"]
    discovery = next(s for s in jobs["freshness"]["steps"] if s.get("id") == "discovery")
    assert "--record-baselines" in discovery["run"]
    assert "baselines_changed=true" in discovery["run"]
    assert discovery["if"] == "github.event_name != 'pull_request'"

    record = jobs["record-baselines"]
    assert "github.event_name != 'pull_request'" in record["if"]
    assert "needs.freshness.outputs.baselines_changed == 'true'" in record["if"]
    assert record["permissions"] == {"contents": "read"}

    maint79 = yaml.safe_load(
        Path(".github/workflows/maint-79-verifier-corpus-harvest.yml").read_text()
    )["jobs"]["harvest"]["steps"]
    ours = record["steps"]

    def uses(steps: list[dict], prefix: str) -> str:
        return next(s["uses"] for s in steps if str(s.get("uses", "")).startswith(prefix))

    assert uses(ours, "peter-evans/create-pull-request") == uses(
        maint79, "peter-evans/create-pull-request"
    )
    cpr = next(s for s in ours if s.get("id") == "cpr")
    assert cpr["with"]["token"] == "${{ secrets.OWNER_PR_PAT }}"
    # Health 72 mirrors the registry into the consumer template; the baseline PR must
    # carry both copies or Health 72's sync push moves the head inside the window.
    mirrored = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py", "--print-sources"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert "config/model_registry.json" in mirrored
    assert cpr["with"]["add-paths"].split() == [
        "config/model_registry.json",
        "templates/consumer-repo/config/model_registry.json",
    ]
    assert (
        "cp config/model_registry.json templates/consumer-repo/config/model_registry.json"
        in discovery["run"]
    )
    assert "<!-- workflow-source:automation_run -->" in cpr["with"]["body"]
    window = next(s for s in ours if s.get("id") == "review_window")["run"]
    assert "sleep 420" in window
    assert "wait_for_required_checks.sh" in window
    merge = next(s for s in ours if s.get("name") == "Enable auto-merge")["run"]
    theirs = next(s for s in maint79 if s.get("name") == "Enable auto-merge")["run"]
    assert merge == theirs


def test_baseline_waits_for_the_announcement_from_the_same_observation() -> None:
    """Review on #5563: an addition must not become 'known' before it was announced."""
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    record = jobs["record-baselines"]
    assert record["needs"] == ["freshness", "tracking-issue"]
    condition = " ".join(record["if"].split())
    assert "!cancelled()" in condition
    assert "needs.freshness.result == 'success'" in condition
    assert (
        "(needs.tracking-issue.result == 'success' || needs.tracking-issue.result == 'skipped')"
        in condition
    )
    steps = jobs["tracking-issue"]["steps"]
    download = next(s for s in steps if s.get("name") == "Download catalog discovery")
    assert download["with"]["name"] == "model-catalog-discovery-${{ github.run_id }}"
    reports = next(s for s in steps if s.get("id") == "reports")
    assert "discover_model_catalog.py" not in reports["run"]
    assert "env" not in reports  # no provider keys: it does not fetch
