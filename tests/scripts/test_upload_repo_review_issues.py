import json
from pathlib import Path

import pytest
from scripts import upload_repo_review_issues as uploader

VALID_BODY = """## Why

The repo needs a deterministic local smoke so agents can prove the reviewed workflow instead of relying on manual inspection.

## Scope

- Add one focused smoke around the documented local path.
- Keep fixtures deterministic and offline.

## Non-Goals

- Do not add live external services.
- Do not refactor unrelated modules.

## Tasks

- [ ] Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.
- [ ] Add fixture data under `tests/fixtures/local_smoke/` that exercises the reviewed path.
- [ ] Assert `tests/test_local_smoke.py` fails when the primary output object is missing.
- [ ] Document the smoke command in `docs/local-testing.md`.

## Acceptance Criteria

- [ ] `python -m pytest tests/test_local_smoke.py --no-cov` exits zero with local fixtures.
- [ ] The smoke fails with a clear assertion if the primary output object is not created.
- [ ] Documentation names the command and the fixture data used by the smoke.

## Implementation Notes

Relevant files: `tests/test_local_smoke.py`, `tests/fixtures/local_smoke/`, `docs/local-testing.md`.
"""

VALID_TRACE = {
    "candidate_title_patterns": ["^Do work$|^Existing issue$|^New issue$"],
    "gap": "The documented local workflow lacks a deterministic smoke gate.",
    "current_state": "The repo has docs and tests but no smoke covering the reviewed path.",
    "required_change": "Add a local fixture-backed smoke and document the command.",
    "design_refs": ["README.md", "docs/local-testing.md"],
    "implementation_refs": ["src/local_workflow.py"],
    "test_refs": ["tests/test_local_smoke.py"],
}


def issue(title: str = "Do work", body: str = VALID_BODY) -> dict:
    return {
        "repo": "owner/repo",
        "title": title,
        "body": body,
        "review_evidence_trace": VALID_TRACE,
    }


def test_load_queue_returns_issue_list(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"issues": [issue()]}), encoding="utf-8")

    assert uploader.load_queue(queue) == [issue()]


