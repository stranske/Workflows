from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import reusable_ci_scope


def test_full_matrix_when_no_scope_info() -> None:
    full = {"include": [{"name": "minimal"}, {"name": "full"}]}

    selected = reusable_ci_scope.select_scenarios(
        "selftest-reusable-ci",
        ["tests/test_example.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    assert selected.matrix == full
    assert selected.selected_count == 2
    assert selected.reason == "no reusable CI scope metadata was provided"


def test_reduced_matrix_when_scope_detected() -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
            {"name": "workflow", "scope_paths": [".github/workflows/**"]},
        ]
    }

    selected = reusable_ci_scope.select_scenarios(
        "selftest-reusable-ci",
        ["tests/test_reusable_ci_scope.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    assert selected.matrix == {"include": [{"name": "tests"}]}
    assert selected.selected_count == 1
    assert selected.total_count == 3


def test_globstar_scope_matches_root_python_file() -> None:
    full = {"include": [{"name": "coverage", "scope": {"paths": ["**/*.py"]}}]}

    selected = reusable_ci_scope.select_scenarios(
        "maint-coverage-guard",
        ["main.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    assert selected.matrix == {"include": [{"name": "coverage"}]}
    assert selected.selected_count == 1


def test_force_full_override_returns_full_matrix() -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
        ]
    }

    selected = reusable_ci_scope.select_scenarios(
        "selftest-reusable-ci",
        ["docs/readme.md"],
        full,
        reusable_ci_scope.SelectionOptions(force_full=True),
    )

    assert selected.matrix == {"include": [{"name": "tests"}, {"name": "docs"}]}
    assert selected.force_full is True
    assert selected.selected_count == 2


def test_describe_selection_is_human_readable() -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "scripts", "scope": {"paths": ["scripts/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
        ]
    }

    selected = reusable_ci_scope.select_scenarios(
        "reusable-10-ci-python",
        ["tests/test_reusable_ci_scope.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    rationale = reusable_ci_scope.describe_selection(selected, full)

    assert rationale == "running 1/3 scenarios because only `tests/` changed"


def test_cli_outputs_matrix_and_rationale(capsys) -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
        ]
    }

    exit_code = reusable_ci_scope.main(
        [
            "--workflow-name",
            "selftest-reusable-ci",
            "--changed-files-json",
            json.dumps(["tests/test_example.py"]),
            "--matrix-json",
            json.dumps(full),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["matrix"] == {"include": [{"name": "tests"}]}
    assert payload["rationale"] == "running 1/2 scenarios because only `tests/` changed"


def test_github_outputs_use_multiline_format(tmp_path: Path) -> None:
    output_path = tmp_path / "outputs.txt"

    reusable_ci_scope._write_github_outputs(
        str(output_path),
        {"rationale": "first line\nsecond=line%"},
    )

    assert output_path.read_text(encoding="utf-8") == (
        "rationale<<__REUSABLE_CI_SCOPE_RATIONALE__\n"
        "first line\nsecond=line%\n"
        "__REUSABLE_CI_SCOPE_RATIONALE__\n"
    )


def test_python_resolver_preserves_runtime_selection():
    selected = reusable_ci_scope.select_python_matrix(
        "Gate", '["3.12","3.13"]', "3.12", ["src/example.py"], False
    )
    assert selected.matrix == {"include": [{"python-version": "3.12"}, {"python-version": "3.13"}]}
    assert reusable_ci_scope.select_python_matrix("Gate", "", "", [], False).matrix == {
        "include": [{"python-version": "3.13"}, {"python-version": "3.14"}]
    }
    assert reusable_ci_scope.select_python_matrix(
        "Gate", "3.13", "3.12", ["docs/a.md"], True
    ).matrix == {"include": [{"python-version": "3.13"}]}
    assert reusable_ci_scope.select_python_matrix(
        "Gate", '["3.12"]', "3.12", ["docs/a.md"], False
    ).matrix == {"include": []}


def test_python_resolver_keeps_explicit_legacy_runtime():
    selected = reusable_ci_scope.select_python_matrix("Gate", "[]", "3.12", [], False)
    assert selected.matrix == {"include": [{"python-version": "3.12"}]}


def test_python_resolver_rejects_ambiguous_inputs():
    import pytest

    for versions in ('["3.12", "3.12"]', "[3.12]", "[null]"):
        with pytest.raises(ValueError):
            reusable_ci_scope.select_python_matrix("Gate", versions, "3.12", [], False)
    with pytest.raises(ValueError):
        reusable_ci_scope.select_python_matrix("Gate", "", "3.12", [None], False)


def test_python_resolver_includes_flat_and_root_application_modules():
    for path in ("pa_core/pa.py", "dashboard/app.py", "another_package/nested/module.py", "app.py"):
        selected = reusable_ci_scope.select_python_matrix(
            "Gate", '["3.12","3.13"]', "3.12", [path], False
        )
        assert selected.selected_count == 2, path


def test_python_resolver_includes_dependency_locks_but_not_unrelated_lockfiles():
    for path in ("requirements.lock", "requirements-dev.lock", "requirements-test.lock"):
        selected = reusable_ci_scope.select_python_matrix(
            "Gate", '["3.12","3.13"]', "3.12", [path], False
        )
        assert selected.selected_count == 2, path
    for path in ("package-lock.json", "docs/lock-policy.md"):
        selected = reusable_ci_scope.select_python_matrix(
            "Gate", '["3.12","3.13"]', "3.12", [path], False
        )
        assert selected.selected_count == 0, path


def test_scope_selection_preserves_requested_metadata_and_includes_unscoped_scenarios() -> None:
    full = [
        {"name": "always"},
        {"name": "docs", "scope": "docs/"},
        {"name": "source", "paths": ["src/**"], "scope": {"reason": "source changed"}},
    ]
    selected = reusable_ci_scope.select_scenarios(
        "example", ["docs/guide.md"], full, {"strip_scope": False}
    )

    assert selected.matrix == [full[0], full[1]]
    assert selected.reason == "`always` is unscoped"
    assert selected.matched_patterns == ("docs/",)


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("docs/guide.md", "docs/", True),
        ("docs/guide.md", "docs", True),
        ("nested/a.py", "**/*.py", True),
        ("a.py", "**/*.py", True),
        ("src/a.py", "src/*.js", False),
    ],
)
def test_path_matching_normalizes_common_scope_forms(
    path: str, pattern: str, expected: bool
) -> None:
    assert reusable_ci_scope._path_matches(path, pattern) is expected


def test_cli_reads_changed_files_and_matrix_files_and_writes_outputs(
    tmp_path: Path, capsys
) -> None:
    changed = tmp_path / "changed.txt"
    changed.write_text("docs/readme.md\n\n", encoding="utf-8")
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"include": [{"name": "docs", "paths": ["docs/**"]}]}))
    output = tmp_path / "out.txt"

    assert (
        reusable_ci_scope.main(
            [
                "--workflow-name",
                "example",
                "--changed-files-file",
                str(changed),
                "--matrix-file",
                str(matrix),
                "--github-output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["selected_count"] == "1"
    assert "matrix<<__REUSABLE_CI_SCOPE_MATRIX__" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--workflow-name", "x", "--matrix-json", "not-json"], "must be valid JSON"),
        (["--workflow-name", "x", "--matrix-json", '"not a matrix"'], "matrix must be"),
        (
            ["--workflow-name", "x", "--matrix-json", "[]", "--changed-files-json", "{}"],
            "JSON array",
        ),
    ],
)
def test_cli_rejects_invalid_input(argv: list[str], message: str) -> None:
    with pytest.raises(SystemExit, match=message):
        reusable_ci_scope.main(argv)


def test_scenario_matrix_receipt_binds_environment_and_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "GITHUB_REPOSITORY": "stranske/Workflows",
        "GITHUB_RUN_ID": "12",
        "GITHUB_RUN_ATTEMPT": "3",
        "PR_HEAD_SHA": "a" * 40,
        "PR_BASE_SHA": "b" * 40,
    }.items():
        monkeypatch.setenv(key, value)
    selected = reusable_ci_scope.select_scenarios("x", ["docs/a.md"], [], None)
    receipt = reusable_ci_scope.scenario_matrix_receipt(
        ".github/workflows/pr-00-gate.yml", ["docs/a.md"], [], selected
    )

    assert receipt["schema"] == "scenario-matrix-producer/v1"
    assert receipt["run_attempt"] == 3
    assert len(receipt["helper_sha256"]) == 64


