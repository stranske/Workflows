from pathlib import Path

import yaml
from scripts.sync_manifest_compiler import compile_manifest

GUIDE = Path("templates/consumer-repo/docs/CI_SYSTEM_GUIDE.md")


def test_consumer_ci_guide_matches_current_agent_entrypoints() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert text.count("agents-80-pr-event-hub.yml") == 1

    for current_surface in (
        "agents-issue-intake.yml",
        "agents-71-codex-belt-dispatcher.yml",
        "agents-72-codex-belt-worker-dispatch.yml",
        "agents-80-pr-event-hub.yml",
        "agents-81-gate-followups.yml",
        "agents-verifier.yml",
    ):
        assert current_surface in text

    for retired_claim in (
        "Agents 63 Issue Intake",
        "Agents 70 Orchestrator",
        "Agents 71-73 Codex Belt",
        "Conveyor merges",
    ):
        assert retired_claim not in text

    assert "Bootstrap creates ready branch + PR" in text
    assert "guarded exact-head closer" in text
    assert "same head for at least seven minutes" in text
    assert "active non-outdated review threads" in text
    assert "bound to the validated head SHA" in text


def test_consumer_operator_docs_match_gate_followup_topology() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    root_labels = Path("docs/LABELS.md").read_text(encoding="utf-8")
    setup = Path("templates/consumer-repo/docs/SETUP_CHECKLIST.md").read_text(encoding="utf-8")
    compiled = compile_manifest(repo_root / ".github/sync-manifest.yml", repo_root=repo_root)
    labels_entry = next(
        entry for entry in compiled.section("docs") if entry.target == "docs/LABELS.md"
    )
    gate_followups_entry = next(
        entry
        for entry in compiled.section("workflows")
        if entry.target == ".github/workflows/agents-81-gate-followups.yml"
    )
    assert labels_entry.source_tree == "template"
    assert gate_followups_entry.source_tree == "template"
    labels = (repo_root / labels_entry.resolved_source).read_text(encoding="utf-8")
    gate_followups = yaml.safe_load(
        (repo_root / gate_followups_entry.resolved_source).read_text(encoding="utf-8")
    )
    jobs = gate_followups["jobs"]

    assert "Root/non-consolidated: sets `force_retry=true`" in root_labels
    assert ".github/workflows/agents-keepalive-loop.yml" in root_labels
    for retired_surface in (
        "agents-63-issue-intake.yml",
        "agents-70-orchestrator.yml",
    ):
        assert retired_surface not in labels

    for agent, display_name in (("cursor", "Cursor"), ("gemini", "Gemini")):
        job_id = f"run-{agent}"
        job = jobs[job_id]
        assert job["uses"] == f"stranske/Workflows/.github/workflows/reusable-{agent}-run.yml@main"
        expected_condition = " ".join(
            (
                f"needs.evaluate.outputs.agent_type == '{agent}' &&",
                "needs.evaluate.outputs.dispatch_should_run == 'true' &&",
                "(needs.evaluate.outputs.action == 'run' ||",
                "needs.evaluate.outputs.action == 'fix' ||",
                "needs.evaluate.outputs.action == 'conflict')",
            )
        )
        assert " ".join(job["if"].split()) == expected_condition

        section_start = labels.index(f"### `agent:{agent}`")
        section_end = labels.index("\n---", section_start)
        label_section = labels[section_start:section_end]
        assert (
            f"| `agent:{agent}` | Issue or PR labeled | "
            f"Routes consumer Gate-followup keepalive to the {display_name} runner"
        ) in labels
        assert f"On PRs, dispatches the `{job_id}` consumer keepalive job" in label_section
        assert f"On PRs, `agents-81-gate-followups.yml` dispatches `reusable-{agent}-run.yml`" in (
            label_section
        )
    assert "applying the label does not trigger a retry by itself" in labels
    assert "Does not set `force_retry`" in labels
    assert "agents-keepalive-loop.yml" not in labels
    assert "agents-pr-meta-v4.yml" not in labels
    assert "Optional recovery-request marker" in setup
    assert "USE_CONSOLIDATED_WORKFLOWS` is `true`" in setup
    assert "cleared by Agents 81 after it successfully merges" in labels
