"""Tests for scripts/repo_review_docs_drift_scan.py.

The classifier and aggregator are pure functions and are exercised directly.
The end-to-end scan() call uses a fake invoker so no live LLM call is made;
the fake returns the seeded fixture drift responses (3 known drifts from the
2026-05-13 weekly cycle plus accurate-no-drift baselines) so the classifier
is verified against real-world cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import scripts.repo_review_docs_drift_scan as drift_scan
from scripts.repo_review_docs_drift_scan import (
    DriftInstance,
    aggregate,
    build_doc_prompt,
    is_gitnexus_stale,
    load_active_repos,
    load_docs_config,
    parse_drift_response,
    resolve_repo_root,
    resolve_workspace_root,
    scan,
    scan_doc,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "repo_review_docs_drift_scan" / "seeded_responses.json"
)
SEEDED_FIXTURE_RESPONSES: dict[str, str] = {
    key: json.dumps(value)
    for key, value in json.loads(FIXTURE_PATH.read_text(encoding="utf-8")).items()
}


# ---------------------------------------------------------------------------
# parse_drift_response
# ---------------------------------------------------------------------------


def test_parse_drift_response_extracts_seeded_stale():
    raw = SEEDED_FIXTURE_RESPONSES["README.md"]
    instances, err = parse_drift_response(raw, doc_path="README.md")
    assert err is None
    assert len(instances) == 2
    classifications = sorted(i.classification for i in instances)
    assert classifications == ["accurate-no-drift", "stale"]


def test_parse_drift_response_classifies_contradictory():
    raw = SEEDED_FIXTURE_RESPONSES["docs/ci/WORKFLOWS.md"]
    instances, err = parse_drift_response(raw, doc_path="docs/ci/WORKFLOWS.md")
    assert err is None
    assert len(instances) == 1
    assert instances[0].classification == "contradictory"


def test_parse_drift_response_handles_prose_wrapper():
    raw = (
        "Sure, here's the audit result:\n\n"
        '```json\n{"doc_path": "x.md", "instances": [{"claim": "c", '
        '"authoritative_source": "s", "classification": "stale"}]}\n```\n'
        "Let me know if you want detail."
    )
    instances, err = parse_drift_response(raw, doc_path="x.md")
    assert err is None
    assert len(instances) == 1
    assert instances[0].classification == "stale"


def test_parse_drift_response_drops_invalid_classification():
    raw = json.dumps(
        {
            "doc_path": "x.md",
            "instances": [
                {"claim": "c1", "authoritative_source": "s1", "classification": "stale"},
                {"claim": "c2", "authoritative_source": "s2", "classification": "ambiguous"},
            ],
        }
    )
    instances, err = parse_drift_response(raw, doc_path="x.md")
    assert err is None
    # Invalid classification dropped silently rather than failing the doc.
    assert len(instances) == 1
    assert instances[0].classification == "stale"


def test_parse_drift_response_empty():
    instances, err = parse_drift_response("", doc_path="x.md")
    assert instances == []
    assert err == "empty response"


def test_parse_drift_response_no_json():
    instances, err = parse_drift_response("just prose, no object", doc_path="x.md")
    assert instances == []
    assert "no JSON object" in err


def test_parse_drift_response_malformed_json():
    instances, err = parse_drift_response("{not valid json}", doc_path="x.md")
    assert instances == []
    assert err.startswith("JSON decode failed")


def test_parse_drift_response_uses_first_valid_instances_object():
    raw = (
        'Ignore this diagnostic object: {"note": "not payload"}\n'
        'Actual payload: {"instances": [{"claim": "c", '
        '"authoritative_source": "s", "classification": "stale"}]}\n'
        "Trailing brace text {not-json}"
    )
    instances, err = parse_drift_response(raw, doc_path="x.md")
    assert err is None
    assert len(instances) == 1
    assert instances[0].classification == "stale"


# ---------------------------------------------------------------------------
# Seeded-fixture classifier verification (acceptance-criteria check)
# ---------------------------------------------------------------------------


def test_seeded_three_known_drifts_classify_as_stale_or_contradictory():
    """The 2026-05-13 cycle confirmed 3 drift instances. Verify each is
    classified as stale or contradictory (NOT accurate-no-drift)."""
    expected = {
        "README.md": "stale",
        "docs/ci/WORKFLOWS.md": "contradictory",
        "docs/ops/REPO_REVIEW_PROCESS.md": "stale",
    }
    for doc_path, expected_class in expected.items():
        instances, err = parse_drift_response(SEEDED_FIXTURE_RESPONSES[doc_path], doc_path=doc_path)
        assert err is None, f"{doc_path} parse failed: {err}"
        drift_only = [i for i in instances if i.classification != "accurate-no-drift"]
        assert drift_only, f"{doc_path} should have at least one drift instance"
        assert drift_only[0].classification == expected_class


# ---------------------------------------------------------------------------
# GitNexus staleness
# ---------------------------------------------------------------------------


def test_gitnexus_status_missing(tmp_path: Path):
    assert is_gitnexus_stale(tmp_path) == "missing"


def test_gitnexus_status_fresh(tmp_path: Path):
    nexus = tmp_path / ".gitnexus"
    nexus.mkdir()
    (nexus / "meta.json").write_text(json.dumps({"stale": False}), encoding="utf-8")
    assert is_gitnexus_stale(tmp_path) == "fresh"


def test_gitnexus_status_stale(tmp_path: Path):
    nexus = tmp_path / ".gitnexus"
    nexus.mkdir()
    (nexus / "meta.json").write_text(json.dumps({"stale": True}), encoding="utf-8")
    assert is_gitnexus_stale(tmp_path) == "stale"


def test_gitnexus_status_malformed_falls_back_to_missing(tmp_path: Path):
    nexus = tmp_path / ".gitnexus"
    nexus.mkdir()
    (nexus / "meta.json").write_text("not json", encoding="utf-8")
    assert is_gitnexus_stale(tmp_path) == "missing"


def test_scan_doc_logs_gitnexus_skip_for_coordinator_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("dummy\n", encoding="utf-8")

    def fake_invoker(*, prompt: str, cwd: Path, timeout: int, log_file: Path):
        return True, '{"instances": []}'

    result = scan_doc(
        repo="stranske/Workflows",
        doc_path="README.md",
        doc_focus="model versions",
        repo_root=repo_root,
        log_dir=tmp_path / "logs",
        timeout=10,
        invoker=fake_invoker,
    )

    assert result.error is None
    assert result.gitnexus_status == "missing"
    captured = capsys.readouterr()
    assert "skipping behavioral check" in captured.out
    assert "README.md" in captured.out


def test_scan_doc_logs_gitnexus_skip_when_meta_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("dummy\n", encoding="utf-8")
    gitnexus_dir = repo_root / ".gitnexus"
    gitnexus_dir.mkdir()
    (gitnexus_dir / "meta.json").write_text(json.dumps({"stale": True}), encoding="utf-8")

    def fake_invoker(*, prompt: str, cwd: Path, timeout: int, log_file: Path):
        return True, '{"instances": []}'

    result = scan_doc(
        repo="stranske/Workflows",
        doc_path="README.md",
        doc_focus="model versions",
        repo_root=repo_root,
        log_dir=tmp_path / "logs",
        timeout=10,
        invoker=fake_invoker,
    )

    assert result.error is None
    assert result.gitnexus_status == "stale"
    captured = capsys.readouterr()
    assert "skipping behavioral check" in captured.out
    assert "GitNexus map stale" in captured.out


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, expected_substring",
    [
        ("fresh", "GitNexus map is FRESH"),
        ("stale", "SKIP behavioral call-graph checks"),
        ("missing", "No GitNexus map present"),
    ],
)
def test_build_doc_prompt_branches_on_gitnexus_status(status, expected_substring):
    prompt = build_doc_prompt(
        repo="stranske/Workflows",
        doc_path="README.md",
        doc_focus="model versions",
        gitnexus_status=status,
    )
    assert expected_substring in prompt
    assert "stranske/Workflows" in prompt
    assert "README.md" in prompt
    assert "model versions" in prompt


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------


def test_load_docs_config_round_trip(tmp_path: Path):
    cfg = tmp_path / "source_of_truth_docs.yml"
    cfg.write_text(
        """