def test_internal_normalization_and_option_helpers_cover_supported_shapes() -> None:
    assert reusable_ci_scope._options_from(None) == reusable_ci_scope.SelectionOptions()
    assert reusable_ci_scope._options_from({"force_full": 1, "strip_scope": 0}) == (
        reusable_ci_scope.SelectionOptions(force_full=True, strip_scope=False)
    )
    assert reusable_ci_scope._normalize_path(r"./docs\\guide.md") == "docs/guide.md"
    assert reusable_ci_scope._normalize_matrix([{"name": "one"}])[1] == "list"
    with pytest.raises(TypeError):
        reusable_ci_scope._normalize_matrix({"exclude": []})
    with pytest.raises(TypeError):
        reusable_ci_scope._restore_matrix([], [], "include")


def test_scope_extraction_and_selection_reason_cover_legacy_forms() -> None:
    assert reusable_ci_scope._scope_for({"scope": {"path_globs": ["a/**"], "reason": " A "}}) == (
        ["a/**"],
        "A",
    )
    assert reusable_ci_scope._scope_for({"changed-paths": "docs/**"}) == (["docs/**"], None)
    assert reusable_ci_scope._changed_roots([]) == "changed files were unavailable"
    assert reusable_ci_scope._changed_roots(["one.py", "two.py", "three.py", "four.py"]) == (
        "changed inputs touched 4 top-level paths"
    )
    assert reusable_ci_scope._scenario_name({"id": "id-value"}) == "id-value"
    assert reusable_ci_scope._scenario_name({}) == "unnamed"


