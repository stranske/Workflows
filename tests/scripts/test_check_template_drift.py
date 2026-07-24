from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_template_drift import (
    AllowlistEntry,
    TemplateDriftAllowlist,
    WorkflowPair,
    check_pairs,
    discover_workflow_pairs,
    drift_between,
    main,
    normalized_sha256,
    read_manifest_workflow_names,
)


def test_drift_between_false_for_identical_normalized_content() -> None:
    main = "name: Demo\r\njobs:\r\n  check: value  \r\n"
    template = "name: Demo\njobs:\n  check: value\n"

    assert drift_between(main, template) is False


def test_drift_between_detects_genuine_content_change() -> None:
    assert drift_between("jobs:\n  check: old\n", "jobs:\n  check: new\n") is True


def test_action_pin_sha_bump_is_not_drift() -> None:
    """A Renovate SHA bump on the same action must not read as drift.

    This is the recurrence Health 74 kept firing on: consumer templates SHA-pin
    actions, so every pin bump changed the fingerprint until a human re-baselined.
    """
    before = "    steps:\n      - uses: actions/checkout@9c091bb # v7.0.0\n"
    after = "    steps:\n      - uses: actions/checkout@3d3c42e # v7.0.1\n"
    assert drift_between(before, after) is False


def test_pinned_and_floating_action_refs_are_equivalent() -> None:
    """Root floats major tags; templates SHA-pin. That divergence is intentional
    and must not count as drift once pins are canonicalized."""
    floating = "      - uses: actions/checkout@v7\n"
    pinned = "      - uses: actions/checkout@3d3c42e5aac5ba8058 # v7.0.1\n"
    assert drift_between(floating, pinned) is False


def test_different_action_path_is_still_drift() -> None:
    """Only the @ref is canonicalized; swapping the action itself must still drift."""
    original = "      - uses: actions/checkout@v7\n"
    swapped = "      - uses: someone-else/checkout@v7\n"
    assert drift_between(original, swapped) is True


def test_reusable_workflow_ref_bump_is_not_drift_but_path_change_is() -> None:
    same_path_bump_a = "    uses: stranske/Workflows/.github/workflows/reusable-x.yml@main\n"
    same_path_bump_b = (
        "    uses: stranske/Workflows/.github/workflows/reusable-x.yml@abc123 # pin\n"
    )
    different_path = "    uses: stranske/Workflows/.github/workflows/reusable-y.yml@abc123 # pin\n"
    assert drift_between(same_path_bump_a, same_path_bump_b) is False
    assert drift_between(same_path_bump_a, different_path) is True


def test_genuine_logic_change_still_drifts_despite_pin_canonicalization() -> None:
    """Deliberate-break guard: canonicalizing pins must not mask real logic drift."""
    base = (
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "        if: github.event.action == 'labeled'\n"
    )
    broken = (
        "    steps:\n"
        "      - uses: actions/checkout@3d3c42e # v7.0.1\n"
        "        if: github.event.action == 'closed'\n"
    )
    # Same-action pin differs (ignored) but the `if:` logic differs (must drift).
    assert drift_between(base, broken) is True


def test_drift_between_honors_matching_fingerprinted_allowlist() -> None:
    main = "name: main\njobs:\n  check: true\n"
    template = "name: template\njobs:\n  check: true\n"
    allowlist = TemplateDriftAllowlist(
        (
            AllowlistEntry(
                main_path=".github/workflows/agents-demo.yml",
                template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
                main_sha256=normalized_sha256(main),
                template_sha256=normalized_sha256(template),
                reason="intentional baseline",
            ),
        )
    )

    assert (
        drift_between(
            main,
            template,
            allowlist,
            main_path=".github/workflows/agents-demo.yml",
            template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
        )
        is False
    )


def test_drift_between_rejects_stale_allowlist_fingerprint() -> None:
    main = "name: main\njobs:\n  check: true\n"
    template = "name: template\njobs:\n  check: true\n"
    stale_template = "name: template\njobs:\n  check: false\n"
    allowlist = TemplateDriftAllowlist(
        (
            AllowlistEntry(
                main_path=".github/workflows/agents-demo.yml",
                template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
                main_sha256=normalized_sha256(main),
                template_sha256=normalized_sha256(template),
                reason="intentional baseline",
            ),
        )
    )

    assert (
        drift_between(
            main,
            stale_template,
            allowlist,
            main_path=".github/workflows/agents-demo.yml",
            template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
        )
        is True
    )


