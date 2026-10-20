import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
from tools import post_ci_summary


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_runs(states: dict[str, str | None] | None = None) -> list[dict[str, object]]:
    job_states = states or {
        "Core Tests (3.12)": "success",
        "Core Tests (3.13)": "success",
        "Docker Smoke": "success",
        "Gate": "success",
    }
    return [
        {
            "key": "ci",
            "displayName": "CI",
            "present": True,
            "status": "success",
            "id": 101,
            "run_attempt": 2,
            "html_url": "https://example/run/101",
            "jobs": [
                {"name": name, "conclusion": state, "html_url": "https://example/job"}
                for name, state in job_states.items()
            ],
        }
    ]


def test_load_required_groups_derives_from_runs() -> None:
    runs = _sample_runs()
    groups = post_ci_summary._load_required_groups(None, runs)

    labels = [group["label"] for group in groups]
    assert labels == ["Core Tests (3.12)", "Core Tests (3.13)", "Docker Smoke", "Gate"]
    assert groups[0]["patterns"] == [r"^Core\ Tests\ \(3\.12\)$"]
    assert groups[3]["patterns"] == [r"^Gate$"]


def test_collect_category_states_marks_docs_only_fast_pass() -> None:
    runs = _sample_runs(
        {
            "Core Tests (3.12)": "skipped",
            "Core Tests (3.13)": "skipped",
            "Docker Smoke": "skipped",
        }
    )
    category_states = post_ci_summary._collect_category_states(runs)

    assert post_ci_summary._is_docs_only_fast_pass(category_states) is True


def test_build_summary_comment_includes_required_sections(tmp_path: Path, monkeypatch) -> None:
    contexts_path = tmp_path / "contexts.json"
    _write_json(contexts_path, {"required_contexts": ["ci/required", "lint"]})
    monkeypatch.setenv("REQUIRED_CONTEXTS_FILE", str(contexts_path))

    runs = [
        {
            "key": "ci",
            "displayName": "CI",
            "present": True,
            "status": "failure",
            "id": 123,
            "run_attempt": 2,
            "html_url": "https://example/run/123",
            "jobs": [
                {"name": "Unit Tests", "conclusion": "failure", "html_url": "https://logs/unit"},
                {"name": "Lint", "conclusion": "success", "html_url": "https://logs/lint"},
            ],
        }
    ]

    coverage_stats = {
        "avg_latest": 71.5,
        "avg_delta": -1.2,
        "worst_latest": 60.0,
        "worst_delta": -5.5,
        "history_len": 12,
        "coverage_table_markdown": "| Job | Coverage |\n| --- | --- |\n| CI | 71.5% |",
    }
    coverage_delta = {
        "current": 71.5,
        "baseline": 73.0,
        "delta": -1.5,
        "drop": 2.0,
        "threshold": 1.0,
        "status": "below",
    }

    required_groups_env = json.dumps([{"label": "required", "patterns": ["Unit Tests", "Lint"]}])

    summary = post_ci_summary.build_summary_comment(
        runs=runs,
        head_sha="abc123",
        coverage_stats=coverage_stats,
        coverage_section="Extra coverage notes.",
        coverage_delta=coverage_delta,
        required_groups_env=required_groups_env,
    )

    assert "## Automated Status Summary" in summary
    assert "**Head SHA:** abc123" in summary
    assert "**Latest Runs:**" in summary
    assert "**Required contexts:** ci/required, lint" in summary
    assert "**Required:**" in summary
    assert "| **CI / Unit Tests** |" in summary
    assert "Coverage Overview" in summary
    assert "Coverage (jobs)" in summary
    assert "Coverage delta:" in summary
    assert "Extra coverage notes." in summary


def test_dedupe_runs_prefers_present_and_priority() -> None:
    runs = [
        {"key": "gate", "present": False, "status": "failure"},
        {"key": "gate", "present": True, "status": "success"},
        {"key": "gate", "present": True, "status": "failure"},
    ]

    deduped = post_ci_summary._dedupe_runs(runs)

    assert len(deduped) == 1
    assert deduped[0].get("status") == "failure"