def test_selection_falls_back_for_empty_changes_and_unknown_paths() -> None:
    full = {"include": [{"name": "docs", "scope": {"paths": ["docs/**"]}}]}
    empty = reusable_ci_scope.select_scenarios("x", [], full)
    unmatched = reusable_ci_scope.select_scenarios("x", ["src/app.py"], full)
    assert empty.reason == "changed files were unavailable"
    assert empty.selected_count == 1
    assert unmatched.selected_count == 0
    assert reusable_ci_scope.describe_selection(empty, full) == (
        "running 1/1 scenarios because changed files were unavailable"
    )


def test_changed_files_environment_and_delimiter_collision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHANGED_FILES_JSON", '["docs/a.md", 4]')
    args = reusable_ci_scope.build_parser().parse_args(
        ["--workflow-name", "x", "--matrix-json", "[]"]
    )
    assert reusable_ci_scope._parse_changed_files(args) == ["docs/a.md", "4"]
    destination = tmp_path / "output.txt"
    reusable_ci_scope._write_github_outputs(str(destination), {"x": "__REUSABLE_CI_SCOPE_X__"})
    assert "___REUSABLE_CI_SCOPE_X___" in destination.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("python_versions", "python_version", "changed_files", "force_full", "message"),
    [
        ('["3.12"]', "3.12", [None], False, "changed_files"),
        ('["3.12"]', "3.12", [], "yes", "force_full"),
        ("[3.12]", "3.12", [], False, "nonempty strings"),
    ],
)
def test_python_matrix_rejects_invalid_selector_inputs(
    python_versions: str,
    python_version: str,
    changed_files: list[object],
    force_full: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        reusable_ci_scope.select_python_matrix(
            "Gate", python_versions, python_version, changed_files, force_full
        )