def test_load_queue_rejects_generic_issue_body(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    bad_body = VALID_BODY.replace(
        "Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.",
        "Implement the approved review gap: Add a smoke test.",
    )
    queue.write_text(json.dumps({"issues": [issue(body=bad_body)]}), encoding="utf-8")

    try:
        uploader.load_queue(queue)
    except ValueError as exc:
        assert "approved issue queue failed quality validation" in str(exc)
    else:
        raise AssertionError("expected quality validation failure")


def test_load_queue_rejects_missing_review_evidence_trace(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps({"issues": [{"repo": "owner/repo", "title": "Do work", "body": VALID_BODY}]}),
        encoding="utf-8",
    )

    try:
        uploader.load_queue(queue)
    except ValueError as exc:
        assert "review evidence trace is missing or not an object" in str(exc)
    else:
        raise AssertionError("expected review evidence validation failure")


def test_upload_dry_run_skips_exact_title_duplicates(monkeypatch) -> None:
    def fake_fetch_open_issues(repo: str, prefix: list[str]):
        assert repo == "owner/repo"
        assert prefix == ["gh"]
        return [
            {
                "number": 5,
                "title": "Existing issue",
                "url": "https://github.test/owner/repo/issues/5",
                "labels": [],
            }
        ]

    monkeypatch.setattr(uploader, "fetch_open_issues", fake_fetch_open_issues)
    issues = [issue("Existing issue") | {"labels": []}, issue("New issue") | {"labels": []}]

    summary = uploader.upload_issues(issues, prefix=["gh"], apply=False)

    assert summary["skipped_duplicates"] == [
        {
            "repo": "owner/repo",
            "title": "Existing issue",
            "number": 5,
            "url": "https://github.test/owner/repo/issues/5",
        }
    ]
    assert summary["would_create"] == [{"repo": "owner/repo", "title": "New issue"}]


def test_fetch_open_issues_queries_state_all(monkeypatch) -> None:
    """Materialization ledger (#2272): dedup must see closed issues. The list
    query uses `--state all` (not `open`) and pulls `body` so the per-item
    marker can be matched."""
    captured: dict[str, list[str]] = {}

    def fake_run(args, *, label=""):
        captured["args"] = args

        class _R:
            stdout = "[]"

        return _R()

    monkeypatch.setattr(uploader, "run_command_with_retry", fake_run)
    uploader.fetch_open_issues("owner/repo", ["gh"])
    args = captured["args"]
    assert "--state" in args and args[args.index("--state") + 1] == "all"
    json_fields = args[args.index("--json") + 1]
    assert "body" in json_fields


def test_upload_skips_recently_closed_item_by_marker(monkeypatch) -> None:
    """#2272 deliberate-break gate: a queue item whose issue was already created
    AND CLOSED must not be recreated. The closed issue carries the per-item
    marker; dedup matches on it even though the closed issue's title was edited.

    Break demonstration: reverting `fetch_open_issues` to `--state open` (so the
    closed issue is invisible) OR dropping the `find_marker_duplicate` call from
    `upload_issues` makes this item fall through to `would_create` and the
    assertion below fails.
    """
    marker = uploader.item_marker("owner/repo", "Add a deterministic smoke gate")
    closed_body = f"## Why\nAlready shipped last cycle.\n\n{marker}\n"

    def fake_fetch(repo: str, prefix: list[str]):
        return [
            {
                "number": 42,
                "title": "Renamed after triage",  # title drifted; marker is stable
                "state": "CLOSED",
                "url": "https://github.test/owner/repo/issues/42",
                "labels": [{"name": "repo-review-approved"}],
                "body": closed_body,
            }
        ]

    monkeypatch.setattr(uploader, "fetch_open_issues", fake_fetch)
    issues = [issue("Add a deterministic smoke gate") | {"labels": ["repo-review-approved"]}]

    summary = uploader.upload_issues(issues, prefix=["gh"], apply=False)

    assert summary["would_create"] == []
    assert summary["skipped_duplicates"] == [
        {
            "repo": "owner/repo",
            "title": "Add a deterministic smoke gate",
            "number": 42,
            "url": "https://github.test/owner/repo/issues/42",
        }
    ]


def test_create_issue_stamps_item_marker(monkeypatch) -> None:
    """create_issue appends the per-item marker to the body it writes, so the
    materialized issue is self-identifying on future dedup passes."""
    written: dict[str, str] = {}

    def fake_run(args, *, label=""):
        body_path = args[args.index("--body-file") + 1]
        written["body"] = Path(body_path).read_text(encoding="utf-8")

        class _R:
            stdout = "https://github.test/owner/repo/issues/7\n"

        return _R()

    monkeypatch.setattr(uploader, "run_command_with_retry", fake_run)
    url = uploader.create_issue(
        issue("Add a deterministic smoke gate") | {"labels": ["repo-review-approved"]},
        ["gh"],
    )
    assert url == "https://github.test/owner/repo/issues/7"
    expected_marker = uploader.item_marker("owner/repo", "Add a deterministic smoke gate")
    assert expected_marker in written["body"]
    # Idempotent: re-stamping a body that already has the marker does not duplicate it.
    restamped = uploader.body_with_item_marker(
        "owner/repo", "Add a deterministic smoke gate", written["body"]
    )
    assert restamped.count("repo-review-item:") == 1


def test_main_refuses_held_queue_before_any_github_operation(tmp_path, monkeypatch, capsys):
    import argparse

    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"issues": [], "intake_hold": {"active": True}}))
    args = argparse.Namespace(queue=path, apply=True, gh_prefix="gh", repo=[])
    monkeypatch.setattr(uploader, "parse_args", lambda: args)
    monkeypatch.setattr(uploader, "upload_issues", lambda *a, **k: pytest.fail("must not upload"))
    assert uploader.main() == 2
    assert "hold active" in capsys.readouterr().err


def test_main_refuses_unresolved_approved_scope_conflicts_before_github(
    tmp_path, monkeypatch, capsys
):
    import argparse

    path = tmp_path / "queue.json"
    path.write_text(
        json.dumps(
            {
                "issues": [],
                "intake_hold": {"active": False},
                "upload_allowed": True,
                "approval_scope_conflicts": [{"disposition": "reconciliation_required"}],
            }
        )
    )
    monkeypatch.setattr(
        uploader,
        "parse_args",
        lambda: argparse.Namespace(queue=path, apply=True, gh_prefix="gh", repo=[]),
    )
    monkeypatch.setattr(uploader, "upload_issues", lambda *a, **k: pytest.fail("must not upload"))
    assert uploader.main() == 2
    assert "scope conflicts" in capsys.readouterr().err


