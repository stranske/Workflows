import json
import subprocess

import pytest
import yaml
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


def test_real_template_inherited_credential_environment_drift_is_blocked():
    template = checker.TEMPLATE.read_text(encoding="utf-8")
    consumer = yaml.safe_load(template)
    consumer["env"]["WRITE_TOKEN"] = "consumer-writer"
    # The job itself is unchanged; only its inherited client selection differs.
    assert consumer["jobs"]["guarded-merge"] == yaml.safe_load(template)["jobs"]["guarded-merge"]
    report = checker.inspect_deployment(template, yaml.safe_dump(consumer), diagnostic())
    assert report["job_matches_source"] is False
    assert report["blockers"] == ["consumer guarded-merge job differs from selected source"]


def test_inherited_permission_drift_is_blocked():
    template = "permissions: {contents: write, pull-requests: write}\n" + WORKFLOW
    consumer = template.replace("contents: write", "contents: read")
    report = checker.inspect_deployment(template, consumer, diagnostic())
    assert report["job_matches_source"] is False


def test_job_overrides_ignore_shadowed_workflow_configuration():
    template = yaml.safe_load(WORKFLOW)
    template["env"] = {"WRITER": "workflow-writer"}
    template["permissions"] = {"contents": "read", "pull-requests": "read"}
    job = template["jobs"]["guarded-merge"]
    job["env"] = {"WRITER": "job-writer"}
    job["permissions"] = {"contents": "write", "pull-requests": "write"}
    source = yaml.safe_dump(template)
    template["env"]["WRITER"] = "other-workflow-writer"
    template["permissions"] = "read-all"
    report = checker.inspect_deployment(source, yaml.safe_dump(template), diagnostic())
    assert report["job_matches_source"] is True
    assert report["blockers"] == []


def test_job_permission_map_replaces_workflow_permissions():
    template = yaml.safe_load(WORKFLOW)
    template["permissions"] = {"contents": "write", "pull-requests": "write"}
    source = yaml.safe_dump(template)
    template["jobs"]["guarded-merge"]["permissions"] = {"contents": "write"}
    report = checker.inspect_deployment(source, yaml.safe_dump(template), diagnostic())
    assert report["job_matches_source"] is False


@pytest.mark.parametrize("level", ["workflow", "job"])
def test_invalid_environment_cannot_establish_deployment_match(level):
    workflow = yaml.safe_load(WORKFLOW)
    target = workflow if level == "workflow" else workflow["jobs"]["guarded-merge"]
    target["env"] = "unsupported environment"
    invalid = yaml.safe_dump(workflow)
    with pytest.raises(ValueError, match="environment must be a mapping"):
        checker.inspect_deployment(invalid, invalid, diagnostic())


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


@pytest.mark.parametrize(
    "incomplete",
    [
        "source=RETRY_PAT; actor=***; OAuth scopes=repo",
        "source=***; actor=writer; OAuth scopes=repo",
        "source=RETRY_PAT; actor=; OAuth scopes=repo",
        "source=RETRY_PAT; actor=writer",
        "source=RETRY_PAT",
        "source",
    ],
)
@pytest.mark.parametrize("position", ["before", "after"])
def test_incomplete_retry_diagnostic_cannot_borrow_another_clients_evidence(incomplete, position):
    line = f"2026-11-05T09:00:00.0000000Z Guarded merge credential {incomplete}\n"
    log = line + diagnostic() if position == "before" else diagnostic() + line
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["attempts"] == [
        {"source": "FIRST_PAT", "actor": "writer", "classic_repo_scope_reported": True}
    ]
    assert report["blockers"] == ["one or more merge-client identity diagnostics were incomplete"]
    assert report["effective_permissions_confirmed"] is False


def test_incomplete_identity_without_another_client_blocks_without_echoing_input():
    log = "Guarded merge credential source=UNRELATED_PRIVATE_LOG_VALUE\n"
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["attempts"] == []
    assert report["blockers"] == [
        "no merge-client identity diagnostics observed",
        "one or more merge-client identity diagnostics were incomplete",
    ]
    assert "UNRELATED_PRIVATE_LOG_VALUE" not in json.dumps(report)


@pytest.mark.parametrize("prefix", ["", "2026-11-05T09:00:00.0000000Z "])
def test_complete_diagnostics_accept_raw_job_log_line_endings(prefix):
    line = diagnostic().split("Z ", 1)[1].rstrip("\n")
    log = prefix + line + "\r\n"
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert report["attempts"] == [
        {"source": "FIRST_PAT", "actor": "writer", "classic_repo_scope_reported": True}
    ]
    assert report["blockers"] == []


