import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_GUIDE = REPO_ROOT / "docs" / "WORKFLOW_GUIDE.md"
INTEGRATION_GUIDE = REPO_ROOT / "docs" / "INTEGRATION_GUIDE.md"
WORKFLOW_DIRS = (
    REPO_ROOT / ".github" / "workflows",
    REPO_ROOT / "templates" / "consumer-repo" / ".github" / "workflows",
)

WORKFLOW_PREFIXES = (
    "agents-",
    "reusable-",
    "health-",
    "maint-",
    "pr-",
    "selftest-",
    "autofix-",
)
SKIP_YML_NAMES = frozenset({"labels-core.yml", "registry.yml"})
ACTIVE_YML_PATTERN = re.compile(r"`([^`]+?\.yml)`")


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _workflow_exists(name: str) -> bool:
    return any((directory / name).is_file() for directory in WORKFLOW_DIRS)


def _is_checked_workflow_name(name: str) -> bool:
    if "*" in name or "/" in name:
        return False
    if name in SKIP_YML_NAMES:
        return False
    if name == "autofix.yml":
        return True
    return name.startswith(WORKFLOW_PREFIXES)


def _active_workflow_guide_text() -> str:
    content = WORKFLOW_GUIDE.read_text(encoding="utf-8")
    marker = "## Archived & Legacy Workflows"
    assert marker in content, f"Missing {marker!r} in WORKFLOW_GUIDE.md"
    return content.split(marker, 1)[0]


def _integration_guide_ci_table_text() -> str:
    content = INTEGRATION_GUIDE.read_text(encoding="utf-8")
    start = content.index("### CI Workflows")
    end = content.index("## Workflow Outputs", start)
    return content[start:end]


def _collect_catalog_workflow_names() -> set[str]:
    names: set[str] = set()
    for match in ACTIVE_YML_PATTERN.finditer(_active_workflow_guide_text()):
        candidate = match.group(1)
        if _is_checked_workflow_name(candidate):
            names.add(candidate)
    for match in ACTIVE_YML_PATTERN.finditer(_integration_guide_ci_table_text()):
        candidate = match.group(1)
        if _is_checked_workflow_name(candidate):
            names.add(candidate)
    return names


def test_active_catalog_workflows_exist() -> None:
    names = _collect_catalog_workflow_names()
    assert names, "expected at least one catalog workflow name"
    missing = sorted(name for name in names if not _workflow_exists(name))
    assert not missing, f"missing workflow files: {', '.join(missing)}"


def test_workflow_guide_marks_pr_meta_v4_as_workflows_local() -> None:
    content = _read("docs/WORKFLOW_GUIDE.md")

    assert "agents-pr-meta-v4.yml" in content
    assert "Workflows-local" in content
    assert "agents-80-pr-event-hub.yml" in content
    assert "agents-81-gate-followups.yml" in content


def test_ci_workflows_guide_marks_consumer_default_event_hub_pair() -> None:
    content = _read("docs/ci/WORKFLOWS.md")

    assert "agents-pr-meta-v4.yml" in content
    assert "Workflows-repo service workflow" in content
    assert "agents-80-pr-event-hub.yml" in content
    assert "agents-81-gate-followups.yml" in content


def test_keepalive_reporter_docs_require_an_app_owned_writer() -> None:
    guide = _read("docs/WORKFLOW_GUIDE.md")
    checklist = _read("docs/workflow-updates/workflow-checklist.md")

    guide_entry = next(
        line for line in guide.splitlines() if "`agents-keepalive-loop-reporter.yml`" in line
    )
    checklist_entry = next(
        line for line in checklist.splitlines() if "`agents-keepalive-loop-reporter.yml`" in line
    )

    for entry in (guide_entry, checklist_entry):
        assert "KEEPALIVE_APP" in entry
        assert "WORKFLOWS_APP" in entry
        assert "fail" in entry.lower() and "closed" in entry.lower()
        assert "no bespoke App mint" not in entry

    assert guide_entry.count("KEEPALIVE_APP") >= 1
    assert checklist_entry.count("KEEPALIVE_APP") >= 1
