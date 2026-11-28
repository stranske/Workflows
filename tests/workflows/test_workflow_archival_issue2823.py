from __future__ import annotations

import pathlib

WORKFLOW_DIR = pathlib.Path(".github/workflows")
ARCHIVE_LEDGER_PATH = pathlib.Path("docs/archive/ARCHIVE_WORKFLOWS.md")


SUPERSEDED_WORKFLOWS = (
    "agent-watchdog.yml",
    "agents-40-consumer.yml",
    "agents-41-assign-and-watch.yml",
    "agents-41-assign.yml",
    "agents-42-watchdog.yml",
    "agents-44-copilot-readiness.yml",
    "agents-45-verify-codex-bootstrap-matrix.yml",
    "agents-47-verify-codex-bootstrap-matrix.yml",
    "agents-62-consumer.yml",
    "assign-to-agents.yml",
    "check-failure-tracker.yml",
    "ci-matrix-summary.yml",
    "ci-signature-guard.yml",
    "ci.yml",
    "docker.yml",
    "docs-only.yml",
    "gate.yml",
    "health-41-repo-health.yml",
    "health-43-ci-signature-guard.yml",
    "pr-status-summary.yml",
    "repo-health-nightly.yml",
    "repo-health-self-check.yml",
)


def test_superseded_workflows_absent_from_inventory() -> None:
    """Do not revive retired root workflows alongside their successors."""

    lingering = [name for name in SUPERSEDED_WORKFLOWS if (WORKFLOW_DIR / name).exists()]
    assert not lingering, f"Superseded workflows resurfaced: {lingering}"


def test_health43_archive_pins_exact_recovery_locator_and_digest() -> None:
    ledger = ARCHIVE_LEDGER_PATH.read_text(encoding="utf-8")
    section = ledger.split("### CI signature guard\n", 1)[1].split("\n### ", 1)[0]
    lines = section.splitlines()
    command = next(line for line in lines if line.startswith("git show "))
    checksum = next(line for line in lines if line.startswith("has SHA-256 ")).split("`")[1]

    assert command == (
        "git show 5fcd51d31705496c1d8d18d264dfce72767a1ba4:"
        ".github/workflows/health-43-ci-signature-guard.yml"
    )
    assert checksum == "d17dd0fc3785320ba919bd83b04f31fe772db623d33e687f68cf831d3a4fb70e"