repos:
  stranske/Foo:
    local_path: Foo
    docs:
      - path: README.md
        focus: f1
      - path: docs/x.md
        focus: f2
""",
        encoding="utf-8",
    )
    parsed = load_docs_config(cfg)
    assert "stranske/Foo" in parsed
    assert len(parsed["stranske/Foo"]["docs"]) == 2


def test_load_active_repos_filters_inactive(tmp_path: Path):
    reg = tmp_path / "registry.json"
    reg.write_text(
        json.dumps(
            {
                "repos": [
                    {"repo": "stranske/A", "status": "active"},
                    {"repo": "stranske/B", "status": "paused"},
                    {"repo": "stranske/C", "status": "active"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert load_active_repos(reg) == {"stranske/A", "stranske/C"}


def test_resolve_workspace_root_honors_registry_contract(tmp_path: Path):
    workspace = tmp_path / "workspace"
    steward = workspace / "Workflows-steward"
    config = steward / "config"
    config.mkdir(parents=True)
    registry = config / "repo_review_registry.json"
    registry.write_text(json.dumps({"workspace_root": "..", "repos": []}), encoding="utf-8")
    assert resolve_workspace_root(registry) == workspace.resolve()


def test_resolve_repo_root_prefers_workspace_local_path(tmp_path: Path):
    workspace = tmp_path / "workspace"
    repo_dir = workspace / "Workflows-steward"
    repo_dir.mkdir(parents=True)
    resolved = resolve_repo_root(
        workspace_root=workspace,
        local_path="Workflows-steward",
        repo="stranske/Workflows",
        cwd=tmp_path / "Workflows",
    )
    assert resolved == repo_dir.resolve()


def test_resolve_repo_root_falls_back_to_matching_cwd_repo_slug(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    cwd_repo = tmp_path / "Workflows"
    cwd_repo.mkdir(parents=True)
    resolved = resolve_repo_root(
        workspace_root=workspace,
        local_path="Workflows-steward",
        repo="stranske/Workflows",
        cwd=cwd_repo,
    )
    assert resolved == cwd_repo.resolve()


def test_parse_args_defaults_docs_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "sys.argv",
        ["repo_review_docs_drift_scan.py", "--registry", "config/r.json", "--out", "/tmp/o.json"],
    )
    args = drift_scan.parse_args()
    assert args.docs_config == Path("config/source_of_truth_docs.yml")


# ---------------------------------------------------------------------------
# Aggregate: one bundled remediation block per repo, NOT per doc
# ---------------------------------------------------------------------------


def _doc_result(repo: str, doc: str, classifications: list[str]):
    from scripts.repo_review_docs_drift_scan import DocResult

    instances = [
        DriftInstance(
            doc_path=doc,
            claim=f"claim-{c}",
            authoritative_source=f"src-{c}",
            classification=c,
        )
        for c in classifications
    ]
    return DocResult(repo=repo, doc_path=doc, instances=instances, gitnexus_status="fresh")


def test_aggregate_groups_by_repo_and_separates_drift_from_accurate():
    results = [
        _doc_result("stranske/X", "README.md", ["stale", "accurate-no-drift"]),
        _doc_result("stranske/X", "docs/AGENTS.md", ["contradictory"]),
        _doc_result("stranske/Y", "README.md", ["accurate-no-drift"]),
    ]
    summary = aggregate(results)
    by_repo = {b["repo"]: b for b in summary["by_repo"]}
    assert sorted(by_repo) == ["stranske/X", "stranske/Y"]
    assert len(by_repo["stranske/X"]["drift_instances"]) == 2
    assert len(by_repo["stranske/X"]["accurate_instances"]) == 1
    assert by_repo["stranske/Y"]["drift_instances"] == []
    assert summary["total_drift_instances"] == 2
    assert summary["total_accurate_instances"] == 2


def test_aggregate_propagates_errors_without_drift_double_count():
    from scripts.repo_review_docs_drift_scan import DocResult

    results = [
        DocResult(repo="stranske/X", doc_path="README.md", error="claude rc=1"),
        _doc_result("stranske/X", "docs/AGENTS.md", ["stale"]),
    ]
    summary = aggregate(results)
    bucket = summary["by_repo"][0]
    assert bucket["repo"] == "stranske/X"
    assert len(bucket["errors"]) == 1
    assert len(bucket["drift_instances"]) == 1
    assert summary["total_errors"] == 1


# ---------------------------------------------------------------------------
# End-to-end scan() with mocked invoker (no live claude calls)
# ---------------------------------------------------------------------------


def _make_fixture_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal workspace with a Workflows-steward checkout containing
    the three seeded-drift docs plus a clean baseline doc. Returns
    (workspace_root, registry_path)."""
    workspace = tmp_path / "workspace"
    steward = workspace / "Workflows-steward"
    docs_dir = steward / "docs"
    ci_dir = steward / "docs" / "ci"
    ops_dir = steward / "docs" / "ops"
    for d in (docs_dir, ci_dir, ops_dir):
        d.mkdir(parents=True, exist_ok=True)
    (steward / "README.md").write_text("dummy README\n", encoding="utf-8")
    (ci_dir / "WORKFLOWS.md").write_text("dummy WORKFLOWS\n", encoding="utf-8")
    (ops_dir / "REPO_REVIEW_PROCESS.md").write_text("dummy process\n", encoding="utf-8")
    (docs_dir / "AGENTS_POLICY.md").write_text("dummy policy\n", encoding="utf-8")
    (docs_dir / "LABELS.md").write_text("dummy labels\n", encoding="utf-8")
    (docs_dir / "WORKFLOW_GUIDE.md").write_text("dummy workflow guide\n", encoding="utf-8")
    (docs_dir / "MODEL_MANAGEMENT.md").write_text("dummy model management\n", encoding="utf-8")
    keepalive_dir = docs_dir / "keepalive"
    keepalive_dir.mkdir(parents=True, exist_ok=True)
    (keepalive_dir / "Agents.md").write_text("dummy keepalive agents\n", encoding="utf-8")
    registry = steward / "config" / "repo_review_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"repos": [{"repo": "stranske/Workflows", "status": "active"}]}),
        encoding="utf-8",
    )
    return workspace, registry


