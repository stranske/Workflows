"""Regression tests for the synced issue-format validator."""

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

VALID_CONTEXT = (
    "## Why\nCurrent evidence\n\n## Scope\nBounded scope\n\n"
    "## Implementation Notes\nDetails\n\n## Non-Goals\nNo expansion\n\n"
)


def _validator(path: Path = Path(".github/scripts/issue_format.py")):
    spec = spec_from_file_location("issue_format", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fenced_headings_do_not_satisfy_required_sections() -> None:
    validator = _validator()
    report = validator.validate(
        "```markdown\n## Tasks\n- [ ] pretend\n## Acceptance Criteria\n- pytest tests/test_x.py\n```\n"
    )
    assert not report.ok
    assert set(report.missing_required) == {"Tasks", "Acceptance Criteria"}


def test_fence_with_language_marker_does_not_close_a_code_block() -> None:
    validator = _validator()
    report = validator.validate(
        "```markdown\n## Tasks\n- [ ] pretend\n```python\n"
        "## Acceptance Criteria\n- pytest tests/test_x.py\n````\n"
    )
    assert not report.ok
    assert "Acceptance Criteria" in report.missing_required


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_list_indented_fenced_acceptance_command_is_ignored(
    validator_path: Path, fence: str
) -> None:
    """A four-space list fence is an example, not an observable gate."""
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `src/client.py`\n\n"
        + f"## Acceptance Criteria\n- Example command:\n\n    {fence}sh\n    pytest tests/test_x.py\n    {fence}\n"
    )
    assert not report.ok
    assert any("names no test" in problem for problem in report.problems)


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
def test_category_word_backticked_target_is_not_concrete(validator_path: Path) -> None:
    """A backticked category word after an explicit category is not a concrete target."""
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update function `file`\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert not report.ok
    assert "concrete file" in report.as_markdown()


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
@pytest.mark.parametrize("target", ["validate", "timeout"])
def test_explicit_category_accepts_quoted_lowercase_identifier(
    validator_path: Path, target: str
) -> None:
    validator = _validator(validator_path)
    category = "function" if target == "validate" else "key"
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] Update {category} `{target}`\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert report.ok


@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_fence_close_requires_marker_only_line(marker: str) -> None:
    """Trailing text after fence markers must not end the fenced region."""
    validator = _validator()
    close_with_junk = f"{marker} not-a-close"
    body = (
        f"{marker}markdown\n"
        "## Tasks\n- [ ] pretend\n"
        f"{close_with_junk}\n"
        "## Acceptance Criteria\n- pytest tests/test_x.py\n"
        f"{marker}\n"
    )
    report = validator.validate(body)
    assert not report.ok
    assert set(report.missing_required) >= {"Tasks", "Acceptance Criteria"}
    # Section body stripping must keep pretending the junk line is still inside.
    stripped = validator._without_fenced_code(body)
    assert "Acceptance Criteria" not in stripped
    assert "pretend" not in stripped


def test_heading_with_trailing_qualifier_matches_required_section() -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks (in order)\n- [ ] Update `.github/workflows/guard.yml`\n\n"
        + "## Acceptance Criteria (all must hold)\n- pytest tests/test_x.py passes\n"
    )
    assert report.ok


@pytest.mark.parametrize("separator", ["-", "/"])
@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
def test_heading_with_spaced_trailing_qualifier_matches_required_section(
    separator: str, validator_path: Path
) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks {separator} in order\n- [ ] Update `.github/workflows/guard.yml`\n\n"
        + f"## Acceptance Criteria {separator} all must hold\n- pytest tests/test_x.py passes\n"
    )
    assert report.ok


def test_checkbox_and_subjective_errors_are_non_conforming() -> None:
    validator = _validator()
    report = validator.validate(
        "## Tasks\nImplement it.\n\n## Acceptance Criteria\n- pytest tests/test_x.py passes\n- It is clean\n"
    )
    assert not report.ok
    assert "not yet agent-processable" in report.as_markdown()


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
def test_subjective_words_in_fenced_acceptance_examples_are_ignored(validator_path: Path) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `src/client.py`\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n\n"
        + "```sh\necho fast\n```\n"
    )
    assert report.ok


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
@pytest.mark.parametrize(
    ("acceptance", "expected_ok"),
    [
        ("- pytest tests/test_x.py passes; `fast` is a literal\n", True),
        ("- pytest tests/test_x.py passes fast\n", False),
    ],
)
def test_subjective_words_in_inline_code_are_ignored_but_prose_is_rejected(
    validator_path: Path, acceptance: str, expected_ok: bool
) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `src/client.py`\n\n"
        + "## Acceptance Criteria\n"
        + acceptance
    )
    assert report.ok is expected_ok


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
def test_acceptance_gate_inside_fence_does_not_satisfy_validation(
    validator_path: Path,
) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `tests/fast/test_api.py`\n\n"
        + "## Acceptance Criteria\nRun the regression suite:\n"
        + "```sh\npython -m pytest tests/fast/test_api.py -q\n```\n"
    )
    assert not report.ok
    assert "names no test" in report.problems[0]


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
def test_acceptance_path_component_is_not_subjective_prose(validator_path: Path) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `tests/fast/test_api.py`\n\n"
        + "## Acceptance Criteria\n- [ ] Run pytest tests/fast/test_api.py and confirm it passes.\n"
    )
    assert report.ok


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
def test_acceptance_slash_separated_subjective_prose_is_rejected(
    validator_path: Path,
) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `tests/fast/test_api.py`\n\n"
        + "## Acceptance Criteria\n- [ ] Run pytest tests/fast/test_api.py and make the response fast/performant.\n"
    )
    assert not report.ok
    assert "subjective wording" in report.problems[0]


