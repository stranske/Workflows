"""November 2026 workflow audit archive report (#4770 acceptance)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_REPORT = REPO_ROOT / "docs/archive/audits/WORKFLOW_AUDIT_2026-11-19.md"

# Non-dynamic workflow files called out in the November 2026 audit baseline.
BELOW_50_WORKFLOWS = (
    "agents-dedup.yml",
    "agents-keepalive-loop-reporter.yml",
    "maint-46-post-ci.yml",
    "health-68-consumer-sync-drift.yml",
    "agents-63-issue-intake.yml",
    "maint-sync-env-from-pyproject.yml",
    "pr-46-dependency-repair-contract.yml",
    "health-40-repo-selfcheck.yml",
    "health-41-repo-health.yml",
    "maint-65-sync-label-docs.yml",
    "agents-verifier.yml",
    "agents-auto-label.yml",
    "maint-71-auto-fix-integration.yml",
    "agents-verify-to-issue-v2.yml",
    "agents-verify-to-new-pr.yml",
    "agents-debug-issue-event.yml",
    "agents-capability-check.yml",
    "agents-decompose.yml",
    "maint-auto-label-dep-prs.yml",
    "health-83-dependency-sync-efficiency.yml",
)

# Remediation targets for issue #4770 task T4 (log-failed inspection).
T4_FAILURE_INSPECTION_WORKFLOWS = (
    "agents-keepalive-loop-reporter.yml",
    "maint-46-post-ci.yml",
    "agents-63-issue-intake.yml",
    "maint-sync-env-from-pyproject.yml",
    "pr-46-dependency-repair-contract.yml",
    "health-40-repo-selfcheck.yml",
    "health-41-repo-health.yml",
    "maint-84-prune-agent-stubs.yml",
    "agents-weekly-metrics.yml",
    "health-78-backplane-contract.yml",
    "health-85-ci-time-budget.yml",
)

BAND_50_80_WORKFLOWS = (
    "agents-moderate-connector.yml",
    "agents-keepalive-loop.yml",
    "selftest-ci.yml",
    "pr-00-gate.yml",
    "health-74-template-drift.yml",
    "health-78-backplane-contract.yml",
    "maint-52-sync-dev-versions.yml",
    "health-85-ci-time-budget.yml",
    "agents-71-codex-belt-dispatcher.yml",
    "maint-66-monthly-audit.yml",
    "maint-84-prune-agent-stubs.yml",
    "agents-weekly-metrics.yml",
    "maint-88-verifier-runtime-comparison.yml",
)


def _section_text(text: str, heading_prefix: str) -> str:
    start = text.index(heading_prefix)
    rest = text[start + len(heading_prefix) :]
    next_heading = rest.find("\n## ")
    return rest if next_heading == -1 else rest[:next_heading]


def test_november_2026_audit_report_exists() -> None:
    assert AUDIT_REPORT.name == "WORKFLOW_AUDIT_2026-11-19.md"
    assert AUDIT_REPORT.is_file()


def test_november_2026_audit_report_sections() -> None:
    text = AUDIT_REPORT.read_text(encoding="utf-8")
    required = (
        "Non-dynamic workflows below 50%",
        "Workflows in the 50",
        "Workflows not run",
        "Parallelism, runtime, and caching",
        "docs/LABELS.md",
        "docs/WORKFLOW_GUIDE.md",
        "Consumer sync",
    )
    for fragment in required:
        assert fragment in text, f"missing audit section or doc surface: {fragment!r}"


def test_november_2026_audit_covers_below_50_workflows() -> None:
    text = AUDIT_REPORT.read_text(encoding="utf-8")
    section = _section_text(text, "## Non-dynamic workflows below 50%")
    missing = [name for name in BELOW_50_WORKFLOWS if f"| `{name}` |" not in section]
    assert not missing, f"audit omits below-50% workflow disposition rows: {missing}"


def test_november_2026_audit_covers_50_80_band() -> None:
    text = AUDIT_REPORT.read_text(encoding="utf-8")
    section = _section_text(text, "## Workflows in the 50–80% band")
    missing = [name for name in BAND_50_80_WORKFLOWS if f"| `{name}` |" not in section]
    assert not missing, f"audit omits 50-80% band workflow disposition rows: {missing}"


def test_november_2026_audit_records_not_run_inventory() -> None:
    text = AUDIT_REPORT.read_text(encoding="utf-8")
    for bucket in (
        "workflow_call`-only",
        "reusable_call_only",
        "scheduled",
        "manual_utility",
        "event_driven",
    ):
        assert bucket in text, f"missing not-run bucket: {bucket!r}"


def test_november_2026_audit_t4_failure_inspection_section() -> None:
    text = AUDIT_REPORT.read_text(encoding="utf-8")
    section = _section_text(text, "## Failed run inspection")
    assert "gh run view" in section
    missing_rows = [
        name for name in T4_FAILURE_INSPECTION_WORKFLOWS if f"| `{name}` |" not in section
    ]
    assert not missing_rows, f"T4 inspection omits table rows: {missing_rows}"
    thin_rows = []
    for name in T4_FAILURE_INSPECTION_WORKFLOWS:
        for line in section.splitlines():
            if line.startswith(f"| `{name}` |"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) < 4 or not cells[2].strip() or not cells[3].strip():
                    thin_rows.append(name)
                break
        else:
            thin_rows.append(name)
    assert not thin_rows, f"T4 rows missing inspection evidence or disposition: {thin_rows}"