@pytest.mark.parametrize("source", ["WRITE_TOKEN fallback", "WRITE_TOKEN", "unknown", "UNKNOWN"])
def test_ambiguous_source_cannot_identify_credential_even_with_repo_scope(source):
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, diagnostic(source=source))
    assert report["attempts"][0]["classic_repo_scope_reported"] is True
    assert report["blockers"] == [
        "one or more clients did not identify a specific credential source"
    ]


def test_retry_with_same_actor_cannot_borrow_previous_clients_credential_source():
    log = diagnostic("FIRST_PAT", "writer") + diagnostic("WRITE_TOKEN fallback", "writer")
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, log)
    assert len(report["attempts"]) == 2
    assert report["blockers"] == [
        "one or more clients did not identify a specific credential source"
    ]
    assert report["effective_permissions_confirmed"] is False


@pytest.mark.parametrize(
    "source", ["AGENTS_AUTOMATION_PAT", "PAT_1", "WORKFLOWS_APP", "github.token"]
)
def test_specific_credential_sources_are_recognized_without_claiming_permissions(source):
    report = checker.inspect_deployment(WORKFLOW, WORKFLOW, diagnostic(source=source))
    assert report["blockers"] == []
    assert report["effective_permissions_confirmed"] is False


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
        (WORKFLOW, diagnostic() + "Guarded merge credential source=RETRY_PAT\n", 2),
        (WORKFLOW, diagnostic(source="WRITE_TOKEN fallback"), 2),
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


@pytest.fixture
def hosted_api(monkeypatch):
    run = {
        "id": 123,
        "repository": {"full_name": "owner/consumer"},
        "path": checker.WORKFLOW_PATH,
        "event": "repository_dispatch",
        "head_sha": "a" * 40,
        "run_attempt": 2,
        "status": "completed",
    }
    job = {
        "id": 456,
        "name": "guarded-merge",
        "run_id": 123,
        "run_attempt": 2,
        "head_sha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
    }
    calls = []
    pages = [{"jobs": [{"name": "unrelated"}]}, {"jobs": [job]}]

    def read(endpoint, *, raw=False, paginate=False):
        calls.append((endpoint, raw, paginate))
        if endpoint.endswith("/runs/123"):
            return dict(run)
        if "/contents/" in endpoint:
            assert endpoint.endswith("?ref=" + "a" * 40)
            assert raw and not paginate
            return WORKFLOW
        if endpoint.endswith("/attempts/2/jobs?per_page=100"):
            assert paginate and not raw
            return pages
        assert endpoint == "repos/owner/consumer/actions/jobs/456/logs"
        assert raw and not paginate
        return diagnostic()

    monkeypatch.setattr(checker, "gh_read", read)
    return run, job, pages, calls


def test_hosted_collection_uses_exact_revision_attempt_and_paginated_job(hosted_api):
    consumer, log, provenance = checker.collect_hosted("owner/consumer", 123, WORKFLOW)
    assert consumer == WORKFLOW
    report = checker.inspect_deployment(WORKFLOW, consumer, log)
    assert report["blockers"] == []
    assert report["effective_permissions_confirmed"] is False
    assert provenance == {
        "repo": "owner/consumer",
        "run_id": 123,
        "run_attempt": 2,
        "event": "repository_dispatch",
        "head_sha": "a" * 40,
        "job_id": 456,
    }
    assert len(hosted_api[3]) == 5


@pytest.mark.parametrize("event", ["workflow_dispatch", "repository_dispatch"])
def test_hosted_collection_accepts_current_and_legacy_dispatch_events(hosted_api, event):
    run, _, _, calls = hosted_api
    run["event"] = event
    run["display_title"] = "keepalive-dispatch/v2 ordinary pr=42"
    consumer, log, provenance = checker.collect_hosted("owner/consumer", 123, WORKFLOW)
    assert provenance["event"] == event
    assert provenance["run_attempt"] == 2
    report = checker.inspect_deployment(WORKFLOW, consumer, log)
    assert report["blockers"] == []
    assert report["effective_permissions_confirmed"] is False
    assert report["merge_success_confirmed"] is False
    assert len(calls) == 5


@pytest.mark.parametrize("event", ["pull_request_target", "workflow_run", "schedule", "push"])
def test_keepalive_run_title_cannot_make_an_unrelated_event_a_dispatch(hosted_api, event):
    run, _, _, calls = hosted_api
    run["event"] = event
    run["display_title"] = "keepalive-dispatch/v2 ordinary pr=42"
    with pytest.raises(ValueError, match="completed consumer dispatch attempt"):
        checker.collect_hosted("owner/consumer", 123, WORKFLOW)
    assert len(calls) == 1


