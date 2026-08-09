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