def _make_fixture_docs_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "source_of_truth_docs.yml"
    cfg.write_text(
        """
repos:
  stranske/Workflows:
    local_path: Workflows-steward
    docs:
      - path: README.md
        focus: model versions
      - path: docs/ci/WORKFLOWS.md
        focus: autofix contract
      - path: docs/ops/REPO_REVIEW_PROCESS.md
        focus: Phase-4 entry point
      - path: docs/AGENTS_POLICY.md
        focus: protected workflows
      - path: docs/LABELS.md
        focus: label contract
      - path: docs/WORKFLOW_GUIDE.md
        focus: workflow inventory links
      - path: docs/MODEL_MANAGEMENT.md
        focus: model registry references
      - path: docs/keepalive/Agents.md
        focus: keepalive role contracts
""",
        encoding="utf-8",
    )
    return cfg


def test_scan_end_to_end_with_seeded_fixtures(tmp_path: Path):
    workspace, registry = _make_fixture_workspace(tmp_path)
    cfg_path = _make_fixture_docs_config(tmp_path)
    docs_config = load_docs_config(cfg_path)
    active = load_active_repos(registry)

    log_dir = tmp_path / "logs"

    def fake_invoker(*, prompt: str, cwd: Path, timeout: int, log_file: Path):
        # Pick the doc from the prompt's DOC: line.
        for line in prompt.splitlines():
            if line.startswith("DOC:"):
                doc_path = line.split(":", 1)[1].strip()
                break
        else:
            doc_path = ""
        return True, SEEDED_FIXTURE_RESPONSES.get(doc_path, '{"instances": []}')

    summary = scan(
        docs_config=docs_config,
        active_repos=active,
        workspace_root=workspace,
        repo_subset=None,
        log_dir=log_dir,
        timeout=10,
        invoker=fake_invoker,
    )

    # Acceptance criteria: at least the 3 known drifts plus clean baselines.
    assert summary["total_docs_scanned"] == 8
    assert summary["total_drift_instances"] == 3, summary
    assert summary["total_accurate_instances"] >= 5, summary
    bucket = summary["by_repo"][0]
    drift_docs = sorted({i["doc_path"] for i in bucket["drift_instances"]})
    assert drift_docs == [
        "README.md",
        "docs/ci/WORKFLOWS.md",
        "docs/ops/REPO_REVIEW_PROCESS.md",
    ]


