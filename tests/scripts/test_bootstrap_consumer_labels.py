from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from scripts import bootstrap_consumer_settings as bcs
from scripts import capture_bootstrap_label_tests as capture
from scripts.upload_repo_review_issues import LABELS as REVIEW_LABELS

EXPECTED_PRIORITY_LABELS = {
    "priority:high": {
        "color": "b60205",
        "description": "High-priority weekly repo-review work",
    },
    "priority:normal": {
        "color": "fbca04",
        "description": "Normal-priority weekly repo-review work",
    },
    "priority:low": {
        "color": "0e8a16",
        "description": "Low-priority weekly repo-review work",
    },
}


def _label_inventory(*names: str) -> dict[str, dict[str, str]]:
    return {name: {"name": name, **EXPECTED_PRIORITY_LABELS[name]} for name in names}


def _priority_source(*, high: str = "", normal: str = "", low: str = "") -> str:
    return "\n".join(
        [
            high or """- name: priority:high
  color: "b60205"
  description: High-priority weekly repo-review work""",
            normal or """- name: priority:normal
  color: "fbca04"
  description: Normal-priority weekly repo-review work""",
            low or """- name: priority:low
  color: "0e8a16"
  description: Low-priority weekly repo-review work""",
            "",
        ]
    )


def _issue(
    number: int,
    title: str,
    *,
    labels: tuple[str, ...] = (),
    login: str = "stranske",
    is_pr: bool = False,
) -> dict[str, object]:
    issue: dict[str, object] = {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in labels],
        "user": {"login": login, "type": "Bot" if login.endswith("[bot]") else "User"},
    }
    if is_pr:
        issue["pull_request"] = {"url": "https://example.invalid/pr"}
    return issue


def test_priority_labels_match_synced_source_and_review_uploader() -> None:
    entries = yaml.safe_load(Path(".github/labels-core.yml").read_text(encoding="utf-8"))
    synced_priority_labels = {
        entry["name"]: {
            "color": entry["color"],
            "description": entry["description"],
        }
        for entry in entries
        if entry["name"].startswith("priority:")
    }
    assert synced_priority_labels == EXPECTED_PRIORITY_LABELS
    assert synced_priority_labels == bcs.PRIORITY_LABELS
    assert {name: REVIEW_LABELS[name] for name in EXPECTED_PRIORITY_LABELS} == (
        EXPECTED_PRIORITY_LABELS
    )


def test_priority_label_source_rejects_missing_required_name(tmp_path: Path) -> None:
    labels_path = tmp_path / "labels-core.yml"
    labels_path.write_text(
        """\
- name: priority:high
  color: "b60205"
  description: High-priority weekly repo-review work
- name: priority:normal
  color: "fbca04"
  description: Normal-priority weekly repo-review work
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required priority labels: priority:low"):
        bcs._load_priority_labels(labels_path)


def test_priority_label_source_matches_yaml_string_semantics(tmp_path: Path) -> None:
    labels_path = tmp_path / "labels-core.yml"
    labels_path.write_text(
        _priority_source(high="""- name: priority:high
  color: "b60205"
  description: 'Owner''s urgent \\work'"""),
        encoding="utf-8",
    )
    loaded = bcs._load_core_label_entries(labels_path)
    assert loaded == yaml.safe_load(labels_path.read_text(encoding="utf-8"))
    assert loaded[0]["description"] == "Owner's urgent \\work"


@pytest.mark.parametrize(
    ("source", "diagnostic"),
    [
        (
            _priority_source(normal="""- name: priority:high
  color: "fbca04"
  description: duplicate"""),
            "duplicate priority label",
        ),
        (
            _priority_source(normal="""- name: priority:normal
  description: missing color"""),
            "is missing color",
        ),
        (
            _priority_source(
                normal='''- name: priority:normal
  color: "fbca04"''',
            ),
            "is missing description",
        ),
        (
            _priority_source(normal="""- name: priority:normal
  color: "fbca04"
  description: 'unpaired ' quote'"""),
            "invalid quoted label value",
        ),
        (
            _priority_source(normal="""- name: priority:normal
  color: "fbca04"
  description:"""),
            "label value is empty",
        ),
        (
            _priority_source(normal="""- name: priority:normal
  color: "fbca04"
  description: valid # YAML comment"""),
            "unsupported label YAML scalar",
        ),
    ],
)
def test_priority_label_source_rejects_invalid_forms(
    tmp_path: Path, source: str, diagnostic: str
) -> None:
    labels_path = tmp_path / "labels-core.yml"
    labels_path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match=diagnostic):
        bcs._load_priority_labels(labels_path)


