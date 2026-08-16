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
REUSABLE_AUTOFIX_PATH = REPO_ROOT / ".github" / "workflows" / "reusable-18-autofix.yml"
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


def test_consumer_gitattributes_preserves_windows_launcher_crlf() -> None:
    """The template-owned attributes must retain native Windows line endings."""
    consumer_gitattributes = (
        REPO_ROOT / "templates" / "consumer-repo" / ".gitattributes"
    ).read_text(encoding="utf-8")

    assert "*.cmd text eol=crlf" in consumer_gitattributes.splitlines()


def test_sync_fanout_is_canary_gated_and_promotion_is_plan_bound() -> None:
    workflow = yaml.safe_load(SYNC_WORKFLOW_PATH.read_text(encoding="utf-8"))
    dispatch_inputs = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
    prepare = workflow["jobs"]["prepare"]
    sync = workflow["jobs"]["sync"]
    continuation = workflow["jobs"]["continue-delivery"]
    source = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert dispatch_inputs["phase"]["default"] == "canary"
    assert set(dispatch_inputs["phase"]["options"]) == {"preview", "canary", "promote"}
    assert "canary_evidence_json" in dispatch_inputs
    assert set(dispatch_inputs["delivery_scope"]["options"]) == {
        "auto",
        "full",
        "source-delta",
    }
    assert "scope_base_sha" in dispatch_inputs
    assert "scope_head_sha" in dispatch_inputs
    assert prepare["outputs"]["phase"] == "${{ steps.repos.outputs.phase }}"
    assert prepare["outputs"]["sync_branch"] == "${{ steps.repos.outputs.sync_branch }}"
    assert prepare["outputs"]["has_plan_items"] == "${{ steps.manifest.outputs.has_plan_items }}"
    assert sync["if"] == (
        "needs.prepare.outputs.phase != 'preview' && "
        "needs.prepare.outputs.has_plan_items == 'true'"
    )
    assert "scope_consumer_sync_plan.py" in source
    assert "Validate immutable source reachability" in source
    assert 'git merge-base --is-ancestor "$SOURCE_COMMIT" "$GITHUB_SHA"' in source
    assert "Consumer-sync plan ID: $PLAN_ID" in source
    assert "Source commit: $PLAN_SOURCE_COMMIT" in source
    assert "select_consumer_sync_phase.py" in source
    assert 'sync_branch="sync/workflows-candidate"' in source
    assert 'sync_branch="sync/workflows-delivery"' in source
    assert "const branchName = process.env.SYNC_BRANCH;" in source
    assert 'branch_name="$SYNC_BRANCH"' in source
    assert "stable_plan_rotation" in source
    assert "expectedStableBranch" in source
    assert "--draft" in source
    assert "sync:delivery-staging" in source
    assert "sync:delivery-ready" in source
    continuation_names = [step.get("name") for step in continuation["steps"]]
    assert "Build exact no-change canary evidence" in continuation_names
    assert "Record exact consumer base" in [step.get("name") for step in sync["steps"]]
    assert "immutable_handoff_json: JSON.stringify({" in source
    assert "plan_id: process.env.PLAN_ID" in source
    assert "source_commit: process.env.SOURCE_COMMIT" in source
    assert "canary_baseline_evidence_json" in source
    assert '"consumer_head_sha": os.environ.get("CONSUMER_HEAD_SHA", "")' in source
    assert "autofix: false" in source
    reusable_autofix = REUSABLE_AUTOFIX_PATH.read_text(encoding="utf-8")
    assert '[[ "$head_ref" == sync/workflows-* ]]' in reusable_autofix
    assert "generated sync PR is Maint 71-owned" in reusable_autofix
    assert "release" not in workflow.get("on", workflow.get(True))
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
    # Canary evidence fields live in the externalized Maint 71 executor JS;
    # the workflow only uploads the artifact path.
    workflow = (REPO_ROOT / ".github" / "workflows" / "maint-71-merge-sync-prs.yml").read_text(
        encoding="utf-8"
    )
    executor = (REPO_ROOT / ".github" / "scripts" / "maint71_merge_sync_prs.js").read_text(
        encoding="utf-8"
    )
    assert "sync-canary-evidence.json" in workflow
    assert "active_review_thread_count" in executor
    assert "required_check_state" in executor
    assert "plan_id" in executor


def test_maint_71_persists_validated_candidate_evidence_before_merge() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "maint-71-merge-sync-prs.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    dispatch_inputs = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
    steps = workflow["jobs"]["merge_sync_prs"]["steps"]
    names = [step.get("name") for step in steps]

    assert "active_sync_hash" in dispatch_inputs
    assert "immutable_handoff_json" in dispatch_inputs
    assert "canary_baseline_evidence_json" in dispatch_inputs
    assert "sync_hash" not in dispatch_inputs
    resolve_index = names.index("Resolve immutable handoff inputs")
    candidate_mode_index = names.index("Resolve candidate evidence mode")
    assert resolve_index < candidate_mode_index
    collect_index = names.index("Collect and validate canary evidence before merge")
    persist_index = names.index("Persist pre-merge canary evidence")
    merge_index = names.index("Check and merge sync PRs")
    authorize_index = names.index("Authorize exact-head fleet commit")
    campaign_commit_index = names.index("Commit prepared sync campaign")
    assert resolve_index < collect_index < persist_index < merge_index
    assert merge_index < authorize_index < campaign_commit_index
    assert steps[persist_index]["with"]["name"] == "sync-canary-evidence-premerge"
    assert steps[persist_index]["with"]["if-no-files-found"] == "error"
    merge_condition = steps[merge_index]["if"]
    assert "steps.repos.outcome == 'success'" in merge_condition
    assert "steps.candidate_mode.outcome == 'success'" in merge_condition

    source = workflow_path.read_text(encoding="utf-8")
    assert 'AUTO_MERGE_INPUT: "false"' in source
    assert 'EVIDENCE_ONLY_INPUT: "true"' in source
    assert "ACTIVE_SYNC_HASH_INPUT" in source
    assert "github.event.client_payload.active_sync_hash" in source
    assert "github.event.client_payload.sync_hash" in source
    assert "CANDIDATE_EVIDENCE_AUTHORIZED" in source
    assert "steps.candidate_evidence_validation.outputs.authorized" in source
    assert "CANDIDATE_ARTIFACT_RESULT" in source
    assert "sync-campaign-commit-authorization.json" in source
    assert "EXPECTED_PLAN_ID_INPUT" in source
    assert "EXPECTED_SOURCE_COMMIT_INPUT" in source
    assert "CANARY_BASELINE_EVIDENCE_JSON" in source
    assert "actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3" in source
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source