@pytest.mark.parametrize("dispatch_event", ["workflow_dispatch", "repository_dispatch"])
@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("run", "id", 999),
        ("run", "repository", {"full_name": "another/consumer"}),
        ("run", "path", ".github/workflows/ci.yml"),
        ("run", "event", "pull_request"),
        ("run", "status", "in_progress"),
        ("run", "head_sha", "main"),
        ("run", "run_attempt", 0),
        ("job", "id", "456"),
        ("job", "run_id", 999),
        ("job", "run_attempt", 1),
        ("job", "head_sha", "b" * 40),
        ("job", "status", "in_progress"),
        ("job", "conclusion", "skipped"),
    ],
)
def test_hosted_collection_rejects_unbound_run_or_job(
    hosted_api, dispatch_event, target, field, value
):
    run, job, _, calls = hosted_api
    run["event"] = dispatch_event
    (run if target == "run" else job)[field] = value
    with pytest.raises(ValueError):
        checker.collect_hosted("owner/consumer", 123, WORKFLOW)
    assert not any(endpoint.endswith("/logs") for endpoint, _, _ in calls)


@pytest.mark.parametrize("count", [0, 2])
def test_hosted_collection_rejects_missing_or_duplicate_guarded_jobs(hosted_api, count):
    _, job, pages, _ = hosted_api
    pages[:] = [{"jobs": [dict(job) for _ in range(count)]}]
    with pytest.raises(ValueError, match="exactly one"):
        checker.collect_hosted("owner/consumer", 123, WORKFLOW)


def test_hosted_collection_rejects_attempt_change_during_log_download(hosted_api, monkeypatch):
    read = checker.gh_read

    def read_with_rerun(endpoint, **kwargs):
        result = read(endpoint, **kwargs)
        if endpoint.endswith("/logs"):
            hosted_api[0]["run_attempt"] = 3
        return result

    monkeypatch.setattr(checker, "gh_read", read_with_rerun)
    with pytest.raises(ValueError, match="run changed"):
        checker.collect_hosted("owner/consumer", 123, WORKFLOW)


def test_hosted_cli_retains_public_provenance_without_claiming_acceptance(
    hosted_api, tmp_path, capsys
):
    source = tmp_path / "source.yml"
    source.write_text(WORKFLOW)
    assert (
        checker.main(["--template", str(source), "--repo", "owner/consumer", "--run-id", "123"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["hosted_run"]["run_attempt"] == 2
    assert report["effective_permissions_confirmed"] is False
    assert report["merge_success_confirmed"] is False


def test_hosted_cli_api_failure_does_not_echo_response(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.yml"
    source.write_text(WORKFLOW)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["gh"], stderr="PRIVATE_RESPONSE")

    monkeypatch.setattr(checker, "gh_read", fail)
    assert (
        checker.main(["--template", str(source), "--repo", "owner/consumer", "--run-id", "123"])
        == 2
    )
    assert json.loads(capsys.readouterr().out) == {
        "error": "unable to read or parse deployment inputs"
    }


def test_gh_transport_uses_only_get_and_captures_logs(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[:4] == ["gh", "api", "--method", "GET"]
        assert kwargs == {"capture_output": True, "text": True, "timeout": 30, "check": True}
        return subprocess.CompletedProcess(command, 0, stdout="[]")

    monkeypatch.setattr(checker.subprocess, "run", run)
    assert checker.gh_read("repos/owner/consumer/actions/runs/123") == []
    assert checker.gh_read("jobs", paginate=True) == []
    assert calls[-1][-2:] == ["--paginate", "--slurp"]
    assert checker.gh_read("logs", raw=True) == "[]"
    assert calls[-1][-2:] == ["-H", "Accept: application/vnd.github.raw+json"]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--repo", "owner/consumer"],
        ["--run-id", "123"],
        ["--consumer-workflow", "consumer.yml"],
        ["--job-log", "job.log"],
        ["--repo", "owner/consumer", "--run-id", "123", "--job-log", "job.log"],
    ],
)
def test_cli_rejects_mixed_or_incomplete_input_modes(args, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid arguments must not make API requests")

    monkeypatch.setattr(checker, "gh_read", unexpected)
    with pytest.raises(SystemExit) as error:
        checker.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize(("repo", "run_id"), [("owner/repo/other", 123), ("owner/repo", 0)])
def test_hosted_collection_validates_identifiers_before_api_access(hosted_api, repo, run_id):
    with pytest.raises(ValueError, match="invalid repository or run id"):
        checker.collect_hosted(repo, run_id, WORKFLOW)
    assert hosted_api[3] == []
