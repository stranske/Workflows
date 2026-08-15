from pathlib import Path


def test_maint71_has_proof_bound_review_resolution_and_exact_evidence_promotion():
    workflow = Path(".github/workflows/maint-71-merge-sync-prs.yml").read_text()
    executor = Path(".github/scripts/maint71_merge_sync_prs.js").read_text()

    assert "review_resolution_json:" in workflow
    assert "github.event.client_payload.review_resolution_json" not in workflow
    assert "Apply proof-bound candidate review resolutions" in workflow
    assert 'RESOLUTION_ONLY_INPUT: "true"' in workflow
    assert "Validate complete pre-merge canary evidence" in workflow
    assert (
        "CANDIDATE_EVIDENCE_RESULT: ${{ steps.candidate_evidence_validation.outcome }}" in workflow
    )
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


def test_sync_lifecycle_chains_and_has_event_plus_timer_fallbacks():
    maint68 = Path(".github/workflows/maint-68-sync-consumer-repos.yml").read_text()
    maint82 = Path(".github/workflows/maint-82-sync-dependency-campaign.yml").read_text()
    followups = Path(
        "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
    ).read_text()

    assert "Start generated delivery reconciliation" in maint68
    assert "Canary evidence JSON (base64)" in maint68
    assert "activeSyncHash = phase === 'canary' ? 'candidate' : 'delivery'" in maint68
    assert 'cron: "*/10 * * * *"' in maint82
    assert "planMaint71Continuations" in maint82
    assert "Dispatch due Maint 71 continuations" in maint82
    assert "const selector = continuation.lane" in maint82
    assert "activeTitles.has('Merge Sync PRs [delivery]')" in maint82
    assert "Wake generated delivery reconciler" in followups
    assert "github.event.workflow_run.head_branch == 'sync/workflows-candidate'" in followups
    assert "event_type: 'merge-sync-prs'" in followups
    assert ": 'dev-tool';" in followups
