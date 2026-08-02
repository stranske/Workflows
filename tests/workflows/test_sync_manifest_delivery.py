"""Delivery-channel invariants for .github/sync-manifest.yml (issue #2347).

Background
----------
LangChain helper scripts were being delivered to consumer repos two ways at
once: copy-synced into the consumer tree by ``maint-68-sync-consumer-repos.yml``
*and* fetched at runtime by the consumer-template workflows that use them (which
sparse-checkout ``stranske/Workflows`` ``scripts/langchain`` as a whole directory
and run the script straight from that fetched tree). During the daily sync
window the two channels can disagree for ~30 minutes, a latent version skew.

Fix
---
Every LangChain manifest entry now carries a ``delivery:`` channel:

* ``copy``    -- physically copy-synced into the consumer tree and read from the
  consumer's own working directory at runtime.
* ``runtime`` -- NOT copy-synced; delivered only via the runtime sparse-checkout.

Entries marked ``runtime`` live in the dedicated ``runtime_fetched:`` section,
which is intentionally absent from the section lists processed by the sync
engine and the drift checker, so they are never copied and never drift-probed.

These tests assert the load-bearing invariant: **no manifest entry is both
``delivery: runtime`` and present in a copy-synced section** (that would
re-create the double delivery this issue removes).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "sync-manifest.yml"
SYNC_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml"
DRIFT_CHECK_PATH = REPO_ROOT / "scripts" / "check_consumer_sync_drift.py"

# Manifest sections whose entries are physically copied into consumer repos by
# maint-68-sync-consumer-repos.yml. Kept in lockstep with that workflow's
# add_target() loop and the per-section sync_file/sync_directory calls. The
# `runtime_fetched:` section is deliberately NOT in this set.
COPY_SYNCED_SECTIONS = (
    "workflows",
    "prompts",
    "scripts",
    "codex_config",
    "copilot_config",
    "templates",
    "actions",
    "docs",
    "llm_config",
    "git_config",
    "issue_templates",
    "user_docs",
)


def _load_manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}


def _sources_in_sections(manifest: dict, sections: tuple[str, ...]) -> set[str]:
    sources: set[str] = set()
    for section in sections:
        entries = manifest.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("source"):
                sources.add(str(entry["source"]))
    return sources


def _runtime_sources(manifest: dict) -> set[str]:
    sources: set[str] = set()
    for value in manifest.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            if (
                isinstance(entry, dict)
                and entry.get("delivery") == "runtime"
                and entry.get("source")
            ):
                sources.add(str(entry["source"]))
    return sources


def test_no_entry_is_both_runtime_and_copy_synced() -> None:
    """The crux invariant: a runtime-delivered entry must not also be copy-synced."""
    manifest = _load_manifest()
    copy_sources = _sources_in_sections(manifest, COPY_SYNCED_SECTIONS)
    runtime_sources = _runtime_sources(manifest)

    double_delivered = sorted(copy_sources & runtime_sources)
    assert not double_delivered, (
        "These entries are delivery: runtime but still present in a copy-synced "
        f"section (double delivery, the skew this issue removes): {double_delivered}"
    )


def test_followup_issue_generator_is_runtime_only() -> None:
    """The proven runtime-fetched langchain script is dropped from copy-sync.

    followup_issue_generator.py is invoked only from a runtime sparse-checkout of
    scripts/langchain in agents-80-pr-event-hub.yml and agents-verify-to-new-pr.yml
    (both check out stranske/Workflows into the workspace root with no `path:`).
    No consumer-delivered workflow reads it from the copy-synced tree.
    """
    manifest = _load_manifest()
    source = "scripts/langchain/followup_issue_generator.py"

    copy_sources = _sources_in_sections(manifest, COPY_SYNCED_SECTIONS)
    assert source not in copy_sources, f"{source} must not be copy-synced"

    runtime_entries = {
        e["source"]: e
        for e in (manifest.get("runtime_fetched") or [])
        if isinstance(e, dict) and e.get("source")
    }
    assert source in runtime_entries, f"{source} must be declared under runtime_fetched:"
    assert runtime_entries[source].get("delivery") == "runtime"


def test_copy_dependent_langchain_scripts_stay_copy_synced() -> None:
    """Regression guard against an over-aggressive future drop.

    agents-auto-pilot.yml runs issue_formatter.py / issue_optimizer.py from the
    consumer's own working tree (it does NOT runtime-fetch scripts/langchain), and
    issue_optimizer.py imports scripts.langchain.structured_output. These three
    must remain copy-synced or auto-pilot breaks in consumers.
    """
    manifest = _load_manifest()
    copy_sources = _sources_in_sections(manifest, COPY_SYNCED_SECTIONS)
    for required in (
        "scripts/langchain/issue_formatter.py",
        "scripts/langchain/issue_optimizer.py",
        "scripts/langchain/structured_output.py",
    ):
        assert required in copy_sources, (
            f"{required} is a copy-path dependency of agents-auto-pilot.yml and "
            "must stay in a copy-synced section"
        )


def test_langchain_client_registry_dependency_stays_copy_synced() -> None:
    """The copy-synced LangChain client imports tools.llm_registry in consumers."""
    manifest = _load_manifest()
    copy_sources = _sources_in_sections(manifest, COPY_SYNCED_SECTIONS)

    assert "tools/langchain_client.py" in copy_sources
    assert "tools/llm_registry.py" in copy_sources


def test_all_langchain_entries_have_a_delivery_channel() -> None:
    """Every scripts/langchain/* entry must declare its delivery channel."""
    manifest = _load_manifest()
    missing: list[str] = []
    for value in manifest.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            if not isinstance(entry, dict):
                continue
            source = str(entry.get("source", ""))
            if source.startswith("scripts/langchain/") and entry.get("delivery") not in {
                "copy",
                "runtime",
            }:
                missing.append(source)
    assert (
        not missing
    ), f"scripts/langchain/* entries missing a delivery: channel: {sorted(missing)}"


def test_runtime_fetched_section_is_not_copy_processed() -> None:
    """`runtime_fetched` must not be wired into the sync engine or drift checker.

    If a future change adds `runtime_fetched` to either consumer of the section
    list, entries here would start being copied/drift-probed -- re-introducing the
    double delivery. This test fails loudly in that case.
    """
    sync_text = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")
    drift_text = DRIFT_CHECK_PATH.read_text(encoding="utf-8")
    assert (
        "runtime_fetched" not in sync_text
    ), "maint-68 must not process the runtime_fetched section (would copy-deliver it)"
    assert (
        "runtime_fetched" not in drift_text
    ), "check_consumer_sync_drift must not probe the runtime_fetched section"


def test_prepare_checkout_includes_manifest_owned_github_roots() -> None:
    """Maint-68 must hash root-owned manifest sources, not stale template copies."""
    workflow = yaml.safe_load(SYNC_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["prepare"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout")
    sparse_checkout = checkout["with"]["sparse-checkout"]

    # The registry is owned at the Workflows root even though a consumer template
    # copy also exists. Without this root, the manifest compiler silently reads
    # the stale template copy during a sync run.
    assert ".github/agents" in sparse_checkout
    assert ".gitattributes" in {
        line.strip() for line in sparse_checkout.splitlines() if line.strip()
    }


def test_sync_fanout_is_canary_gated_and_promotion_is_plan_bound() -> None:
    workflow = yaml.safe_load(SYNC_WORKFLOW_PATH.read_text(encoding="utf-8"))
    dispatch_inputs = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
    prepare = workflow["jobs"]["prepare"]
    sync = workflow["jobs"]["sync"]
    source = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert dispatch_inputs["phase"]["default"] == "canary"
    assert set(dispatch_inputs["phase"]["options"]) == {"preview", "canary", "promote"}
    assert "canary_evidence_json" in dispatch_inputs
    assert prepare["outputs"]["phase"] == "${{ steps.repos.outputs.phase }}"
    assert sync["if"] == "needs.prepare.outputs.phase != 'preview'"
    assert "select_consumer_sync_phase.py" in source
    upload = next(
        step for step in prepare["steps"] if step.get("uses") == "actions/upload-artifact@v7"
    )
    download = next(
        step for step in sync["steps"] if step.get("uses") == "actions/download-artifact@v8"
    )
    assert upload["with"]["name"] == "sync-plan-and-prospective-diffs"
    assert download["with"]["name"] == upload["with"]["name"]

    config = json.loads((REPO_ROOT / "config" / "consumer_sync_canaries.json").read_text())
    assert config["schema"] == "workflows.consumer-sync-canaries/v1"
    assert 2 <= len(config["canaries"]) <= 3


def test_maint_71_emits_canary_evidence_with_review_debt() -> None:
    source = (REPO_ROOT / ".github" / "workflows" / "maint-71-merge-sync-prs.yml").read_text(
        encoding="utf-8"
    )

    assert "sync-canary-evidence.json" in source
    assert "active_review_thread_count" in source
    assert "required_check_state" in source
    assert "plan_id" in source


def test_maint68_refreshes_only_a_same_base_and_tree_delivery_attempt() -> None:
    """A current generation reuses its PR; a changed base/tree must be replaced safely."""
    source = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")

    credential_idx = source.index('git config credential.helper "$credential_helper"')
    fetch_idx = source.index('git fetch origin "$branch_name"')
    assert credential_idx < fetch_idx

    assert 'git fetch origin "$branch_name"' in source
    assert 'existing_base=$(git rev-parse "${existing_head}^")' in source
    assert 'existing_tree=$(git rev-parse "${existing_head}^{tree}")' in source
    assert "desired_tree_hash=$(git write-tree)" in source
    assert "existing_refreshable=false" in source
    assert "parseDeliveryRecord" in source
    assert "mergeEligibility" in source
    assert "status=existing_pr_not_refreshable" in source
    assert '[ "$existing_refreshable" = "true" ]' in source
    assert '[ "$existing_base" = "$base_sha" ]' in source
    assert '[ "$existing_tree" = "$desired_tree_hash" ]' in source
    assert "matching_existing=true" in source
    commit_push_guard = source.index('if [ "$matching_existing" != "true" ]; then')
    assert (
        source.index(
            'git commit -m "chore: sync workflow templates from Workflows repo', commit_push_guard
        )
        > commit_push_guard
    )
    assert (
        source.index(
            'git push --quiet --force-with-lease="refs/heads/$branch_name:$existing_head"',
            commit_push_guard,
        )
        > commit_push_guard
    )