def test_cli_fails_on_unallowlisted_agent_template_drift(tmp_path: Path) -> None:
    _write_pair(tmp_path, "agents-demo.yml", "one\n", "two\n")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "Unallowlisted Drift" in result.stdout
    assert "agents-demo.yml" in result.stdout


def test_cli_fails_when_agent_template_counterpart_is_missing(tmp_path: Path) -> None:
    main_path = tmp_path / ".github" / "workflows" / "agents-demo.yml"
    main_path.parent.mkdir(parents=True)
    main_path.write_text("name: demo\n", encoding="utf-8")
    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.write_text(
        "\n".join(
            [
                "version: 1",
                "workflows:",
                "  - source: .github/workflows/agents-demo.yml",
                "    description: Demo workflow",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "template counterpart is missing" in result.stdout
    assert "templates/consumer-repo/.github/workflows/agents-demo.yml" in result.stdout


def test_cli_passes_on_allowlisted_agent_template_drift(tmp_path: Path) -> None:
    main = "one\n"
    template = "two\n"
    _write_pair(tmp_path, "agents-demo.yml", main, template)
    allowlist = tmp_path / "config" / "template-drift-allowlist.txt"
    allowlist.parent.mkdir(parents=True)
    allowlist.write_text(
        "\n".join(
            [
                "[pair.demo]",
                "main = .github/workflows/agents-demo.yml",
                "template = templates/consumer-repo/.github/workflows/agents-demo.yml",
                f"main_sha256 = {normalized_sha256(main)}",
                f"template_sha256 = {normalized_sha256(template)}",
                "reason = intentional test baseline",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 0
    assert "allowlisted baseline drift: 1" in result.stdout


def test_main_empty_argv_ignores_process_argv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_template_drift.py",
            "--repo-root",
            str(tmp_path / "missing"),
        ],
    )

    assert main([]) == 0


def test_read_manifest_workflow_names_returns_empty_set_when_manifest_missing(
    tmp_path: Path,
) -> None:
    result = read_manifest_workflow_names(tmp_path)
    assert result == set()


def test_read_manifest_workflow_names_extracts_workflow_sources(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
version: 1
workflows:
  - source: .github/workflows/agents-issue-intake.yml
    description: Issue intake
  - source: .github/workflows/agents-80-pr-event-hub.yml
    description: PR event hub
  - source: .github/workflows/ci.yml
    description: CI workflow
""",
        encoding="utf-8",
    )

    result = read_manifest_workflow_names(tmp_path)
    assert result == {"agents-issue-intake.yml", "agents-80-pr-event-hub.yml", "ci.yml"}


def test_read_manifest_workflow_names_ignores_non_workflow_sources(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
version: 1
workflows:
  - source: .github/workflows/agents-demo.yml
    description: Agent demo
  - source: templates/consumer-repo/AGENTS.md
    description: Docs file
  - source: .github/CODEOWNERS
    description: Code owners
""",
        encoding="utf-8",
    )

    result = read_manifest_workflow_names(tmp_path)
    assert result == {"agents-demo.yml"}


def test_read_manifest_workflow_names_ignores_malformed_entries(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
version: 1
workflows:
  - source: .github/workflows/valid.yml
    description: Valid entry
  - "just a string"
  - 123
  - null
  -
    source: .github/workflows/another-valid.yml
""",
        encoding="utf-8",
    )

    result = read_manifest_workflow_names(tmp_path)
    assert result == {"valid.yml", "another-valid.yml"}


def test_read_manifest_workflow_names_ignores_missing_source(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
version: 1
workflows:
  - description: No source field
  - source: .github/workflows/has-source.yml
    description: Has source
  - source: ""
    description: Empty source
""",
        encoding="utf-8",
    )

    result = read_manifest_workflow_names(tmp_path)
    assert result == {"has-source.yml"}


def test_discover_workflow_pairs_uses_alias_mappings(tmp_path: Path) -> None:
    main_dir = tmp_path / ".github" / "workflows"
    template_dir = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows"
    main_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)

    main_workflow = main_dir / "agents-63-issue-intake.yml"
    template_workflow = template_dir / "agents-issue-intake.yml"
    main_workflow.write_text("name: main\n", encoding="utf-8")
    template_workflow.write_text("name: template\n", encoding="utf-8")

    pairs = discover_workflow_pairs(tmp_path)
    assert len(pairs) == 1
    assert pairs[0].main_path == main_dir / "agents-63-issue-intake.yml"
    assert pairs[0].template_path == template_dir / "agents-issue-intake.yml"


def test_discover_workflow_pairs_skips_non_manifested_workflows(tmp_path: Path) -> None:
    main_dir = tmp_path / ".github" / "workflows"
    template_dir = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows"
    main_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)

    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.write_text("version: 1\nworkflows: []\n", encoding="utf-8")

    non_manifested_workflow = main_dir / "agents-custom.yml"
    non_manifested_workflow.write_text("name: custom\n", encoding="utf-8")

    pairs = discover_workflow_pairs(tmp_path)
    assert len(pairs) == 0


def test_discover_workflow_pairs_includes_manifested_workflows(tmp_path: Path) -> None:
    main_dir = tmp_path / ".github" / "workflows"
    template_dir = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows"
    main_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)

    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.write_text(
        "version: 1\nworkflows:\n  - source: .github/workflows/agents-demo.yml\n",
        encoding="utf-8",
    )

    manifested_workflow = main_dir / "agents-demo.yml"
    template_workflow = template_dir / "agents-demo.yml"
    manifested_workflow.write_text("name: demo\n", encoding="utf-8")
    template_workflow.write_text("name: demo\n", encoding="utf-8")

    pairs = discover_workflow_pairs(tmp_path)
    assert len(pairs) == 1
    assert pairs[0].main_path == main_dir / "agents-demo.yml"
    assert pairs[0].template_path == template_dir / "agents-demo.yml"


def test_check_pairs_reports_missing_template_hash(tmp_path: Path) -> None:
    main_dir = tmp_path / ".github" / "workflows"
    template_dir = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows"
    main_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)

    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.write_text(
        "version: 1\nworkflows:\n  - source: .github/workflows/agents-demo.yml\n",
        encoding="utf-8",
    )

    main_workflow = main_dir / "agents-demo.yml"
    main_workflow.write_text("name: demo\n", encoding="utf-8")

    pairs = [WorkflowPair(main_workflow, template_dir / "agents-demo.yml")]
    allowlist = TemplateDriftAllowlist()

    results = check_pairs(tmp_path, pairs, allowlist)
    assert len(results) == 1
    assert results[0].status == "drift"
    assert results[0].template_sha256 == ""
    assert results[0].reason == "template counterpart is missing"