def test_label_plan_contains_all_three_required_labels() -> None:
    plan = bcs.build_label_plan("stranske/Foo")
    assert [operation["id"] for operation in plan] == [
        "label_high",
        "label_normal",
        "label_low",
    ]
    commands = [operation["command"] for operation in plan]
    for name, definition in EXPECTED_PRIORITY_LABELS.items():
        command = next(command for command in commands if name in command)
        assert command == [
            "gh",
            "label",
            "create",
            name,
            "--repo",
            "stranske/Foo",
            "--color",
            definition["color"],
            "--description",
            definition["description"],
        ]
        assert "--force" not in command


def test_apply_priority_labels_creates_only_missing_and_rechecks() -> None:
    initial = _label_inventory("priority:high", "priority:low")
    complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            side_effect=[initial, complete],
        ),
        patch("subprocess.run") as run,
    ):
        bcs.apply_priority_labels("stranske/Foo")
    run.assert_called_once_with(
        bcs._label_create_command(
            "stranske/Foo",
            "priority:normal",
            EXPECTED_PRIORITY_LABELS["priority:normal"],
        ),
        check=True,
    )


def test_apply_priority_labels_accepts_complete_template_inventory() -> None:
    complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            side_effect=[complete, complete],
        ),
        patch("subprocess.run") as run,
    ):
        bcs.apply_priority_labels("stranske/Template")
    run.assert_not_called()


def test_main_execute_reconciles_template_derived_consumer_fixture() -> None:
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/template_derived_consumer_priority_labels.json"
        ).read_text(encoding="utf-8")
    )
    response = MagicMock(stdout=json.dumps([fixture]))
    with (
        patch(
            "sys.argv",
            [
                "bootstrap_consumer_settings.py",
                "--repo",
                "fixture/template-consumer",
                "--labels-only",
                "--execute",
            ],
        ),
        patch("subprocess.run", side_effect=[response, response]) as run,
    ):
        assert bcs.main() == 0

    commands = [call.args[0] for call in run.call_args_list]
    label_reads = [
        command
        for command in commands
        if "--paginate" in command
        and "/repos/fixture/template-consumer/labels?per_page=100" in command
    ]
    assert len(label_reads) == 2
    assert not any(command[1:3] == ["label", "create"] for command in commands)


@pytest.mark.parametrize("returncode", [0, 7])
def test_capture_script_writes_output_and_returns_pytest_status(
    tmp_path: Path, returncode: int
) -> None:
    output = tmp_path / "nested" / "bootstrap-label-tests.txt"
    completed = MagicMock(returncode=returncode, stdout="focused proof\n")
    with (
        patch("sys.argv", ["capture_bootstrap_label_tests.py", "--out", str(output)]),
        patch("subprocess.run", return_value=completed) as run,
    ):
        assert capture.main() == returncode

    assert output.read_text(encoding="utf-8") == "focused proof\n"
    run.assert_called_once_with(
        [
            capture.sys.executable,
            "-m",
            "pytest",
            "tests/scripts/test_bootstrap_consumer_labels.py",
            "-q",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_apply_priority_labels_refuses_metadata_overwrite() -> None:
    inventory = _label_inventory(*EXPECTED_PRIORITY_LABELS)
    inventory["priority:normal"]["description"] = "Normal priority"
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            return_value=inventory,
        ),
        patch("subprocess.run") as run,
        pytest.raises(SystemExit, match="Refusing to overwrite"),
    ):
        bcs.apply_priority_labels("stranske/Foo")
    run.assert_not_called()


def test_apply_priority_labels_tolerates_concurrent_exact_create() -> None:
    initial = _label_inventory("priority:high", "priority:low")
    complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
    error = subprocess.CalledProcessError(1, ["gh"], stderr="already exists")
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            side_effect=[initial, complete, complete],
        ),
        patch("subprocess.run", side_effect=error),
    ):
        bcs.apply_priority_labels("stranske/Foo")


def test_apply_priority_labels_reraises_when_create_fails() -> None:
    initial = _label_inventory("priority:high", "priority:low")
    error = subprocess.CalledProcessError(1, ["gh"], stderr="forbidden")
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            side_effect=[initial, initial],
        ),
        patch("subprocess.run", side_effect=error),
        pytest.raises(subprocess.CalledProcessError),
    ):
        bcs.apply_priority_labels("stranske/Foo")


def test_apply_priority_labels_fails_final_verification() -> None:
    initial = _label_inventory("priority:high", "priority:low")
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            side_effect=[initial, initial],
        ),
        patch("subprocess.run"),
        pytest.raises(SystemExit, match="Priority label verification failed"),
    ):
        bcs.apply_priority_labels("stranske/Foo")


def test_read_paginated_collection_flattens_every_page() -> None:
    result = MagicMock()
    result.stdout = json.dumps([[{"number": 1}], [{"number": 2}], []])
    with patch("subprocess.run", return_value=result) as run:
        items = bcs._read_paginated_collection("/repos/stranske/Foo/issues?state=open")
    assert items == [{"number": 1}, {"number": 2}]
    assert "--paginate" in run.call_args.args[0]
    assert "--slurp" in run.call_args.args[0]