def test_runner_and_curl_are_accepted_gates() -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `.github/workflows/guard.yml`\n\n## Acceptance Criteria\n- gh run watch succeeds\n- curl endpoint returns 200\n"
    )
    assert report.ok


@pytest.mark.parametrize(
    "criterion",
    [
        "API returns 400 status for invalid input",
        "endpoint returns 400 status for invalid input",
        "request returns 400 status for invalid input",
        "response returns 400 status for invalid input",
        "API responds with 400 status for invalid input",
    ],
)
def test_api_status_sentence_is_an_accepted_gate(criterion: str) -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] Update `src/client.py`\n\n## Acceptance Criteria\n- {criterion}\n"
    )
    assert report.ok


def test_missing_acceptance_criteria_is_reported_once() -> None:
    validator = _validator()
    report = validator.validate("## Tasks\n- [ ] Implement it\n")
    assert report.missing_required == ["Acceptance Criteria"]
    assert "No `Acceptance Criteria` section" not in report.as_markdown()


def test_implementation_notes_is_a_recommended_section() -> None:
    validator = _validator()
    report = validator.validate(
        "## Tasks\n- [ ] Update `src/client.py`\n\n## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert "Implementation Notes" in report.missing_recommended
    assert report.ok


def test_implementation_notes_does_not_satisfy_tasks() -> None:
    validator = _validator()
    report = validator.validate(
        "## Implementation Notes\n- [ ] Not a task\n\n"
        "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert "Tasks" in report.missing_required


def test_nested_headings_remain_inside_their_parent_section() -> None:
    validator = _validator()
    report = validator.validate(
        "## Why\nCurrent evidence\n\n## Scope\nBounded scope\n\n"
        "## Tasks\n### Backend\n- [ ] Update `src/client.py`\n\n"
        "## Acceptance Criteria\n### Verification\n- pytest tests/test_x.py passes\n\n"
        "## Implementation Notes\nDetails\n\n## Non-Goals\nNo expansion\n"
    )
    assert report.ok


def test_verify_is_an_accepted_gate() -> None:
    validator = _validator()
    report = validator.validate(
        "## Why\nCurrent evidence\n\n## Scope\nBounded scope\n\n"
        "## Tasks\n- [ ] Update `src/client.py`\n\n"
        "## Acceptance Criteria\n- Verify the endpoint response\n\n"
        "## Implementation Notes\nDetails\n\n## Non-Goals\nNo expansion\n"
    )
    assert report.ok


def test_task_without_concrete_target_is_non_conforming() -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Fix bugs\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert not report.ok
    assert "concrete file" in report.as_markdown()


def test_punctuation_does_not_make_a_generic_task_target_concrete() -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Improve file handling.\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert not report.ok


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
@pytest.mark.parametrize("task", ["Make the UI better", "Just fix bugs", "Go improve it"])
def test_command_words_in_prose_are_not_concrete_targets(task: str, validator_path: Path) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] {task}\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert not report.ok
    assert "concrete file" in report.as_markdown()


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
@pytest.mark.parametrize(
    "task",
    [
        # No separate path/file token — these must not pass via _TASK_COMMAND alone.
        "Run python -m pytestfoo",
        "Run python -m unittestfoo",
        "Run gh run",
        "Run gh workflow run",
        "Run `gh run`",
        "Run `gh workflow run`",
    ],
)
def test_incomplete_command_shaped_tasks_are_rejected(task: str, validator_path: Path) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] {task}\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert not report.ok
    assert "concrete file" in report.as_markdown()