@pytest.fixture(autouse=True)
def no_live_prompt_tools(tmp_path, monkeypatch):
    # Unit tests must never consult this machine's real authoring fleet.
    monkeypatch.setattr(uploader, "ORCHESTRATOR_MIRROR", tmp_path / "absent-mirror")
    monkeypatch.setattr(
        uploader.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("unexpected subprocess; no live uploads or tools"),
    )


def authoring_tools(tmp_path, monkeypatch, *, failed=None, invalid_claim=False):
    import subprocess

    mirror = tmp_path / "mirror"
    mirror.mkdir()
    for name in ("capability_advisor.py", "roles.py", "capability_propensity.py"):
        (mirror / name).touch()
    monkeypatch.setattr(uploader, "ORCHESTRATOR_MIRROR", mirror)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        name = Path(args[1]).name
        if name == "capability_advisor.py":
            assert args[args.index("--surface") + 1] == "repo-review-uploader"
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "experiment_id": "advice:test",
                        "capabilities": [{"capability_id": "role-prompt"}],
                    }
                ),
                "",
            )
        if name == "roles.py":
            assert "--dispatch" in args
            assert args[args.index("--output") + 1] == "issue_body"
            batch = json.loads(Path(args[args.index("--batch") + 1]).read_text())
            directory = Path(args[args.index("--output-dir") + 1])
            directory.mkdir()
            rows = []
            for index, item in enumerate(batch):
                assert VALID_BODY in item["context"]
                body = VALID_BODY.replace("## Why\n", "## Why\n\n")
                valid = index != failed
                body_path = directory / f"{index}.md"
                body_path.write_text(body if valid else "rejected incomplete body")
                rows.append(
                    {
                        "target": item["target"],
                        "valid": valid or invalid_claim,
                        "body_file": str(body_path) if valid or invalid_claim else None,
                        "failed_body_file": None if valid else str(body_path),
                        "errors": [] if valid or invalid_claim else ["body validation failed"],
                        "role_record_error": None,
                    }
                )
            (directory / "manifest.json").write_text(json.dumps({"items": rows}))
            return subprocess.CompletedProcess(
                args, int(failed is not None), "manifest retained", ""
            )
        assert name == "capability_propensity.py"
        return subprocess.CompletedProcess(args, 0, "{}", "")

    monkeypatch.setattr(uploader.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("failed,invalid_claim", [(None, False), (1, False), (1, True)])
def test_three_item_authoring_keeps_per_item_fallback_and_failure_manifest(
    tmp_path, monkeypatch, failed, invalid_claim
):
    calls = authoring_tools(tmp_path, monkeypatch, failed=failed, invalid_claim=invalid_claim)
    monkeypatch.setattr(uploader, "fetch_open_issues", lambda *args: [])
    monkeypatch.setattr(uploader, "ensure_labels", lambda *args: None)
    created = []

    def create(item, prefix):
        created.append(item)
        return f"https://github.test/owner/repo/issues/{100 + len(created)}"

    monkeypatch.setattr(uploader, "create_issue", create)
    items = [issue(title) for title in ("Alpha", "Beta", "Gamma")]
    summary = uploader.upload_issues(
        items, prefix=["gh"], apply=True, authoring_dir=tmp_path / "evidence"
    )
    assert len(summary["created"]) == len(created) == 3
    assert [item["title"] for item in created] == [item["title"] for item in items]
    for index, item in enumerate(created):
        if index == failed:
            assert item["body"] == VALID_BODY
            assert not summary["authoring"]["items"][index]["used_role"]
        else:
            assert item["body"] == VALID_BODY.replace("## Why\n", "## Why\n\n")
            assert item["review_evidence_trace"] == VALID_TRACE
    assert sum(Path(args[1]).name == "capability_advisor.py" for args in calls) == 1
    assert sum(Path(args[1]).name == "roles.py" for args in calls) == 1
    triggers = [args for args in calls if "trigger" in args]
    assert len(triggers) == (3 if failed is None else 2)
    assert all(
        args[args.index("--deliverable") + 1].startswith("owner/repo#10") for args in triggers
    )
    manifest = json.loads(Path(summary["authoring"]["role_manifest"]).read_text())
    if failed is not None:
        assert (
            Path(manifest["items"][failed]["failed_body_file"]).read_text()
            == "rejected incomplete body"
        )
        assert summary["authoring"]["items"][failed]["errors"]


def test_small_batch_consults_once_and_records_decline(tmp_path, monkeypatch):
    calls = authoring_tools(tmp_path, monkeypatch)
    selected, receipt = uploader.author_issue_batch([issue()], output_root=tmp_path / "evidence")
    assert selected == [issue()]
    assert receipt["state"] == "baseline"
    assert not any(Path(args[1]).name == "roles.py" for args in calls)
    declines = [args for args in calls if "decline" in args]
    assert len(declines) == 1
    assert declines[0][declines[0].index("--kind") + 1] == "scope_too_small"


def test_consult_batches_only_new_filtered_items_across_repos(tmp_path, monkeypatch):
    calls = authoring_tools(tmp_path, monkeypatch)
    existing = {"number": 7, "title": "Existing issue", "labels": []}
    monkeypatch.setattr(
        uploader,
        "fetch_open_issues",
        lambda repo, prefix: [existing] if repo == "owner/repo" else [],
    )
    monkeypatch.setattr(uploader, "ensure_labels", lambda *args: None)
    monkeypatch.setattr(uploader, "add_missing_labels", lambda *args: None)
    created = []

    def create(item, prefix):
        created.append(item)
        return f"https://github.test/{item['repo']}/issues/{100 + len(created)}"

    monkeypatch.setattr(uploader, "create_issue", create)
    eligible = [
        issue("Alpha") | {"labels": ["priority:high"]},
        issue("Beta") | {"labels": ["priority:normal"]},
        issue("Gamma") | {"repo": "owner/other", "labels": ["priority:low"]},
    ]
    result = uploader.upload_issues(
        [issue("Existing issue"), *eligible, eligible[0], issue() | {"repo": "owner/excluded"}],
        prefix=["gh"],
        apply=True,
        repo_filter={"owner/repo", "owner/other"},
        authoring_dir=tmp_path / "evidence",
    )
    assert len(result["created"]) == 3
    assert len(result["skipped_duplicates"]) == 2
    assert {item["title"] for item in created} == {item["title"] for item in eligible}
    for item in created:
        original = next(row for row in eligible if row["title"] == item["title"])
        assert item["repo"] == original["repo"]
        assert item["labels"] == original["labels"]
    assert sum(Path(args[1]).name == "capability_advisor.py" for args in calls) == 1
    assert sum(Path(args[1]).name == "roles.py" for args in calls) == 1
    directory = Path(result["authoring"]["directory"])
    batch = json.loads((directory / "batch.json").read_text())
    assert len(batch) == 3
    assert {row["goal"] for row in batch} == {item["title"] for item in eligible}


def test_missing_mirror_keeps_original_bodies_without_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(
        uploader.subprocess, "run", lambda *args, **kwargs: pytest.fail("no local tools")
    )
    selected, receipt = uploader.author_issue_batch(
        [issue()] * 3, output_root=tmp_path / "evidence"
    )
    assert selected == [issue()] * 3
    assert receipt == {"state": "mirror-unavailable"}
    assert not (tmp_path / "evidence").exists()


@pytest.mark.parametrize("missing", ["roles.py", "capability_propensity.py"])
def test_partial_mirror_still_consults_once_and_retains_decline(tmp_path, monkeypatch, missing):
    calls = authoring_tools(tmp_path, monkeypatch)
    (uploader.ORCHESTRATOR_MIRROR / missing).unlink()
    items = [issue(title) for title in ("Alpha", "Beta", "Gamma")]

    selected, receipt = uploader.author_issue_batch(items, output_root=tmp_path / "evidence")

    assert selected == items
    assert receipt["state"] == "baseline"
    assert receipt["experiment_id"] == "advice:test"
    assert receipt["missing_tools"] == [missing]
    assert sum(Path(args[1]).name == "capability_advisor.py" for args in calls) == 1
    assert not any(Path(args[1]).name == "roles.py" for args in calls)
    assert receipt["decline"]["kind"] == "precondition_unmet"
    assert receipt["decline"]["exit"] == (1 if missing == "capability_propensity.py" else 0)
    directory = Path(receipt["directory"])
    assert json.loads((directory / "upload-authoring.json").read_text()) == receipt
    if missing == "capability_propensity.py":
        assert missing in (directory / f"{missing}.stderr.txt").read_text()
    else:
        decline = next(args for args in calls if "decline" in args)
        assert decline[decline.index("--experiment") + 1] == "advice:test"
        assert missing in decline[decline.index("--reason") + 1]


def test_role_body_must_name_a_runnable_acceptance_gate():
    start = VALID_BODY.index("## Acceptance Criteria")
    end = VALID_BODY.index("## Implementation Notes")
    body = (
        VALID_BODY[:start]
        + "## Acceptance Criteria\n\n"
        + "\n".join(
            [
                "- [ ] The implementation matches every approved requirement in the documented workflow."
            ]
            * 3
        )
        + "\n\n"
        + VALID_BODY[end:]
    )
    assert not uploader.issue_body_quality_errors(body)
    assert any("names no test" in error for error in uploader.role_body_errors(body))


def test_upload_rechecks_original_identity_after_authoring(tmp_path, monkeypatch):
    authoring_tools(tmp_path, monkeypatch)
    items = [issue(title) for title in ("Alpha", "Beta", "Gamma")]
    fetches = []
    existing = {
        "number": 7,
        "title": "Renamed remotely",
        "url": "https://github.test/owner/repo/issues/7",
        "body": uploader.body_with_item_marker("owner/repo", "Beta", VALID_BODY),
        "labels": [],
    }

    def fetch(*args):
        fetches.append(args)
        return [] if len(fetches) == 1 else [existing]

    monkeypatch.setattr(uploader, "fetch_open_issues", fetch)
    monkeypatch.setattr(uploader, "ensure_labels", lambda *args: None)
    monkeypatch.setattr(uploader, "add_missing_labels", lambda *args: None)
    created = []

    def create(item, prefix):
        created.append(item["title"])
        return f"https://github.test/owner/repo/issues/{100 + len(created)}"

    monkeypatch.setattr(uploader, "create_issue", create)
    summary = uploader.upload_issues(
        items, prefix=["gh"], apply=True, authoring_dir=tmp_path / "evidence"
    )
    assert created == ["Alpha", "Gamma"]
    assert summary["skipped_duplicates"][0]["number"] == 7
    assert "trigger" not in summary["authoring"]["items"][1]


def test_dry_run_never_consults_or_authors(tmp_path, monkeypatch):
    monkeypatch.setattr(uploader, "fetch_open_issues", lambda *args: [])
    monkeypatch.setattr(
        uploader, "author_issue_batch", lambda *args, **kwargs: pytest.fail("dry run")
    )
    result = uploader.upload_issues([issue()], prefix=["gh"], apply=False)
    assert result["would_create"] == [{"repo": "owner/repo", "title": "Do work"}]


@pytest.mark.parametrize("failure", ["os-error", "invalid-json", "no-offer"])
def test_advisor_failure_or_no_offer_preserves_baseline(tmp_path, monkeypatch, failure):
    import subprocess

    authoring_tools(tmp_path, monkeypatch)

    def run(args, **kwargs):
        assert Path(args[1]).name == "capability_advisor.py"
        if failure == "os-error":
            raise OSError("optional tool unavailable")
        return subprocess.CompletedProcess(
            args, 0, "not json" if failure == "invalid-json" else "{}", ""
        )

    monkeypatch.setattr(uploader.subprocess, "run", run)
    selected, receipt = uploader.author_issue_batch(
        [issue()] * 3, output_root=tmp_path / "evidence"
    )
    assert selected == [issue()] * 3
    assert receipt["state"] == "baseline"
    assert not receipt["offered"]


@pytest.mark.parametrize("capabilities", [True, 1, "role-prompt", {"capability_id": "role-prompt"}])
def test_malformed_advisor_capabilities_preserve_baseline(tmp_path, monkeypatch, capabilities):
    import subprocess

    authoring_tools(tmp_path, monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert Path(args[1]).name == "capability_advisor.py"
        return subprocess.CompletedProcess(args, 0, json.dumps({"capabilities": capabilities}), "")

    monkeypatch.setattr(uploader.subprocess, "run", run)
    items = [issue(title) for title in ("Alpha", "Beta", "Gamma")]
    selected, receipt = uploader.author_issue_batch(items, output_root=tmp_path / "evidence")
    assert selected == items
    assert receipt["state"] == "baseline"
    assert not receipt["offered"]
    assert len(calls) == 1


@pytest.mark.parametrize(
    "old,new",
    [
        (
            "Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.",
            "Implement a remote service in `tests/test_network.py` using existing public APIs.",
        ),
        (
            "- Keep fixtures deterministic and offline.",
            "- Keep fixtures deterministic and offline.\n- Add a new production database.",
        ),
        ("--no-cov", "-k easy"),
        ("The repo needs", "Also migrate production records. The repo needs"),
    ],
)
def test_structurally_valid_role_rewrite_cannot_change_approved_content(
    tmp_path, monkeypatch, old, new
):
    calls = authoring_tools(tmp_path, monkeypatch)
    original_run = uploader.subprocess.run

    def run(args, **kwargs):
        result = original_run(args, **kwargs)
        if Path(args[1]).name == "roles.py":
            directory = Path(args[args.index("--output-dir") + 1])
            for file in directory.glob("*.md"):
                file.write_text(VALID_BODY.replace(old, new))
        return result

    monkeypatch.setattr(uploader.subprocess, "run", run)
    items = [issue(title) for title in ("Alpha", "Beta", "Gamma")]
    selected, receipt = uploader.author_issue_batch(items, output_root=tmp_path / "evidence")
    assert not uploader.issue_body_quality_errors(VALID_BODY.replace(old, new))
    assert selected == items
    assert receipt["state"] == "baseline"
    assert all(
        any("changed approved content" in error for error in row["errors"])
        for row in receipt["items"]
    )
    assert any("decline" in args for args in calls)


def test_approved_code_spans_preserve_internal_whitespace():
    assert uploader.approval_body_key("Gate `echo 'a  b'`.") != uploader.approval_body_key(
        "Gate `echo 'a b'`."
    )


def test_post_authoring_snapshot_excludes_created_siblings(tmp_path, monkeypatch):
    authoring_tools(tmp_path, monkeypatch)
    created = []
    fetches = []

    def fetch(*args):
        fetches.append(args)
        return list(created)

    monkeypatch.setattr(uploader, "fetch_open_issues", fetch)
    monkeypatch.setattr(uploader, "ensure_labels", lambda *args: None)
    monkeypatch.setattr(
        uploader, "add_missing_labels", lambda *args: pytest.fail("must not dedup siblings")
    )

    def create(item, prefix):
        row = {
            **item,
            "number": 100 + len(created),
            "labels": [{"name": "repo-review-approved"}],
            "url": f"https://github.test/owner/repo/issues/{100+len(created)}",
        }
        created.append(row)
        return row["url"]

    monkeypatch.setattr(uploader, "create_issue", create)
    result = uploader.upload_issues(
        [issue(title) for title in ("Alpha", "Beta", "Gamma")],
        prefix=["gh"],
        apply=True,
        authoring_dir=tmp_path / "evidence",
    )
    assert len(result["created"]) == 3
    assert result["skipped_duplicates"] == []
    assert len(fetches) == 2  # initial and one post-authoring snapshot, before creation


@pytest.mark.parametrize(
    "fault",
    ["outside-directory", "duplicate-target", "record-error", "missing-body", "missing-row"],
)
def test_manifest_rejection_preserves_approved_bodies(tmp_path, monkeypatch, fault):
    authoring_tools(tmp_path, monkeypatch)
    original_run = uploader.subprocess.run

    def run(args, **kwargs):
        result = original_run(args, **kwargs)
        if Path(args[1]).name == "roles.py":
            file = Path(args[args.index("--output-dir") + 1]) / "manifest.json"
            manifest = json.loads(file.read_text())
            if fault == "outside-directory":
                outside = tmp_path / "outside.md"
                outside.write_text(VALID_BODY)
                manifest["items"][0]["body_file"] = str(outside)
            elif fault == "duplicate-target":
                manifest["items"].append(manifest["items"][0])
            elif fault == "missing-body":
                Path(manifest["items"][0]["body_file"]).unlink()
            elif fault == "missing-row":
                manifest["items"].pop(0)
            else:
                manifest["items"][0]["role_record_error"] = "Brain record failed"
            file.write_text(json.dumps(manifest))
        return result

    monkeypatch.setattr(uploader.subprocess, "run", run)
    items = [issue(title) for title in ("Alpha", "Beta", "Gamma")]
    selected, receipt = uploader.author_issue_batch(items, output_root=tmp_path / "evidence")
    assert selected[0]["body"] == VALID_BODY
    assert not receipt["items"][0]["used_role"]
    assert receipt["items"][1]["used_role"] == (fault != "duplicate-target")
    assert receipt["items"][2]["used_role"] == (fault != "duplicate-target")
    if fault == "duplicate-target":
        assert selected == items
        assert all(not row["used_role"] for row in receipt["items"])