def test_scan_skips_non_active_repos(tmp_path: Path):
    workspace, registry = _make_fixture_workspace(tmp_path)
    cfg_path = tmp_path / "cfg.yml"
    cfg_path.write_text(
        """
repos:
  stranske/Workflows:
    local_path: Workflows-steward
    docs:
      - path: README.md
        focus: x
  stranske/Inactive:
    local_path: NotPresent
    docs:
      - path: README.md
        focus: y
""",
        encoding="utf-8",
    )
    summary = scan(
        docs_config=load_docs_config(cfg_path),
        active_repos=load_active_repos(registry),
        workspace_root=workspace,
        repo_subset=None,
        log_dir=tmp_path / "logs",
        timeout=10,
        invoker=lambda **kw: (True, '{"instances": []}'),
    )
    assert len(summary["by_repo"]) == 1
    assert summary["by_repo"][0]["repo"] == "stranske/Workflows"


def test_scan_records_malformed_doc_entry_without_aborting(tmp_path: Path):
    workspace, registry = _make_fixture_workspace(tmp_path)
    cfg_path = tmp_path / "cfg.yml"
    cfg_path.write_text(
        """
repos:
  stranske/Workflows:
    local_path: Workflows-steward
    docs:
      - README.md
      - path: README.md
        focus: x
""",
        encoding="utf-8",
    )
    summary = scan(
        docs_config=load_docs_config(cfg_path),
        active_repos=load_active_repos(registry),
        workspace_root=workspace,
        repo_subset=None,
        log_dir=tmp_path / "logs",
        timeout=10,
        invoker=lambda **kw: (True, '{"instances": []}'),
    )
    bucket = summary["by_repo"][0]
    assert summary["total_docs_scanned"] == 2
    assert summary["total_errors"] == 1
    assert bucket["errors"][0]["doc_path"] == "<config.docs[0]>"


