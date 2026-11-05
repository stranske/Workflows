import json

import pytest
from scripts import check_guarded_merge_deployment as checker

WORKFLOW = """name: Consumer
jobs:
  guarded-merge:
    steps:
      - name: Merge
        run: guarded-merge
"""


def diagnostic(source="FIRST_PAT", actor="writer", scopes="repo"):
    return (
        "2026-11-05T09:00:00.0000000Z Guarded merge credential "
        f"source={source}; actor={actor}; OAuth scopes={scopes}\n"
    )


def test_matching_job_and_reported_classic_scope_do_not_claim_acceptance():
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, diagnostic())
    assert report["job_matches_source"] is True
    assert report["blockers"] == []
    assert report["attempts"] == [
        {"source": "FIRST_PAT", "actor": "writer", "classic_repo_scope_reported": True}
    ]
    assert report["effective_permissions_confirmed"] is False
    assert report["merge_success_confirmed"] is False


def test_real_template_job_is_compared_without_unrelated_workflow_metadata():
    template = checker.TEMPLATE.read_text(encoding="utf-8")
    consumer = template.replace("name: Agents Gate Followups", "name: Consumer Followups", 1)
    assert consumer != template
    assert checker.inspect_deployment(template, consumer, diagnostic())["job_matches_source"]
    # An actual missing diagnostic, permission change or guard cannot pass comparison.
    consumer = template.replace("Guarded merge credential source=", "Old diagnostic source=", 1)
    assert consumer != template
    report = checker.inspect_deployment(template, consumer, diagnostic())
    assert report["job_matches_source"] is False
    assert "differs from selected source" in report["blockers"][0]


@pytest.mark.parametrize(
    "scopes",
    [
        "",
        "public_repo",
        "repo:status",
        "read:org",
        "not reported (fine-grained/App tokens require settings verification)",
    ],
)
def test_absent_or_insufficient_scope_evidence_requires_verification(scopes):
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, diagnostic(scopes=scopes))
    assert report["blockers"]
    assert not any(attempt["classic_repo_scope_reported"] for attempt in report["attempts"])


@pytest.mark.parametrize("retry_scopes", ["read:org", ""])
def test_retry_cannot_borrow_previous_clients_identity_or_scope(retry_scopes):
    log = diagnostic(scopes="repo, workflow") + diagnostic(
        "RETRY_PAT", "retry-writer", retry_scopes
    )
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["attempts"] == [
        {"source": "FIRST_PAT", "actor": "writer", "classic_repo_scope_reported": True},
        {"source": "RETRY_PAT", "actor": "retry-writer", "classic_repo_scope_reported": False},
    ]
    assert report["blockers"] == ["one or more clients require owner permission verification"]


@pytest.mark.parametrize("prefix", ["", "2026-11-05T09:00:00.0000000Z ##[warning]"])
def test_unavailable_identity_blocks_even_with_another_observed_client(prefix):
    log = diagnostic() + prefix + "Guarded merge credential identity unavailable: HTTP 403\n"
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["blockers"] == ["one or more merge-client identities were unavailable"]


def test_script_echo_and_unrelated_log_content_are_not_diagnostics():
    log = "core.info(`" + diagnostic().strip() + "`);\nUNRELATED_PRIVATE_LOG_VALUE\n"
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["attempts"] == []
    assert report["blockers"] == ["no merge-client identity diagnostics observed"]
    assert "UNRELATED_PRIVATE_LOG_VALUE" not in json.dumps(report)


def test_echoed_warning_does_not_block_an_observed_identity():
    log = diagnostic(actor="automation[bot]") + (
        "core.warning(`Guarded merge credential identity unavailable: HTTP ${status}`);\n"
    )
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["attempts"][0]["actor"] == "automation[bot]"
    assert report["blockers"] == []


@pytest.mark.parametrize("workflow", ["", "[]", "jobs: []", "jobs: {guarded-merge: null}"])
def test_malformed_workflow_cannot_match(workflow):
    with pytest.raises(ValueError, match="no guarded-merge job"):
        checker.inspect_deployment(workflow, workflow, diagnostic())


@pytest.mark.parametrize(
    ("consumer", "log", "exit_code"),
    [
        (WORKFLOW, diagnostic(), 0),
        (WORKFLOW, "", 2),
        (WORKFLOW.replace("run: guarded", "run: old"), diagnostic(), 1),
    ],
)
def test_cli_outputs_inspection_and_exit_status(tmp_path, capsys, consumer, log, exit_code):
    for filename, content in [
        ("source.yml", WORKFLOW),
        ("consumer.yml", consumer),
        ("job.log", log),
    ]:
        (tmp_path / filename).write_text(content, encoding="utf-8")
    result = checker.main(
        [
            "--template",
            str(tmp_path / "source.yml"),
            "--consumer-workflow",
            str(tmp_path / "consumer.yml"),
            "--job-log",
            str(tmp_path / "job.log"),
        ]
    )
    assert result == exit_code
    assert json.loads(capsys.readouterr().out)["effective_permissions_confirmed"] is False


def test_cli_parse_errors_do_not_echo_input(tmp_path, capsys):
    bad = tmp_path / "bad.yml"
    bad.write_text("jobs: [UNRELATED_PRIVATE_LOG_VALUE", encoding="utf-8")
    assert (
        checker.main(
            ["--template", str(bad), "--consumer-workflow", str(bad), "--job-log", str(bad)]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out) == {
        "error": "unable to read or parse deployment inputs"
    }
