from __future__ import annotations

from pathlib import Path

from scripts import validate_dependency_test_setup as validator


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_check_lock_file_completeness_accepts_dynamic_extra_extraction(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "pyproject.toml",
        """
[project.optional-dependencies]
llm = ["openai"]
dev = ["pytest"]
""",
    )
    _write(
        tmp_path / ".github/workflows/dependabot-auto-lock.yml",
        """
jobs:
  lock:
    steps:
      - run: python - <<'PY'
          import tomllib
          optional-dependencies = "read from pyproject"
          tools/requirements-llm.txt
          PY
""",
    )

    passed, issues = validator.check_lock_file_completeness()

    assert passed
    assert issues == []


def test_check_lock_file_completeness_reports_missing_optional_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "pyproject.toml", "[project]\nname = 'workflows'\n")

    passed, issues = validator.check_lock_file_completeness()

    assert not passed
    assert issues == ["No [project.optional-dependencies] section found"]


def test_check_lock_file_completeness_reports_missing_workflow_extra(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "pyproject.toml",
        """
[project.optional-dependencies]
llm = ["openai"]
dev = ["pytest"]
""",
    )
    _write(
        tmp_path / ".github/workflows/dependabot-auto-lock.yml",
        "run: uv pip compile --extra llm\n",
    )

    passed, issues = validator.check_lock_file_completeness()

    assert not passed
    assert issues == ["dependabot-auto-lock.yml missing --extra dev"]


def test_check_for_hardcoded_versions_reports_non_comment_test_versions(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "tests/test_versions.py",
        """
def test_version():
    version = "1.2.3"
    assert version == "1.2.3"
""",
    )

    passed, issues = validator.check_for_hardcoded_versions()

    assert not passed
    assert issues[0] == "Found potential hardcoded versions in tests:"
    assert any("tests/test_versions.py:4" in issue for issue in issues)


def test_check_for_hardcoded_versions_allows_comments_and_alignment_exceptions(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "tests/test_comments.py",
        """
def test_comment_only():
    # assert version == "1.2.3"
    assert True
""",
    )
    _write(
        tmp_path / "tests/test_dependency_version_alignment.py",
        """
def test_alignment_fixture():
    assert "1.2.3" == "1.2.3"
""",
    )

    passed, issues = validator.check_for_hardcoded_versions()

    assert passed
    assert issues == []


def test_check_metadata_serialization_accepts_model_dump_calls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "src/trend_analysis/io/validators.py",
        "validated.metadata.model_dump(mode='json')\n",
    )
    _write(
        tmp_path / "src/trend_analysis/io/market_data.py",
        "metadata.model_dump(mode='json')\n",
    )
    _write(
        tmp_path / "streamlit_app/components/data_schema.py",
        "metadata.model_dump(mode='json')\n",
    )

    passed, issues = validator.check_metadata_serialization()

    assert passed
    assert issues == []


def test_check_metadata_serialization_reports_present_files_without_model_dump(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "src/trend_analysis/io/validators.py", "return validated.metadata\n")
    _write(tmp_path / "src/trend_analysis/io/market_data.py", "return metadata\n")
    _write(tmp_path / "streamlit_app/components/data_schema.py", "return metadata\n")

    passed, issues = validator.check_metadata_serialization()

    assert not passed
    assert issues == [
        "load_and_validate_upload may not be serializing metadata properly",
        "attach_metadata may not be serializing metadata properly",
        "_build_meta may not be serializing metadata properly",
    ]


def test_check_metadata_serialization_accepts_absent_optional_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    passed, issues = validator.check_metadata_serialization()

    assert passed
    assert issues == []


def test_check_metadata_serialization_ignores_absent_optional_file_with_present_issues(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "src/trend_analysis/io/validators.py",
        "validated.metadata.model_dump(mode='json')\n",
    )
    _write(tmp_path / "src/trend_analysis/io/market_data.py", "return metadata\n")

    passed, issues = validator.check_metadata_serialization()

    assert not passed
    assert issues == ["attach_metadata may not be serializing metadata properly"]


def test_check_test_expectations_reports_attribute_and_identity_patterns(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "tests/test_validators.py",
        """
def test_metadata_expectations(frame, metadata):
    assert frame.attrs["metadata"].mode == "live"
    assert meta["metadata"] is metadata
""",
    )

    passed, issues = validator.check_test_expectations()

    assert not passed
    assert issues == [
        "test_validators.py: Uses .mode attribute access instead of dict access",
        "test_validators.py: Uses 'is' identity check instead of equality",
    ]


def test_check_test_expectations_accepts_dict_based_metadata_access(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "tests/test_data_schema.py",
        """
def test_metadata_expectations(meta, metadata):
    assert meta["metadata"]["mode"] == "live"
    assert meta["metadata"] == metadata
""",
    )

    passed, issues = validator.check_test_expectations()

    assert passed
    assert issues == []


def test_main_returns_zero_and_prints_cli_success(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / "pyproject.toml",
        """
[project.optional-dependencies]
llm = ["openai"]
dev = ["pytest"]
""",
    )
    _write(
        tmp_path / ".github/workflows/dependabot-auto-lock.yml",
        "run: uv pip compile --extra llm --extra dev\n",
    )
    _write(
        tmp_path / "src/trend_analysis/io/validators.py",
        "validated.metadata.model_dump(mode='json')\n",
    )
    _write(
        tmp_path / "src/trend_analysis/io/market_data.py",
        "metadata.model_dump(mode='json')\n",
    )
    _write(
        tmp_path / "streamlit_app/components/data_schema.py",
        "metadata.model_dump(mode='json')\n",
    )
    _write(
        tmp_path / "tests/test_data_schema.py",
        """
def test_metadata_expectations(meta, metadata):
    assert meta["metadata"]["mode"] == "live"
""",
    )

    exit_code = validator.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Dependency Test Setup Validation" in output
    assert "Checking: Lock file completeness" in output
    assert "All validation checks passed!" in output


def test_main_returns_one_and_prints_cli_failures(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "pyproject.toml", "[project]\nname = 'workflows'\n")
    _write(
        tmp_path / "tests/test_versions.py",
        """
def test_version():
    assert version == "1.2.3"
""",
    )

    exit_code = validator.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Some validation checks failed:" in output
    assert "No [project.optional-dependencies] section found" in output
    assert "Found potential hardcoded versions in tests:" in output