def test_scan_doc_records_missing_file(tmp_path: Path):
    (tmp_path / "Workflows-steward").mkdir()
    res = scan_doc(
        repo="stranske/Workflows",
        doc_path="docs/never-existed.md",
        doc_focus="x",
        repo_root=tmp_path / "Workflows-steward",
        log_dir=tmp_path / "logs",
        timeout=10,
        invoker=lambda **kw: (True, '{"instances": []}'),
    )
    assert res.error is not None
    assert "not found" in res.error


def test_scan_doc_propagates_invoker_failure(tmp_path: Path):
    steward = tmp_path / "Workflows-steward"
    steward.mkdir()
    (steward / "README.md").write_text("dummy\n", encoding="utf-8")
    res = scan_doc(
        repo="stranske/Workflows",
        doc_path="README.md",
        doc_focus="x",
        repo_root=steward,
        log_dir=tmp_path / "logs",
        timeout=10,
        invoker=lambda **kw: (False, "claude rc=1: boom"),
    )
    assert res.error == "claude rc=1: boom"
    assert res.instances == []


# ---------------------------------------------------------------------------
# Notify renderer (one snippet per repo, NOT per doc -- acceptance criterion)
# ---------------------------------------------------------------------------


def test_notify_renders_one_snippet_per_repo_not_per_doc(tmp_path: Path):
    from scripts.repo_review_notify import format_docs_drift_section

    drift = {
        "by_repo": [
            {
                "repo": "stranske/X",
                "drift_instances": [
                    {
                        "doc_path": "README.md",
                        "claim": "c1",
                        "authoritative_source": "s1",
                        "classification": "stale",
                    },
                    {
                        "doc_path": "docs/ops/REPO_REVIEW_PROCESS.md",
                        "claim": "c2",
                        "authoritative_source": "s2",
                        "classification": "stale",
                    },
                    {
                        "doc_path": "docs/ci/WORKFLOWS.md",
                        "claim": "c3",
                        "authoritative_source": "s3",
                        "classification": "contradictory",
                    },
                ],
                "accurate_instances": [],
                "errors": [],
            }
        ]
    }
    rendered = format_docs_drift_section(drift)
    # Acceptance criterion: ONE gh issue create command per affected repo,
    # NOT one per doc. Despite 3 drift instances spanning 3 docs, the
    # rendered section must contain exactly one `gh issue create` invocation.
    assert rendered.count("gh issue create --repo stranske/X") == 1
    assert "README.md" in rendered
    assert "docs/ops/REPO_REVIEW_PROCESS.md" in rendered
    assert "docs/ci/WORKFLOWS.md" in rendered