@pytest.mark.parametrize(
    "validator_path",
    [
        Path(".github/scripts/issue_format.py"),
        Path("templates/consumer-repo/.github/scripts/issue_format.py"),
    ],
)
@pytest.mark.parametrize(
    "task",
    [
        "Run python -m pytest tests/test_x.py",
        "Run python3 -m unittest tests/test_x.py",
        "Run gh run watch",
        "Run gh workflow run selftest-ci.yml",
        "Run `gh run watch`",
        "Run `gh workflow run selftest-ci.yml`",
    ],
)
def test_complete_command_shaped_tasks_are_accepted(task: str, validator_path: Path) -> None:
    validator = _validator(validator_path)
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] {task}\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert report.ok, report.as_markdown()


@pytest.mark.parametrize(
    "task",
    [
        "Fix `bugs`",
        "Fix bugs `later`",
        "Fix file handling",
        "Update the configuration",
        "Update the GitHub configuration",
        "Update the JavaScript documentation",
    ],
)
def test_vague_task_targets_are_non_conforming(task: str) -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] {task}\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert not report.ok
    assert "concrete file" in report.as_markdown()


@pytest.mark.parametrize(
    "task",
    [
        "Update src/main.go",
        "Update pom.xml",
        "Update Dockerfile",
        "Wire `IssueFormatter` into the guard",
        "Write unit tests for calculateDiscount function",
        "Touch file `src/client.py`",
        "Run pytest tests/scripts/test_issue_format.py",
    ],
)
def test_concrete_unquoted_and_symbol_task_targets_are_accepted(task: str) -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + f"## Tasks\n- [ ] {task}\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert report.ok, report.as_markdown()


@pytest.mark.parametrize(
    "criterion",
    [
        "python -m unittest tests.guard passes",
        "node --test tests/guard.js passes",
        "pnpm vitest tests/guard.test.ts passes",
    ],
)
def test_named_non_pytest_commands_are_accepted_gates(criterion: str) -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `src/client.py`\n\n"
        + f"## Acceptance Criteria\n- {criterion}\n"
    )
    assert report.ok


def test_performant_is_subjective_acceptance_wording() -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Update `src/client.py`\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes and is performant\n"
    )
    assert not report.ok
    assert "performant" in report.as_markdown()


def test_backticked_make_test_is_a_concrete_target() -> None:
    validator = _validator()
    report = validator.validate(
        VALID_CONTEXT
        + "## Tasks\n- [ ] Run `make test`\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert report.ok


# --- Addressability ---------------------------------------------------------
#
# Regression cover for Fine-Art-Archive #406-409: perfectly-formatted issues,
# `agents:formatted` awarded, and every path they name existing only in a local
# workspace that is not on GitHub. A lane tried, could not find the files, and
# paused. Format and addressability are different axes; these pin the second.

# The six paths #409 actually instructed an agent to modify. None is in the repo.
FAA_409_PATHS = (
    "scripts/automation_audit.py",
    "automation_state.json",
    "scripts/audit_checks/state_integrity.py",
    "scripts/acquire.py",
    "discovery_frontier.json",
    "scripts/promote_acquisitions.py",
)


def _body_citing(*paths: str) -> str:
    tasks = "\n".join(f"- [ ] Update `{p}`" for p in paths)
    return (
        VALID_CONTEXT
        + f"## Tasks\n{tasks}\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )


def test_issue_citing_only_absent_paths_is_not_addressable(tmp_path) -> None:
    validator = _validator()
    report = validator.validate(_body_citing(*FAA_409_PATHS), repo_root=tmp_path)
    assert not report.ok
    assert "None of the 6 paths" in report.as_markdown()


def test_one_resolving_path_is_enough_to_be_addressable(tmp_path) -> None:
    validator = _validator()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "acquire.py").write_text("x = 1\n")
    report = validator.validate(_body_citing(*FAA_409_PATHS), repo_root=tmp_path)
    assert report.ok
    assert "do not exist yet" in report.as_markdown()


def test_new_files_alone_do_not_fail_below_the_threshold(tmp_path) -> None:
    """Naming a file to be created is normal; two of them must not fail."""
    validator = _validator()
    report = validator.validate(
        _body_citing("src/brand_new.py", "tests/test_brand_new.py"), repo_root=tmp_path
    )
    assert report.ok


def test_explicit_create_paths_do_not_trigger_wrong_repository_failure(tmp_path) -> None:
    validator = _validator()
    body = (
        VALID_CONTEXT
        + "## Tasks\n"
        + "- [ ] Create `src/new_a.py`\n"
        + "- [ ] Add src/new_b.py\n"
        + "- [ ] Generate `tests/test_new_c.py`\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert validator.validate(body, repo_root=tmp_path).ok


def test_all_paths_resolving_produces_no_advisory(tmp_path) -> None:
    validator = _validator()
    (tmp_path / "src").mkdir()
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / "src" / name).write_text("x = 1\n")
    report = validator.validate(
        _body_citing("src/a.py", "src/b.py", "src/c.py"), repo_root=tmp_path
    )
    assert report.ok
    assert "do not exist yet" not in report.as_markdown()


def test_repo_root_is_optional_and_off_by_default(tmp_path) -> None:
    """Callers without a checkout keep the old pure-body behaviour."""
    validator = _validator()
    report = validator.validate(_body_citing(*FAA_409_PATHS))
    assert report.ok


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        ("`src/app.py:42`", ["src/app.py"]),  # file:line suffix stripped
        ("`src/app.py:10-20`", ["src/app.py"]),  # range suffix stripped
        ("`./src/app.py`", ["src/app.py"]),  # leading ./ normalised
        ("`.github/workflows/gate.yml`", [".github/workflows/gate.yml"]),
        ("`../src/app.py`", []),  # parent-relative paths are never repo evidence
        ("`/etc/passwd`", []),  # absolute paths are never repo evidence
        ("`https://example.com/x.py`", []),  # URLs are not repo paths
        ("`src/*.py`", []),  # globs are ambiguous
        ("`--flag`", []),  # CLI flags
        ("`pytest -q tests/x.py`", []),  # commands contain spaces
        ("`SomeClass`", []),  # bare symbols
        ("`config.yaml`", ["config.yaml"]),  # extension alone qualifies
    ],
)
def test_path_extraction_edges(span: str, expected: list[str]) -> None:
    validator = _validator()
    assert validator._cited_paths(f"prose {span} prose") == expected