def test_check_pairs_reports_allowlisted_reason(tmp_path: Path) -> None:
    main_dir = tmp_path / ".github" / "workflows"
    template_dir = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows"
    main_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)

    main_workflow = main_dir / "agents-demo.yml"
    template_workflow = template_dir / "agents-demo.yml"
    main_text = "name: main\njobs:\n  check: true\n"
    template_text = "name: template\njobs:\n  check: true\n"
    main_workflow.write_text(main_text, encoding="utf-8")
    template_workflow.write_text(template_text, encoding="utf-8")

    allowlist = TemplateDriftAllowlist(
        (
            AllowlistEntry(
                main_path=".github/workflows/agents-demo.yml",
                template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
                main_sha256=normalized_sha256(main_text),
                template_sha256=normalized_sha256(template_text),
                reason="intentional baseline drift",
            ),
        )
    )

    pairs = [WorkflowPair(main_workflow, template_workflow)]
    results = check_pairs(tmp_path, pairs, allowlist)

    assert len(results) == 1
    assert results[0].status == "allowlisted"
    assert results[0].reason == "intentional baseline drift"
    assert results[0].main_sha256 == normalized_sha256(main_text)
    assert results[0].template_sha256 == normalized_sha256(template_text)


def test_check_pairs_reports_in_sync_status(tmp_path: Path) -> None:
    main_dir = tmp_path / ".github" / "workflows"
    template_dir = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows"
    main_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)

    main_workflow = main_dir / "agents-demo.yml"
    template_workflow = template_dir / "agents-demo.yml"
    content = "name: demo\n"
    main_workflow.write_text(content, encoding="utf-8")
    template_workflow.write_text(content, encoding="utf-8")

    pairs = [WorkflowPair(main_workflow, template_workflow)]
    allowlist = TemplateDriftAllowlist()

    results = check_pairs(tmp_path, pairs, allowlist)
    assert len(results) == 1
    assert results[0].status == "in_sync"
    assert results[0].reason == ""


def _write_pair(tmp_path: Path, filename: str, main: str, template: str) -> None:
    main_path = tmp_path / ".github" / "workflows" / filename
    template_path = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows" / filename
    main_path.parent.mkdir(parents=True)
    template_path.parent.mkdir(parents=True)
    main_path.write_text(main, encoding="utf-8")
    template_path.write_text(template, encoding="utf-8")


def _run_checker(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts" / "check_template_drift.py"),
            "--repo-root",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