def test_notify_emits_empty_string_when_no_drift_no_errors():
    from scripts.repo_review_notify import format_docs_drift_section

    drift = {
        "by_repo": [
            {
                "repo": "stranske/X",
                "drift_instances": [],
                "accurate_instances": [
                    {
                        "doc_path": "README.md",
                        "claim": "c",
                        "authoritative_source": "s",
                        "classification": "accurate-no-drift",
                    }
                ],
                "errors": [],
            }
        ]
    }
    assert format_docs_drift_section(drift) == ""


def test_notify_headline_reflects_docs_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.repo_review_notify import write_desktop_reminder

    monkeypatch.setenv("HOME", str(tmp_path))
    path = write_desktop_reminder(
        queue_summary={
            "total": 0,
            "by_repo": {},
            "skipped_count": 0,
            "issue_titles": [],
        },
        backlog={"auto_labeled": [], "needs_human": []},
        docs_drift={
            "total_drift_instances": 1,
            "total_errors": 0,
            "by_repo": [
                {
                    "repo": "stranske/X",
                    "drift_instances": [
                        {
                            "doc_path": "README.md",
                            "claim": "c",
                            "authoritative_source": "s",
                            "classification": "stale",
                        }
                    ],
                    "accurate_instances": [],
                    "errors": [],
                }
            ],
        },
        packet_path=tmp_path / "packet.md",
        queue_path=tmp_path / "queue.json",
        output_dir=tmp_path / "out",
        workflows_steward_root=tmp_path / "Workflows-steward",
    )
    rendered = path.read_text(encoding="utf-8")
    assert "doc-drift item" in rendered
    assert "Clean week" not in rendered


def test_notify_headline_uses_by_repo_fallback_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.repo_review_notify import write_desktop_reminder

    monkeypatch.setenv("HOME", str(tmp_path))
    path = write_desktop_reminder(
        queue_summary={
            "total": 0,
            "by_repo": {},
            "skipped_count": 0,
            "issue_titles": [],
        },
        backlog={"auto_labeled": [], "needs_human": []},
        docs_drift={
            # Intentionally omit total_drift_instances/total_errors to ensure
            # notifier derives counts from by_repo buckets.
            "by_repo": [
                {
                    "repo": "stranske/X",
                    "drift_instances": [
                        {
                            "doc_path": "README.md",
                            "claim": "c",
                            "authoritative_source": "s",
                            "classification": "stale",
                        }
                    ],
                    "accurate_instances": [],
                    "errors": [],
                }
            ],
        },
        packet_path=tmp_path / "packet.md",
        queue_path=tmp_path / "queue.json",
        output_dir=tmp_path / "out",
        workflows_steward_root=tmp_path / "Workflows-steward",
    )
    rendered = path.read_text(encoding="utf-8")
    assert "Doc drift detected" in rendered
    assert "Clean week" not in rendered


def test_notify_falls_back_when_desktop_unwritable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts import repo_review_notify

    monkeypatch.setenv("HOME", str(tmp_path))

    original_mkdir = repo_review_notify.Path.mkdir

    def _mkdir_with_desktop_failure(self: Path, *args: object, **kwargs: object) -> None:
        if str(self).endswith("/Desktop"):
            raise PermissionError("desktop blocked")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(repo_review_notify.Path, "mkdir", _mkdir_with_desktop_failure)

    out_dir = tmp_path / "out"
    path = repo_review_notify.write_desktop_reminder(
        queue_summary={"total": 0, "by_repo": {}, "skipped_count": 0, "issue_titles": []},
        backlog={"auto_labeled": [], "needs_human": []},
        docs_drift={},
        packet_path=tmp_path / "packet.md",
        queue_path=tmp_path / "queue.json",
        output_dir=out_dir,
        workflows_steward_root=tmp_path / "Workflows-steward",
    )

    assert path == out_dir / repo_review_notify.DESKTOP_FILENAME
    assert path.exists()