def test_duplicate_citations_are_counted_once(tmp_path) -> None:
    validator = _validator()
    body = _body_citing("a/x.py", "a/x.py", "a/x.py", "a/x.py")
    assert validator._cited_paths(body) == ["a/x.py"]
    # one distinct path is below the judging threshold, so it cannot fail
    assert validator.validate(body, repo_root=tmp_path).ok


def test_unquoted_task_paths_are_checked_for_addressability(tmp_path) -> None:
    validator = _validator()
    body = (
        VALID_CONTEXT
        + "## Tasks\n"
        + "- [ ] Update scripts/missing_a.py\n"
        + "- [ ] Update .github/workflows/missing_b.yml\n"
        + "- [ ] Update tests/missing_c.py\n\n"
        + "## Acceptance Criteria\n- pytest tests/test_x.py passes\n"
    )
    assert validator._cited_paths(body) == [
        "scripts/missing_a.py",
        ".github/workflows/missing_b.yml",
        "tests/missing_c.py",
    ]
    assert not validator.validate(body, repo_root=tmp_path).ok


def test_pytest_node_ids_normalise_to_their_file() -> None:
    """`tests/x.py::test_a` and `::test_b` are one path, not two unknowns."""
    validator = _validator()
    body = "See `tests/test_gate.py::test_alpha` and `tests/test_gate.py::test_beta`."
    assert validator._cited_paths(body) == ["tests/test_gate.py"]


def test_format_contract_reference_is_not_counted_as_evidence(tmp_path) -> None:
    """Boilerplate every issue cites must not single-handedly pass the gate.

    Measured on Fine-Art-Archive #409: `docs/AGENT_ISSUE_FORMAT.md` was the only
    path that resolved, so counting it flipped a wholly-unaddressable issue to
    'addressable'.
    """
    validator = _validator()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "AGENT_ISSUE_FORMAT.md").write_text("contract\n")
    body = _body_citing(*FAA_409_PATHS) + "\nPer `docs/AGENT_ISSUE_FORMAT.md`.\n"
    assert "docs/AGENT_ISSUE_FORMAT.md" not in validator._cited_paths(body)
    report = validator.validate(body, repo_root=tmp_path)
    assert not report.ok
    assert "None of the 6 paths" in report.as_markdown()


def test_package_relative_citations_resolve(tmp_path) -> None:
    """`collect/quality.py` should find `src/pkg/collect/quality.py`.

    Issues cite package-relative paths constantly. Counting them as missing
    would both spam the advisory and undercount `resolved`, which is what the
    failure rule keys on.
    """
    validator = _validator()
    pkg = tmp_path / "src" / "mypkg" / "collect"
    pkg.mkdir(parents=True)
    (pkg / "quality.py").write_text("x = 1\n")
    resolved, unresolved = validator._resolve_citations("cites `collect/quality.py`", tmp_path)
    assert resolved == ["collect/quality.py"]
    assert unresolved == []


def test_search_roots_stay_bounded(tmp_path) -> None:
    """A wide src/ must not turn resolution into an unbounded walk."""
    validator = _validator()
    base = tmp_path / "src"
    base.mkdir()
    for i in range(40):
        (base / f"pkg{i:02d}").mkdir()
    roots = validator._search_roots(tmp_path)
    assert len(roots) <= 1 + 1 + 12  # repo root + src + capped children
