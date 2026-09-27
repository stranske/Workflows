import re
import threading
from pathlib import Path


def _top_level_concurrency(source: str) -> tuple[str, str]:
    match = re.search(
        r"^concurrency:\n"
        r"  group: (?P<group>[^\n]+)\n"
        r"  cancel-in-progress: (?P<cancel>[^\n]+)$",
        source,
        flags=re.MULTILINE,
    )
    assert match, "workflow must declare the stable-PR writer concurrency contract"
    assert "queue:" not in source, "workflow must use supported concurrency syntax"
    return match.group("group"), match.group("cancel")


def test_maint68_and_maint71_serialize_stable_pr_writers_across_final_read_patch_window():
    maint68 = Path(".github/workflows/maint-68-sync-consumer-repos.yml").read_text()
    maint71 = Path(".github/workflows/maint-71-merge-sync-prs.yml").read_text()
    maint68_group, maint68_cancel = _top_level_concurrency(maint68)
    maint71_group, maint71_cancel = _top_level_concurrency(maint71)

    expected_group = "consumer-sync-stable-pr-writers-${{ github.repository }}"
    assert maint68_group == maint71_group == expected_group
    assert maint68_cancel == maint71_cancel == "false"
    for partition in (
        "github.workflow",
        "github.ref",
        "active_sync_hash",
        "sync_hash",
        "phase",
        "plan",
        "generation",
        "head",
    ):
        assert partition not in maint68_group
        assert partition not in maint71_group

    # Model GitHub's repository-scoped concurrency semantics with the group
    # parsed from production YAML. Maint 68 is queued precisely after Maint 71's
    # final identity read; it must not reach its read/write section until Maint
    # 71 releases the shared group after PATCH.
    locks: dict[str, threading.Lock] = {}
    final_read = threading.Event()
    release_maint71 = threading.Event()
    maint68_attempting = threading.Event()
    maint68_mutated = threading.Event()

    def group_lock(group: str) -> threading.Lock:
        return locks.setdefault(group, threading.Lock())

    def maint71_writer() -> None:
        with group_lock(maint71_group):
            final_read.set()
            assert release_maint71.wait(timeout=2)

    def maint68_writer() -> None:
        assert final_read.wait(timeout=2)
        maint68_attempting.set()
        with group_lock(maint68_group):
            maint68_mutated.set()

    lifecycle = threading.Thread(target=maint71_writer)
    refresh = threading.Thread(target=maint68_writer)
    lifecycle.start()
    refresh.start()
    assert maint68_attempting.wait(timeout=2)
    assert not maint68_mutated.wait(timeout=0.05)
    release_maint71.set()
    lifecycle.join(timeout=2)
    refresh.join(timeout=2)
    assert not lifecycle.is_alive()
    assert not refresh.is_alive()
    assert maint68_mutated.is_set()

    actionlint_allowlist = Path(".github/actionlint-allowlist.txt").read_text()
    assert 'unexpected key "queue" for "concurrency" section' not in actionlint_allowlist


def test_stable_writer_concurrency_documents_pending_replacement_and_replay():
    maintenance_guide = Path("docs/ops/CONSUMER_REPO_MAINTENANCE.md").read_text()
    topology_guide = Path("docs/ci/WORKFLOWS.md").read_text()
    maint82 = Path(".github/workflows/maint-82-sync-dependency-campaign.yml").read_text()

    assert "at most one pending run" in maintenance_guide
    assert "mutual exclusion, not a lossless" in maintenance_guide
    assert "rerun" in maintenance_guide
    assert "the original normal selector with the same immutable inputs" in maintenance_guide
    assert "persisted transient handoffs" in maintenance_guide
    assert "not a lossless cross-workflow queue" in topology_guide
    assert "consumer-sync-stable-pr-writers-${{ github.repository }}" in topology_guide
    assert "planMaint71Continuations" in maint82
    assert "Dispatch due Maint 71 continuations" in maint82