def test_main_writes_github_output(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "output.txt"
    contexts_path = tmp_path / "contexts.json"
    _write_json(contexts_path, [])

    monkeypatch.setenv("RUNS_JSON", "[]")
    monkeypatch.setenv("REQUIRED_CONTEXTS_FILE", str(contexts_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    post_ci_summary.main()

    output_text = output_path.read_text(encoding="utf-8")
    assert "body<<EOF" in output_text
    assert "Automated Status Summary" in output_text


def test_main_runs_when_invoked_by_file_path(tmp_path: Path) -> None:
    output_path = tmp_path / "output.txt"
    contexts_path = tmp_path / "contexts.json"
    _write_json(contexts_path, [])

    result = subprocess.run(
        [sys.executable, "tools/post_ci_summary.py"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "RUNS_JSON": "[]",
            "REQUIRED_CONTEXTS_FILE": str(contexts_path),
            "GITHUB_OUTPUT": str(output_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Automated Status Summary" in output_path.read_text(encoding="utf-8")


def test_main_runs_by_file_path_when_tools_package_is_shadowed(tmp_path: Path) -> None:
    output_path = tmp_path / "output.txt"
    contexts_path = tmp_path / "contexts.json"
    shadow_root = tmp_path / "shadow"
    shadow_tools = shadow_root / "tools"
    shadow_tools.mkdir(parents=True)
    (shadow_tools / "__init__.py").write_text("# Shadow package without ci_failure_triage\n")
    _write_json(contexts_path, [])

    result = subprocess.run(
        [sys.executable, "tools/post_ci_summary.py"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PYTHONPATH": str(shadow_root),
            "RUNS_JSON": "[]",
            "REQUIRED_CONTEXTS_FILE": str(contexts_path),
            "GITHUB_OUTPUT": str(output_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Automated Status Summary" in output_path.read_text(encoding="utf-8")


def _exec_post_ci_summary_with_tools_stub() -> types.ModuleType:
    """Load post_ci_summary.py while ``tools`` is an incomplete package stub.

    Forces the ModuleNotFoundError import-fallback (lines 22–30). The subprocess
    shadowed-tools test exercises the same path behaviorally, but in-process
    reload is required for pytest-cov to attribute those lines.
    """
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "tools" / "post_ci_summary.py"
    probe_name = "tools.post_ci_summary_import_fallback_probe"

    saved = {
        name: module
        for name, module in sys.modules.items()
        if name == "tools" or name.startswith("tools.")
    }
    try:
        for name in list(sys.modules):
            if name == "tools" or name.startswith("tools."):
                del sys.modules[name]

        stub_tools = types.ModuleType("tools")
        stub_tools.__path__ = []
        sys.modules["tools"] = stub_tools

        spec = importlib.util.spec_from_file_location(probe_name, module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[probe_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(probe_name, None)
        for name in list(sys.modules):
            if name == "tools" or name.startswith("tools."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_import_fallback_recovers_when_tools_package_is_incomplete() -> None:
    module = _exec_post_ci_summary_with_tools_stub()

    assert hasattr(module, "JobRecord")
    assert callable(module.triage_ci_failure)
    # Canonical import used by the rest of this module must still resolve.
    assert post_ci_summary.triage_ci_failure is not None


def test_import_fallback_reraises_unrelated_module_not_found(tmp_path: Path) -> None:
    """Unrelated ModuleNotFoundError names must propagate (line 25 raise)."""
    shadow_root = tmp_path / "shadow"
    shadow_tools = shadow_root / "tools"
    shadow_tools.mkdir(parents=True)
    (shadow_tools / "__init__.py").write_text("# shadow tools\n", encoding="utf-8")
    (shadow_tools / "ci_failure_triage.py").write_text(
        "import totally_missing_unrelated_dep  # noqa: F401\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "tools" / "post_ci_summary.py"
    probe_name = "tools.post_ci_summary_import_fallback_reraise_probe"

    saved = {
        name: module
        for name, module in sys.modules.items()
        if name == "tools" or name.startswith("tools.")
    }
    saved_path = list(sys.path)
    try:
        for name in list(sys.modules):
            if name == "tools" or name.startswith("tools."):
                del sys.modules[name]
        sys.path.insert(0, str(shadow_root))

        spec = importlib.util.spec_from_file_location(probe_name, module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[probe_name] = module
        with pytest.raises(ModuleNotFoundError, match="totally_missing_unrelated_dep") as excinfo:
            spec.loader.exec_module(module)
        assert excinfo.value.name == "totally_missing_unrelated_dep"
    finally:
        sys.path[:] = saved_path
        sys.modules.pop(probe_name, None)
        for name in list(sys.modules):
            if name == "tools" or name.startswith("tools."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_collect_triage_block_from_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    artifacts_root = tmp_path / "gate_artifacts"
    runtime_dir = artifacts_root / "downloads" / "coverage" / "runtimes" / "3.12"
    runtime_dir.mkdir(parents=True)

    summary_payload = {
        "checks": {
            "type_check": {"outcome": "failure"},
            "tests": {"outcome": "failure"},
            "coverage_minimum": {"outcome": "failure"},
        }
    }
    (runtime_dir / "summary.json").write_text(
        json.dumps(summary_payload),
        encoding="utf-8",
    )

    junit_payload = """<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="1" failures="1">
  <testcase classname="tests.test_demo" name="test_import" file="src/app.py" line="12">
    <failure message="ImportError: No module named foo">Traceback (most recent call last):
ImportError: No module named foo</failure>
  </testcase>
</testsuite>
"""
    (runtime_dir / "pytest-junit.xml").write_text(junit_payload, encoding="utf-8")

    head_sha = "a" * 40
    triage_block = post_ci_summary._collect_triage_block(artifacts_root, head_sha=head_sha)
    triage_text = "\n".join(triage_block)

    assert "Failure triage" in triage_text
    assert "error_type: mypy" in triage_text
    assert "error_type: pytest" in triage_text
    assert "error_type: coverage" in triage_text
    assert "error_type: import_error" in triage_text
    for anchor in ("type-errors", "test-failures", "coverage-failures", "import-errors"):
        path = f"docs/CI_FAILURE_PLAYBOOK.md#{anchor}"
        assert (
            f"playbook_url: [{path}](https://github.com/stranske/Workflows/blob/{head_sha}/{path})"
            in triage_text
        )


def test_playbook_link_preserves_absolute_url_and_rejects_unsafe_relative_path(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    for url in ("https://example.com/guide#section", "http://example.com/guide"):
        assert post_ci_summary._playbook_link(url, "a" * 40) == f"[playbook]({url})"
    for url in (
        "docs/../private.md",
        "javascript:alert(1)",
        "//example.com/guide",
        "https://example.com/guide)evil",
        "https://user:secret@example.com/guide",
        "https://example.com:abc/guide",
        "https://example.com:99999/guide",
    ):
        assert post_ci_summary._playbook_link(url, "a" * 40) == "unavailable playbook URL"


def test_playbook_link_rejects_malformed_server_ports(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    for server in ("https://github.example:abc", "https://github.example:99999"):
        monkeypatch.setenv("GITHUB_SERVER_URL", server)
        assert (
            post_ci_summary._playbook_link("docs/CI_FAILURE_PLAYBOOK.md", "a" * 40)
            == "unavailable playbook URL"
        )


def test_playbook_link_falls_back_to_main_without_valid_head(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    url = "docs/CI_FAILURE_PLAYBOOK.md#type-errors"
    assert post_ci_summary._playbook_link(url, "not-a-sha") == (
        f"[{url}](https://github.com/stranske/Workflows/blob/main/{url})"
    )


def test_display_helpers_prioritize_and_render_all_state_families() -> None:
    assert post_ci_summary._badge(None) == "⏳"
    assert post_ci_summary._badge("cancelled") == "❌"
    assert post_ci_summary._badge("skipped") == "⏭️"
    assert post_ci_summary._display_state("TIMED_OUT") == "timed out"
    assert post_ci_summary._combine_states(["success", "queued", "failure"]) == "failure"
    assert post_ci_summary._combine_states([]) == "missing"
    assert post_ci_summary._priority("unknown") > post_ci_summary._priority("success")
    assert post_ci_summary._badge("waiting") == "⏳"
    assert post_ci_summary._display_state("  ") == "pending"
    assert post_ci_summary._priority("queued") == 1
    assert post_ci_summary._combine_states(["requested", "success"]) == "requested"
    assert post_ci_summary._combine_states(["skipped"]) == "skipped"
    assert post_ci_summary._combine_states(["other"]) == "other"


def test_required_group_loading_handles_invalid_and_valid_configurations() -> None:
    runs = _sample_runs()
    derived = post_ci_summary._load_required_groups("not-json", runs)
    assert [item["label"] for item in derived] == [
        "Core Tests (3.12)",
        "Core Tests (3.13)",
        "Docker Smoke",
        "Gate",
    ]
    configured = post_ci_summary._load_required_groups(
        json.dumps([{"name": "unit", "patterns": ["Unit"], "ignored": True}]), runs
    )
    assert configured == [{"label": "unit", "patterns": ["Unit"]}]


def test_collect_junit_failures_and_triage_limits(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    junit = root / "downloads" / "pytest-junit.xml"
    junit.parent.mkdir(parents=True)
    junit.write_text(
        '<testcase file="tests/x.py" line="9"><failure message="bad &amp; worse">trace <b>detail</b></failure></testcase>',
        encoding="utf-8",
    )
    assert post_ci_summary._collect_junit_failures(root, 2) == [
        'File "tests/x.py", line 9',
        "bad & worse",
    ]
    assert post_ci_summary._collect_junit_failures(tmp_path / "missing", 2) == []


def test_summary_helpers_render_empty_and_docs_only_paths(tmp_path: Path, monkeypatch) -> None:
    contexts = tmp_path / "contexts.json"
    _write_json(contexts, {"contexts": [" gate ", 3]})
    monkeypatch.setenv("REQUIRED_CONTEXTS_FILE", str(contexts))
    runs = _sample_runs(
        {
            "Core Tests (3.12)": "skipped",
            "Core Tests (3.13)": "skipped",
            "Docker Smoke": "skipped",
            "Gate": "success",
        }
    )
    summary = post_ci_summary.build_summary_comment(
        runs=runs,
        head_sha=None,
        coverage_stats=None,
        coverage_section=None,
        coverage_delta={"status": "no-baseline"},
        required_groups_env=None,
    )
    assert "Docs-only change detected" in summary
    assert "base — (no baseline)" in summary
    assert "**Required contexts:** gate" in summary


def test_format_helpers_and_main_stdout_handle_non_json_environment(monkeypatch, capsys) -> None:
    assert post_ci_summary._format_percent("not-a-number") is None
    assert post_ci_summary._format_delta_pp(-2, signed=False) == "2.00 pp"
    assert post_ci_summary._format_coverage_lines({"history_len": "3"}) == []
    assert post_ci_summary._format_coverage_delta_lines({}) == []
    monkeypatch.setenv("RUNS_JSON", "not-json")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("GATE_ARTIFACTS_ROOT", "/definitely/missing")

    post_ci_summary.main()

    assert "Automated Status Summary" in capsys.readouterr().out


def test_loading_helpers_tolerate_missing_malformed_and_alternate_shapes(tmp_path: Path) -> None:
    assert post_ci_summary._load_required_contexts(tmp_path / "missing.json") == []
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert post_ci_summary._load_required_contexts(malformed) == []
    assert post_ci_summary._load_json_from_env("[]") is None
    assert post_ci_summary._load_json_from_env("{") is None
    assert post_ci_summary._load_json_from_env('{"current": 80}') == {"current": 80}


def test_summary_helpers_reject_invalid_configuration_and_render_unusual_run_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = [
        {"present": True, "display_name": "Odd", "jobs": [None, {"name": "", "status": "queued"}]},
        {"key": 4, "present": True, "jobs": "not-a-job-list"},
        {"key": "plain", "present": True, "jobs": [{"name": "Build", "status": "queued"}]},
    ]
    assert post_ci_summary._build_job_rows(runs) == [
        post_ci_summary.JobRecord("plain / Build", "queued", None, False)
    ]
    assert post_ci_summary._collect_required_segments(
        runs,
        [
            {"label": "bad", "patterns": ["["]},
            {"label": "build", "patterns": ["Build", 4]},  # type: ignore[list-item]
        ],
    ) == ["Build: ⏳ queued"]
    fallback = post_ci_summary._load_required_groups("[]", [])
    assert [group["label"] for group in fallback] == [
        "core tests (3.12)",
        "core tests (3.13)",
        "docker smoke",
        "gate",
    ]
    assert (
        post_ci_summary._load_required_groups('[null, {"label": "", "patterns": []}]', [])
        == fallback
    )

    contexts = tmp_path / "contexts.json"
    _write_json(contexts, [" one ", 2, ""])
    assert post_ci_summary._load_required_contexts(contexts) == ["one"]
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    assert post_ci_summary._playbook_link("docs/Guide.md#one", "a" * 40) == (
        "[docs/Guide.md#one](https://github.com/stranske/Workflows/blob/"
        + "a" * 40
        + "/docs/Guide.md#one)"
    )


def test_artifact_failure_collection_handles_invalid_files_and_all_failure_outcomes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    downloads = root / "downloads"
    downloads.mkdir(parents=True)
    (downloads / "summary.json").write_text("{", encoding="utf-8")
    records = [
        {
            "checks": {
                "type_check": {"outcome": "cancelled"},
                "tests": {"outcome": "error"},
                "coverage_minimum": {"outcome": "action_required"},
            }
        },
        {"checks": "not-an-object"},
    ]
    assert post_ci_summary._load_gate_summary_records(root) == []
    assert post_ci_summary._collect_check_failure_lines(records) == [
        "mypy type check failed",
        "= FAILURES =",
        "coverage failure: coverage minimum check failed",
    ]


def test_xml_helpers_cache_patterns_decode_attributes_and_strip_tags() -> None:
    assert list(
        post_ci_summary._iter_junit_testcase_blocks('<testcase name="x">body</testcase>')
    ) == [{"attrs": ' name="x"', "body": "body"}]
    assert list(post_ci_summary._iter_xml_tag_blocks("<failure>oops</failure>", "failure")) == [
        {"attrs": "", "body": "oops"}
    ]
    assert post_ci_summary._parse_xml_attributes('message="bad &amp; worse" kind=missing') == {
        "message": "bad & worse"
    }
    assert post_ci_summary._strip_xml_tags("a <b>bold</b> &amp; c") == "a bold & c"


def test_run_rendering_and_deduplication_cover_missing_and_jobless_records() -> None:
    runs = [
        "not-a-run",
        {"key": "absent", "present": False, "status": "queued"},
        {"key": "no-jobs", "present": True, "status": "success"},
        {
            "key": "jobs",
            "present": True,
            "display_name": "CI",
            "status": "success",
            "jobs": [
                {"name": "", "conclusion": "success"},
                {"name": "Unit", "status": "failure", "html_url": "https://logs"},
            ],
        },
    ]
    assert len(post_ci_summary._dedupe_runs(runs)) == 3
    rows = post_ci_summary._build_job_rows(runs)
    assert rows[0].highlight is True
    assert "**CI / Unit**" in rows[0].name
    assert "no jobs reported" in "\n".join(post_ci_summary._format_jobs_table([]))
    assert "queued — absent" in post_ci_summary._format_latest_runs(runs)


def test_required_segments_skip_bad_patterns_and_render_canonical_match() -> None:
    runs = _sample_runs({"Core Tests (3.12)": "success"})
    segments = post_ci_summary._collect_required_segments(
        runs,
        [
            {"label": "bad", "patterns": ["["]},
            {"label": "core", "patterns": ["Core Tests"]},
        ],
    )
    assert segments == ["Core Tests (3.12): ✅ success"]


def test_triage_and_playbook_helpers_reject_unusable_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert (
        post_ci_summary._playbook_link("docs/CI_FAILURE_PLAYBOOK.md", None)
        == "unavailable playbook URL"
    )
    assert post_ci_summary._format_triage_block("ordinary text") == []
    assert post_ci_summary._collect_triage_block(tmp_path / "missing") == []


def test_job_group_derivation_and_category_collection_ignore_malformed_records() -> None:
    runs = [
        "bad",
        {"present": True, "jobs": "bad"},
        {
            "present": True,
            "key": "fallback",
            "jobs": [
                None,
                {"name": 3},
                {"name": "  "},
                {"name": "Core Tests (3.12)", "status": "queued"},
            ],
        },
    ]
    groups = post_ci_summary._derive_required_groups_from_runs(runs)
    assert groups[0]["label"] == "Core Tests (3.12)"
    states = post_ci_summary._collect_category_states(runs)
    assert states["core312"] == ("fallback / Core Tests (3.12)", "queued")
    assert post_ci_summary._is_docs_only_fast_pass({}) is False


@pytest.mark.parametrize("raw", ["{}", "[null]", '[{"label": "", "patterns": ["x"]}]'])
def test_required_group_configuration_falls_back_when_no_usable_groups(raw: str) -> None:
    groups = post_ci_summary._load_required_groups(raw, [])
    assert [group["label"] for group in groups] == [
        "core tests (3.12)",
        "core tests (3.13)",
        "docker smoke",
        "gate",
    ]


def test_required_contexts_accepts_list_and_filters_blank_values(tmp_path: Path) -> None:
    config = tmp_path / "contexts.json"
    _write_json(config, ["alpha", " ", 5])
    assert post_ci_summary._load_required_contexts(config) == ["alpha"]


def test_formatting_helpers_render_complete_coverage_and_run_variants() -> None:
    assert post_ci_summary._format_coverage_lines(
        {"avg_latest": 10, "avg_delta": 0, "worst_latest": 5, "worst_delta": -1, "history_len": 2}
    ) == [
        "- Coverage (jobs): 10.00% | Δ 0.00 pp",
        "- Coverage (worst job): 5.00% | Δ -1.00 pp",
        "- Coverage history entries: 2",
    ]
    assert post_ci_summary._format_coverage_delta_lines(
        {"current": 10, "baseline": 9, "delta": 1, "drop": 0, "threshold": 1, "status": "ok"}
    ) == [
        "- Coverage delta: head 10.00% | base 9.00% | Δ +1.00 pp | drop 0.00 pp | threshold 1.00 pp | status ok"
    ]
    rendered = post_ci_summary._format_latest_runs(
        [
            {
                "present": True,
                "displayName": "Gate",
                "id": 4,
                "run_attempt": 2,
                "html_url": "https://run",
            }
        ]
    )
    assert "[Gate (#4 (attempt 2))](https://run)" in rendered


def test_main_ignores_non_list_runs_and_uses_output_path(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "output.txt"
    monkeypatch.setenv("RUNS_JSON", "{}")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GATE_ARTIFACTS_ROOT", str(tmp_path / "missing"))
    post_ci_summary.main()
    assert output.read_text(encoding="utf-8").startswith("body<<EOF\n## Automated Status Summary")


def test_post_ci_helpers_preserve_safe_empty_and_fallback_rendering(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    downloads = artifacts / "downloads"
    downloads.mkdir(parents=True)
    (downloads / "summary.json").write_text('{"checks": {}}', encoding="utf-8")
    malformed = downloads / "malformed"
    malformed.mkdir()
    (malformed / "summary.json").write_text("{", encoding="utf-8")
    junit = downloads / "pytest-junit.xml"
    junit.write_text(
        '<testcase name="no-location"><error>plain failure</error></testcase>', encoding="utf-8"
    )

    assert post_ci_summary._load_gate_summary_records(artifacts) == [{"checks": {}}]
    assert post_ci_summary._collect_junit_failures(artifacts, 5) == ["plain failure"]
    assert post_ci_summary._collect_required_segments(
        [{"present": True, "jobs": [{"name": "Build", "status": "success"}]}],
        [{"label": "broken", "patterns": ["["]}, {"label": "missing", "patterns": ["Lint"]}],
    ) == ["missing: ⏳ pending"]
    summary = post_ci_summary.build_summary_comment(
        runs=[],
        head_sha=None,
        coverage_stats={"coverage_table_markdown": "| only | table |"},
        coverage_section="",
        coverage_delta=None,
        required_groups_env="[]",
        triage_block=["triage"],
    )
    assert "### Coverage Overview" in summary
    assert "| only | table |" in summary
    assert "triage" in summary


def test_default_required_groups_used_when_derivation_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(post_ci_summary, "_derive_required_groups_from_runs", lambda _runs: [])
    assert post_ci_summary._load_required_groups(None, []) == post_ci_summary._copy_required_groups(
        post_ci_summary.DEFAULT_REQUIRED_JOB_GROUPS
    )
    assert post_ci_summary._load_required_groups("{", []) == post_ci_summary._copy_required_groups(
        post_ci_summary.DEFAULT_REQUIRED_JOB_GROUPS
    )
    assert post_ci_summary._load_required_groups("{}", []) == post_ci_summary._copy_required_groups(
        post_ci_summary.DEFAULT_REQUIRED_JOB_GROUPS
    )
    assert post_ci_summary._load_required_groups("[]", []) == post_ci_summary._copy_required_groups(
        post_ci_summary.DEFAULT_REQUIRED_JOB_GROUPS
    )


def test_derive_required_groups_skips_duplicate_casefold_matches() -> None:
    runs = [
        {
            "jobs": [
                {"name": "Core Tests (3.12)"},
                {"name": "core tests (3.12)"},
                {"name": "Unrelated Job"},
            ]
        }
    ]
    groups = post_ci_summary._derive_required_groups_from_runs(runs)
    assert groups[0]["patterns"] == [r"^Core\ Tests\ \(3\.12\)$"]


def test_load_required_groups_skips_empty_pattern_lists() -> None:
    raw = json.dumps(
        [
            {"label": "empty", "patterns": ["", None]},
            {"label": "ok", "patterns": ["Unit"]},
            {"name": "alias", "patterns": ["Lint"]},
        ]
    )
    groups = post_ci_summary._load_required_groups(raw, [])
    assert groups == [
        {"label": "ok", "patterns": ["Unit"]},
        {"label": "alias", "patterns": ["Lint"]},
    ]


def test_append_helpers_respect_limits_and_blank_lines() -> None:
    lines: list[str] = []
    post_ci_summary._append_line(lines, "  keep  ", 1)
    post_ci_summary._append_line(lines, "ignored", 1)
    post_ci_summary._append_line(lines, "   ", 5)
    assert lines == ["keep"]
    more: list[str] = []
    post_ci_summary._append_text(more, "a\n\nb\nc", 2)
    assert more == ["a", "b"]


def test_junit_collection_skips_unreadable_files_and_honors_limit(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    unreadable = downloads / "pytest-junit.xml"
    unreadable.write_text("<testcase></testcase>", encoding="utf-8")
    unreadable.chmod(0)
    try:
        assert post_ci_summary._collect_junit_failures(tmp_path, 5) == []
    finally:
        unreadable.chmod(0o644)

    readable = downloads / "nested"
    readable.mkdir()
    (readable / "pytest-junit.xml").write_text(
        '<testcase file="a.py" line="1"><failure message="one">body</failure>'
        '<error message="two">more</error></testcase>'
        '<testcase file="b.py"><failure message="three">x</failure></testcase>',
        encoding="utf-8",
    )
    assert post_ci_summary._collect_junit_failures(tmp_path, 3) == [
        'File "a.py", line 1',
        "one",
        "body",
    ]


def test_check_failure_lines_and_gate_summary_edge_cases(tmp_path: Path) -> None:
    assert post_ci_summary._load_gate_summary_records(tmp_path) == []
    assert post_ci_summary._collect_check_failure_lines(
        [
            {"checks": "bad"},
            {
                "checks": {
                    "type_check": {"outcome": "success"},
                    "tests": "bad",
                    "coverage_minimum": {"outcome": "cancelled"},
                }
            },
        ]
    ) == ["coverage failure: coverage minimum check failed"]


def test_playbook_link_rejects_control_chars_and_unsafe_server(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    assert (
        post_ci_summary._playbook_link("https://example.com/a b", None)
        == "unavailable playbook URL"
    )
    monkeypatch.setenv("GITHUB_SERVER_URL", "ftp://github.com")
    assert (
        post_ci_summary._playbook_link("docs/CI_FAILURE_PLAYBOOK.md", "a" * 40)
        == "unavailable playbook URL"
    )
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://user:pass@github.com")
    assert (
        post_ci_summary._playbook_link("docs/CI_FAILURE_PLAYBOOK.md", "a" * 40)
        == "unavailable playbook URL"
    )


def test_format_triage_includes_files_and_playbook(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    finding = type(
        "Finding",
        (),
        {
            "error_type": "pytest",
            "root_cause": "assert failed",
            "suggested_fix": "fix test",
            "relevant_files": ["tests/a.py"],
            "playbook_url": "docs/CI_FAILURE_PLAYBOOK.md#test-failures",
        },
    )()
    report = type("Report", (), {"findings": [finding], "summary": "one finding"})()
    monkeypatch.setattr(post_ci_summary, "triage_ci_failure", lambda _text: report)
    lines = post_ci_summary._format_triage_block("= FAILURES =", head_sha="b" * 40)
    assert "relevant_files: tests/a.py" in "\n".join(lines)
    assert "playbook_url:" in "\n".join(lines)


def test_collect_triage_dedupes_and_stops_at_limit(tmp_path: Path, monkeypatch) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    _write_json(
        downloads / "summary.json",
        {"checks": {"tests": {"outcome": "failure"}, "type_check": {"outcome": "failure"}}},
    )
    (downloads / "pytest-junit.xml").write_text(
        "".join(
            f'<testcase name="t{i}"><failure message="fail-{i}">x</failure></testcase>'
            for i in range(5)
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        post_ci_summary,
        "_format_triage_block",
        lambda text, head_sha=None: [f"lines={len(text.splitlines())}"],
    )
    assert post_ci_summary._collect_triage_block(tmp_path) == ["lines=8"]


def test_collect_triage_breaks_when_dedupe_hits_hard_limit(tmp_path: Path, monkeypatch) -> None:
    """Hit the dedupe ``break`` when unique failure lines reach the hard limit."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    _write_json(downloads / "summary.json", {"checks": {}})
    unique_lines = [f"unique-failure-{index}" for index in range(250)]
    monkeypatch.setattr(
        post_ci_summary,
        "_collect_check_failure_lines",
        lambda _records: list(unique_lines),
    )
    monkeypatch.setattr(post_ci_summary, "_collect_junit_failures", lambda _root, _limit: [])
    captured: dict[str, str] = {}

    def _capture(text: str, head_sha=None) -> list[str]:
        captured["text"] = text
        return ["triaged"]

    monkeypatch.setattr(post_ci_summary, "_format_triage_block", _capture)
    assert post_ci_summary._collect_triage_block(tmp_path) == ["triaged"]
    assert len(captured["text"].splitlines()) == 200


def test_dedupe_runs_handles_non_string_keys_and_state_replacement() -> None:
    runs = [
        "skip",
        {"key": 7, "present": True, "status": "success"},
        {"key": 7, "present": True, "status": "failure"},
        {"key": None, "present": True, "status": "queued"},
        {"key": "  ", "present": True, "status": "success"},
        {"key": "gate", "present": True, "conclusion": None, "status": None},
        {"key": "gate", "present": True, "status": "queued"},
    ]
    deduped = post_ci_summary._dedupe_runs(runs)
    assert any(run.get("key") == 7 and run.get("status") == "failure" for run in deduped)
    assert any(run.get("key") == "gate" and run.get("status") == "queued" for run in deduped)
    assert sum(1 for run in deduped if run.get("key") in {None, "  "}) == 2


def test_required_segments_skip_blank_labels_and_duplicate_names() -> None:
    runs = [
        "not-a-mapping",
        {"present": False, "jobs": [{"name": "Lint", "conclusion": "failure"}]},
        {
            "present": True,
            "jobs": [
                {"name": "Lint", "conclusion": "success"},
                {"name": "lint", "conclusion": "failure"},
                {"name": "", "conclusion": "success"},
            ],
        },
        {"present": True, "jobs": "bad"},
    ]
    segments = post_ci_summary._collect_required_segments(
        runs,
        [
            {"label": "  ", "patterns": ["Lint"]},
            {"label": "lint-group", "patterns": [1, "Lint"]},
        ],
    )
    assert segments == ["Lint: ❌ failure"]


def test_build_summary_coverage_section_alone_adds_overview_header(monkeypatch) -> None:
    """Coverage section with no stats/delta/table must still open the Overview block."""
    monkeypatch.setattr(post_ci_summary, "_is_docs_only_fast_pass", lambda _states: False)
    monkeypatch.setattr(post_ci_summary, "_load_required_contexts", lambda _path=None: [])
    summary = post_ci_summary.build_summary_comment(
        runs=[],
        head_sha=None,
        coverage_stats=None,
        coverage_section="section-only notes",
        coverage_delta=None,
        required_groups_env="[]",
    )
    assert "### Coverage Overview" in summary
    assert "section-only notes" in summary
    assert "Docs-only" not in summary


def test_build_summary_docs_only_and_coverage_section_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        post_ci_summary,
        "_is_docs_only_fast_pass",
        lambda _states: True,
    )
    monkeypatch.setattr(post_ci_summary, "_load_required_contexts", lambda _path=None: [])
    summary = post_ci_summary.build_summary_comment(
        runs=_sample_runs(
            {
                "Core Tests (3.12)": "skipped",
                "Core Tests (3.13)": "skipped",
                "Docker Smoke": "skipped",
            }
        ),
        head_sha=None,
        coverage_stats=None,
        coverage_section="section only",
        coverage_delta={"status": "no-baseline", "current": 10},
        required_groups_env=None,
    )
    assert "Docs-only change detected; heavy checks skipped." in summary
    assert "Docs-only fast-pass: coverage artifacts were not refreshed for this run." in summary
    assert "base — (no baseline)" in summary
    assert "section only" in summary

    monkeypatch.setattr(post_ci_summary, "_is_docs_only_fast_pass", lambda _states: False)
    summary_note_only = post_ci_summary.build_summary_comment(
        runs=[],
        head_sha=None,
        coverage_stats=None,
        coverage_section="",
        coverage_delta=None,
        required_groups_env="[]",
    )
    assert "### Coverage Overview" not in summary_note_only
    assert "Docs-only change detected" not in summary_note_only


def test_category_states_prefer_higher_priority_and_docs_only_requires_skipped() -> None:
    runs = [
        {
            "present": True,
            "displayName": "CI",
            "jobs": [
                {"name": "Core Tests (3.12)", "conclusion": "success"},
                {"name": "Core Tests (3.12)", "conclusion": "failure"},
                {"name": "Core Tests (3.13)", "conclusion": "skipped"},
                {"name": "Docker Smoke", "conclusion": "success"},
            ],
        }
    ]
    states = post_ci_summary._collect_category_states(runs)
    assert states["core312"][1] == "failure"
    assert post_ci_summary._is_docs_only_fast_pass(states) is False
    skipped_only = {
        "core312": ("a", "skipped"),
        "core313": ("b", "skipped"),
        "docker": ("c", None),
    }
    assert post_ci_summary._is_docs_only_fast_pass(skipped_only) is False


def test_badge_unknown_state_renders_pending_hourglass() -> None:
    assert post_ci_summary._badge("mystery") == "⏳"


def test_derive_and_category_skip_non_sequence_jobs() -> None:
    runs = [{"jobs": {"name": "Gate"}}, {"present": True, "jobs": {"name": "Gate"}}]
    assert all(
        group["label"] in {"core tests (3.12)", "core tests (3.13)", "docker smoke", "gate"}
        for group in post_ci_summary._derive_required_groups_from_runs(runs)
    )
    assert post_ci_summary._collect_category_states(runs) == {}


def test_required_contexts_ignores_non_iterable_payload(tmp_path: Path) -> None:
    config = tmp_path / "contexts.json"
    _write_json(config, {"required_contexts": 5})
    assert post_ci_summary._load_required_contexts(config) == []


def test_collect_triage_returns_empty_when_no_failure_lines(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    _write_json(downloads / "summary.json", {"checks": {"tests": {"outcome": "success"}}})
    assert post_ci_summary._collect_triage_block(tmp_path) == []


def test_build_summary_coverage_section_without_other_coverage(monkeypatch) -> None:
    monkeypatch.setattr(post_ci_summary, "_is_docs_only_fast_pass", lambda _states: True)
    monkeypatch.setattr(post_ci_summary, "_load_required_contexts", lambda _path=None: ["ctx"])
    summary = post_ci_summary.build_summary_comment(
        runs=[],
        head_sha=None,
        coverage_stats=None,
        coverage_section="",
        coverage_delta=None,
        required_groups_env="[]",
    )
    assert "### Coverage Overview" in summary
    assert "Docs-only fast-pass" in summary
    assert "**Required contexts:** ctx" in summary