def test_issue_summary_counts_unlabelled_and_bot_delivery_without_guessing_priority() -> None:
    issues = [
        _issue(1, "ordinary unlabeled defect"),
        _issue(2, "normal defect", labels=("priority:normal",)),
        _issue(3, "two labels", labels=("priority:high", "priority:low")),
        _issue(4, "verifier follow-up", login="github-actions[bot]"),
        _issue(5, "durable tracker", labels=("tracker:durable",)),
        _issue(6, "Dependency Dashboard"),
        _issue(7, "Bump pytest from 8 to 9", login="dependabot[bot]"),
        _issue(
            8,
            "[sync-review] managed path drift",
            labels=("automation", "consumer-sync"),
        ),
        _issue(9, "open pull request", is_pr=True),
    ]
    assert bcs.summarize_implementation_issues(issues) == {
        "implementation_count": 4,
        "priority_labelled_count": 2,
        "unprioritized_count": 2,
        "excluded": {
            "dependency_bot": 1,
            "dependency_dashboard": 1,
            "durable_holder": 1,
            "pull_request": 1,
            "sync_bookkeeping": 1,
        },
    }


def test_health_check_reports_zero_counts_and_missing_labels() -> None:
    complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
    missing_normal = _label_inventory("priority:high", "priority:low")
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            side_effect=[complete, missing_normal],
        ),
        patch(
            "scripts.bootstrap_consumer_settings._read_paginated_collection",
            side_effect=[[], [_issue(1, "unlabelled delivery")]],
        ),
    ):
        rows, exit_code = bcs.check_consumer_health(["stranske/Empty", "stranske/Missing"])
    assert exit_code == 1
    assert rows[0] == {
        "repository": "stranske/Empty",
        "implementation_count": 0,
        "priority_labelled_count": 0,
        "unprioritized_count": 0,
        "missing": [],
        "metadata_mismatch": [],
        "excluded": {},
        "error": None,
        "status": "OK",
    }
    assert rows[1]["missing"] == ["priority:normal"]
    assert rows[1]["implementation_count"] == 1
    assert rows[1]["priority_labelled_count"] == 0
    assert rows[1]["status"] == "FAIL"


def test_health_check_preserves_unknown_on_systemic_api_failure() -> None:
    error = subprocess.CalledProcessError(
        1,
        ["gh", "api"],
        stderr="API rate limit exceeded for installation",
    )
    with patch(
        "scripts.bootstrap_consumer_settings._priority_label_inventory",
        side_effect=error,
    ) as inventory:
        rows, exit_code = bcs.check_consumer_health(["stranske/First", "stranske/Second"])
    assert exit_code == 2
    assert inventory.call_count == 1
    assert [row["status"] for row in rows] == ["ERROR", "ERROR"]
    assert rows[1]["missing"] is None
    assert rows[1]["implementation_count"] is None


def test_render_health_row_preserves_explicit_zeroes() -> None:
    row = {
        "repository": "stranske/Empty",
        "implementation_count": 0,
        "priority_labelled_count": 0,
        "unprioritized_count": 0,
        "missing": [],
        "metadata_mismatch": [],
        "excluded": {},
        "error": None,
        "status": "OK",
    }
    assert bcs._render_health_row(row) == (
        "stranske/Empty implementation=0 priority_labelled=0 unprioritized=0 "
        "missing=none metadata_mismatch=none status=OK"
    )


def test_labels_only_execute_skips_unrelated_settings() -> None:
    with (
        patch(
            "sys.argv",
            ["bcs", "--repo", "stranske/Template", "--labels-only", "--execute"],
        ),
        patch("subprocess.run") as run,
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels") as apply,
    ):
        assert bcs.main() == 0
    run.assert_not_called()
    apply.assert_called_once_with("stranske/Template")


def test_health_mode_uses_registry_and_performs_no_direct_writes(tmp_path) -> None:
    manifest = tmp_path / "maint-68.yml"
    manifest.write_text(
        "env:\n  REGISTERED_CONSUMER_REPOS: |\n    stranske/One\n    stranske/Two\n",
        encoding="utf-8",
    )
    rows = [
        {
            "repository": "stranske/One",
            "implementation_count": 0,
            "priority_labelled_count": 0,
            "unprioritized_count": 0,
            "missing": [],
            "metadata_mismatch": [],
            "excluded": {},
            "error": None,
            "status": "OK",
        }
    ]
    with (
        patch(
            "sys.argv",
            ["bcs", "--health-check", "--manifest", str(manifest)],
        ),
        patch(
            "scripts.bootstrap_consumer_settings.check_consumer_health",
            return_value=(rows, 0),
        ) as health,
        patch("subprocess.run") as run,
    ):
        assert bcs.main() == 0
    run.assert_not_called()
    health.assert_called_once_with(["stranske/One", "stranske/Two"])
