from __future__ import annotations

import pytest
from scripts import create_verifier_labels as cvl


def test_filter_labels_defaults_to_all() -> None:
    labels = cvl._filter_labels(cvl.LABELS, [])
    assert [label["name"] for label in labels] == [label["name"] for label in cvl.LABELS]


def test_filter_labels_returns_subset_in_defined_order() -> None:
    labels = cvl._filter_labels(cvl.LABELS, ["verify:compare", "verify:checkbox"])
    assert [label["name"] for label in labels] == ["verify:checkbox", "verify:compare"]


def test_filter_labels_rejects_unknown_label() -> None:
    with pytest.raises(SystemExit, match="Unknown label name"):
        cvl._filter_labels(cvl.LABELS, ["verify:unknown"])


def test_parse_repos_from_workflow_reads_block(tmp_path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        "\n".join(
            [
                "name: Example",
                "env:",
                "  REGISTERED_CONSUMER_REPOS: |",
                "    stranske/Foo",
                "    # comment",
                "    stranske/Bar",
                "",
                "jobs:",
                "  noop:",
                "    runs-on: ubuntu-latest",
            ]
        ),
        encoding="utf-8",
    )

    assert cvl._parse_repos_from_workflow(workflow) == ["stranske/Foo", "stranske/Bar"]


def test_normalize_repo_list_dedupes_in_order() -> None:
    repos = ["a", "b", "a", "c", "b"]
    assert cvl._normalize_repo_list(repos) == ["a", "b", "c"]


def test_validate_repo_count_mismatch_raises() -> None:
    with pytest.raises(SystemExit, match="Expected 2 repos"):
        cvl._validate_repo_count(["one"], 2)


def test_extract_label_names_parses_valid_payload() -> None:
    payload = """
    [
      {"name": "verify:checkbox"},
      {"name": "verify:evaluate"},
      {"name": "verify:compare"},
      {"name": ""},
      {"foo": "bar"}
    ]
    """
    assert cvl._extract_label_names(payload) == {
        "verify:checkbox",
        "verify:evaluate",
        "verify:compare",
    }


def test_find_missing_labels_returns_ordered_names() -> None:
    existing = {"verify:checkbox"}
    missing = cvl._find_missing_labels(existing, list(cvl.LABELS))
    assert missing == ["verify:evaluate", "verify:compare", "verify:create-issue"]


def test_parse_split_validate_extract_and_command_helpers_cover_edge_cases(tmp_path) -> None:
    assert cvl._parse_repos_from_workflow(tmp_path / "missing.yml") == []
    no_repos = tmp_path / "no-repos.yml"
    no_repos.write_text("name: no repos\n", encoding="utf-8")
    assert cvl._parse_repos_from_workflow(no_repos) == []
    assert cvl._split_csv(None) == []
    assert cvl._split_csv(" one, ,two ") == ["one", "two"]
    cvl._validate_repo_count(["one"], None)
    cvl._validate_repo_count(["one"], 1)
    with pytest.raises(SystemExit, match="Unable to parse"):
        cvl._extract_label_names("not json")
    with pytest.raises(SystemExit, match="expected a list"):
        cvl._extract_label_names('{"name": "verify:checkbox"}')
    command = cvl._build_command("octo/demo", cvl.LABELS[0])
    assert command[:6] == ["gh", "label", "create", "verify:checkbox", "--repo", "octo/demo"]
    assert cvl._build_list_command("octo/demo")[-4:] == ["--json", "name", "--limit", "500"]
    assert "'has space'" in cvl._format_command(["gh", "has space"])


def test_main_dry_run_execute_and_check_modes(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "labels",
            "--repos",
            "octo/a,octo/a,octo/b",
            "--labels",
            "verify:checkbox",
            "--only",
            "octo/a",
        ],
    )
    assert cvl.main() == 0
    assert "gh label create verify:checkbox --repo octo/a" in capsys.readouterr().out

    commands = []
    monkeypatch.setattr(cvl.subprocess, "run", lambda cmd, **kwargs: commands.append((cmd, kwargs)))
    monkeypatch.setattr(
        "sys.argv", ["labels", "--repos", "octo/a", "--labels", "verify:checkbox", "--execute"]
    )
    assert cvl.main() == 0
    assert commands[0][0] == cvl._build_command("octo/a", cvl.LABELS[0])
    assert commands[0][1] == {"check": True}

    class Result:
        stdout = '[{"name": "verify:checkbox"}]'

    monkeypatch.setattr(cvl.subprocess, "run", lambda *args, **kwargs: Result())
    monkeypatch.setattr(
        "sys.argv", ["labels", "--repos", "octo/a", "--labels", "verify:checkbox", "--check"]
    )
    assert cvl.main() == 0
    assert "octo/a: ok" in capsys.readouterr().out

    class MissingResult:
        stdout = "[]"

    monkeypatch.setattr(cvl.subprocess, "run", lambda *args, **kwargs: MissingResult())
    assert cvl.main() == 1
    assert "octo/a: missing verify:checkbox" in capsys.readouterr().out


def test_main_reads_file_applies_filters_and_rejects_invalid_requests(
    tmp_path, monkeypatch
) -> None:
    workflow = tmp_path / "repos.yml"
    workflow.write_text(
        "REGISTERED_CONSUMER_REPOS: |\n  octo/a\n  octo/b\nnext: value\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "sys.argv",
        ["labels", "--repos-file", str(workflow), "--exclude", "octo/a", "--expect-count", "1"],
    )
    assert cvl.main() == 0

    monkeypatch.setattr("sys.argv", ["labels", "--repos", "octo/a", "--execute", "--check"])
    with pytest.raises(SystemExit, match="Choose either"):
        cvl.main()
    monkeypatch.setattr("sys.argv", ["labels", "--repos", "octo/a", "--only", "octo/b"])
    with pytest.raises(SystemExit, match="No repos"):
        cvl.main()