def test_maint71_has_proof_bound_review_resolution_and_exact_evidence_promotion():
    workflow = Path(".github/workflows/maint-71-merge-sync-prs.yml").read_text()
    executor = Path(".github/scripts/maint71_merge_sync_prs.js").read_text()
    maintenance_guide = Path("docs/ops/CONSUMER_REPO_MAINTENANCE.md").read_text()
    campaign_contract = Path("docs/ops/SYNC_DEPENDENCY_CAMPAIGN.md").read_text()

    assert "review_resolution_json:" in workflow
    assert "github.event.client_payload.review_resolution_json" not in workflow
    assert "Apply proof-bound candidate review resolutions" in workflow
    assert 'RESOLUTION_ONLY_INPUT: "true"' in workflow
    assert "Validate complete pre-merge canary evidence" in workflow
    assert "CANDIDATE_EVIDENCE_AUTHORIZED:" in workflow
    assert "steps.candidate_evidence_validation.outputs.authorized" in workflow
    assert "steps.candidate_evidence_validation.outputs.authorized == 'true'" in workflow
    assert "PREPARE_ONLY_INPUT:" in workflow
    assert "CAMPAIGN_COMMIT_AUTHORIZATION_JSON:" in workflow
    assert "Authorize exact-head fleet commit" in workflow
    assert "Commit prepared sync campaign" in workflow
    assert "dryRun && !resolutionOnly" in executor
    assert "workflows-sync-review-resolution/v1" in executor
    assert "resolveReviewThread" in executor
    assert "source_fix_not_in_delivery_source" in executor
    assert "candidatePromotionDecision" in workflow
    assert "candidateRefreshDecision" in workflow
    assert "deliveryRefreshDecision" in workflow
    assert "Refresh stale candidate bases" in workflow
    assert "Refresh stale delivery bases" in workflow
    assert "phase: 'canary'" in workflow
    assert "delivery_scope: 'full'" in workflow
    assert "canary_evidence_json: JSON.stringify(evidence)" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "EXCLUDED_REPOS_INPUT: stranske/Collab-Admin" in workflow
    assert "MANUAL_RECONCILIATION_REPOS_INPUT: stranske/Collab-Admin" in workflow
    assert "selectReconciliationTargets" in executor
    for document in (maintenance_guide, campaign_contract):
        assert "repos=stranske/Collab-Admin" in document
        assert "active_sync_hash=delivery" in document
        assert "workflow_dispatch" in document
    assert "['candidate', 'campaign', 'delivery', 'dev-tool']" in workflow
    assert "/^[0-9a-f]{12,64}$/i.test(selector)" in workflow
    assert "active sync selector must be candidate, campaign, delivery, dev-tool, " in workflow
    assert "'stale_closed'" in workflow
    assert "paginateWithRetry(api.rest.actions.listWorkflowRuns" in workflow
    assert "Maint 71 requires OWNER_PR_PAT" in executor
    assert "retryHelpers.withRetry(fn" in executor
    assert "createTokenAwareRetry" in executor
    assert "const withReviewReadRetry" in executor
    assert "const withRetry = (fn, options = {}) => retryHelpers.withRetry" in executor
    assert "sha: pr.head.sha" in executor
    assert workflow.count("github-token: ${{ secrets.OWNER_PR_PAT }}") == 5


def test_maint71_reviewer_reassessment_is_trusted_request_only_dispatch():
    workflow = Path(".github/workflows/maint-71-merge-sync-prs.yml").read_text()
    executor = Path(".github/scripts/maint71_merge_sync_prs.js").read_text()
    policy = Path("config/consumer_sync_review_policy.json").read_text()
    guide = Path("docs/ops/CONSUMER_REPO_MAINTENANCE.md").read_text()

    assert "types: [merge-sync-prs, maint71-review-reassessment]" in workflow
    assert "github.event.action != 'maint71-review-reassessment'" in workflow
    assert "github.event.client_payload.review_reassessment_json" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "ref: main" in workflow
    assert "runReviewReassessment" in workflow
    assert "maint71-review-reassessment-${{ github.repository }}" in workflow
    assert "Never rotate a cross-repository read/comment onto GITHUB_TOKEN" in workflow
    assert "maint71-review-reassessment/v1" in executor
    assert "client.rest.issues.createComment" in executor
    assert '"reassessment_comment": "@codex review"' in policy
    assert '"reassessment_comment": "@coderabbitai full review"' in policy
    assert "A reviewer request is not itself thread acceptance" in guide


def test_sync_lifecycle_chains_and_has_event_plus_timer_fallbacks():
    maint68 = Path(".github/workflows/maint-68-sync-consumer-repos.yml").read_text()
    maint82 = Path(".github/workflows/maint-82-sync-dependency-campaign.yml").read_text()
    followups = Path(
        "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
    ).read_text()

    assert "Start generated delivery reconciliation" in maint68
    assert "Canary evidence JSON (base64)" in maint68
    assert "activeSyncHash = phase === 'canary' ? 'candidate' : 'campaign'" in maint68
    assert 'cron: "*/10 * * * *"' in maint82
    assert "planMaint71Continuations" in maint82
    assert "Dispatch due Maint 71 continuations" in maint82
    assert "const selector = continuation.lane" in maint82
    assert "value.startsWith('Merge Sync PRs [delivery]')" in maint82
    assert "continuation_key" in maint82
    assert "immutable_handoff_json" in maint82
    assert "Wake generated delivery reconciler" in followups
    assert "github.event.workflow_run.head_branch == 'sync/workflows-candidate'" in followups
    assert "event_type: 'merge-sync-prs'" in followups
    assert ": 'dev-tool';" in followups


def test_maint68_holds_stable_generation_when_a_legacy_sync_pr_is_open():
    maint68 = Path(".github/workflows/maint-68-sync-consumer-repos.yml").read_text()

    assert "const legacyInFlight = await isConsumerOpenPr" in maint68
    assert "!exists && await isConsumerOpenPr" not in maint68
    assert "/^sync\\/workflows-[0-9a-f]{12}$/i" in maint68
    assert "legacy_in_flight" in maint68
    assert "must reach terminal disposition before migration" in maint68
    assert "steps.open_pr.outputs.legacy_in_flight != 'true'" in maint68
    assert 'elif legacy_in_flight:\n              status = "legacy_hold"' in maint68
    assert "Stop reconciliation when a legacy sync PR holds generation" in maint68
    assert r"present=${held.length ? 'true' : 'false'}\n" in maint68
    assert r"present=${held.length ? 'true' : 'false'}\\n" not in maint68
    assert "steps.legacy_hold.outputs.present != 'true'" in maint68
    assert "steps.sync.outcome == 'success' && inputs.dry_run != true" in maint68
