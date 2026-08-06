"""Regression tests for the synced issue-format validator."""

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _validator():
    path = Path(".github/scripts/issue_format.py")
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
        "## Tasks\n- [ ] Implement it\n\n## Acceptance Criteria\n- gh run watch succeeds\n- curl endpoint returns 200\n"
    )
    assert report.ok