def test_maint68_reuses_stable_delivery_pr_without_resetting_an_unchanged_head() -> None:
    """Stable PRs retain review state unless Maint 68 actually changes the head."""
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
    assert '[ "$existing_verified" = "true" ]' in source
    assert "matching_existing=true" in source
    assert "migrating_legacy_lifecycle=true" in source
    assert "migrating its legacy metadata into the staged delivery lifecycle" in source
    assert "preserving its review lifecycle" in source
    assert "delivery_state=$(jq -r" in source
    assert 'current_pr_json=$(gh pr view "$existing_pr" --json state,headRefOid,isDraft)' in source
    assert 'gh pr merge "$existing_pr" --disable-auto' in source
    assert 'gh pr ready "$existing_pr" --undo' in source
    assert '--force-with-lease="refs/heads/$branch_name:$existing_head"' in source
    assert source.count("--json number,headRefName,isCrossRepository") == 2
    assert source.count(".isCrossRepository == false") == 2
    commit_push_guard = source.index('if [ "$matching_existing" != "true" ]; then')
    assert (
        source.index(
            "create_signed_sync_commit.js",
            commit_push_guard,
        )
        > commit_push_guard
    )
    assert "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3" in source
    assert "permission-contents: write" in source
    assert "permission-workflows: write" in source
    assert "gh api" not in source
    assert 'git config user.name "github-actions[bot]"' not in source
    assert "published_verified=$(jq -r" in source
    assert "published_reason=$(jq -r" in source
    assert 'head_observed_sha="$signed_commit_sha"' in source
    assert "head_observed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" in source
    assert '--arg head_observed_sha "$head_observed_sha"' in source
    assert '--arg head_observed_at "$head_observed_at"' in source
    assert (
        source.index(
            '--force-with-lease="refs/heads/$branch_name:$existing_head"',
            commit_push_guard,
        )
        > commit_push_guard
    )


def test_maint71_anchors_review_window_to_producer_head_observation() -> None:
    source = Path(".github/scripts/maint71_merge_sync_prs.js").read_text(encoding="utf-8")

    assert "selection.deliveryRecord?.head_observed_sha === pr.head.sha" in source
    assert "selection.deliveryRecord.head_observed_at" in source
    assert "observed_sha: pr?.head?.observed_sha" in source
    assert "observed_at: pr?.head?.observed_at" in source
    assert "selectedHeadCommit?.committer?.date" not in source


def test_gate_and_shared_mergers_hold_mutable_stable_deliveries() -> None:
    gate = (REPO_ROOT / ".github" / "workflows" / "pr-00-gate.yml").read_text(encoding="utf-8")
    template_gate = (
        REPO_ROOT / "templates" / "consumer-repo" / ".github" / "workflows" / "pr-00-gate.yml"
    ).read_text(encoding="utf-8")
    seal_action = (
        REPO_ROOT / ".github" / "actions" / "generated-delivery-seal" / "action.yml"
    ).read_text(encoding="utf-8")
    seal_check = (
        REPO_ROOT / ".github" / "actions" / "generated-delivery-seal" / "check.js"
    ).read_text(encoding="utf-8")
    gate_summary = (REPO_ROOT / ".github" / "scripts" / "gate_summary.py").read_text(
        encoding="utf-8"
    )
    merger_guard = (REPO_ROOT / ".github" / "scripts" / "runtime_ac_merge_guard.js").read_text(
        encoding="utf-8"
    )

    assert "generated-delivery-seal" in gate
    action_ref = (
        "stranske/Workflows/.github/actions/generated-delivery-seal"
        "@632eb20586f8403219d101e8a982b62efeb94104"
    )
    assert action_ref in gate
    assert action_ref in template_gate
    assert (
        "uses: ./.github/actions/path-classifier"
        not in gate.split("generated-delivery-seal:", 1)[1].split("\n  python-ci:", 1)[0]
    )
    assert "using: composite" in seal_action
    assert "requireSealed: true" in seal_check
    assert "pullRequest?.head?.sha" in seal_check
    assert "DELIVERY_SEAL_RESULT" in gate
    assert "sync/workflows-delivery" in gate_summary
    assert "sealed_head_sha" in gate_summary
    assert "sync:delivery-staging" in merger_guard
    assert "allowSealedSyncDelivery" in merger_guard


def test_delivery_lease_contract_is_copy_synced_with_the_gate() -> None:
    manifest = _load_manifest()
    copy_sources = _sources_in_sections(manifest, COPY_SYNCED_SECTIONS)
    source = ".github/scripts/sync_pr_lease_contract.js"

    assert source in copy_sources
    assert (REPO_ROOT / "templates" / "consumer-repo" / source).read_bytes() == (
        REPO_ROOT / source
    ).read_bytes()
