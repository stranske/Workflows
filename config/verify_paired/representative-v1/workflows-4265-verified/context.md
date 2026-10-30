# Verifier context

## Context source coverage

```json
{"schema": "verifier-context-source-coverage/v1", "stage": "generated-context", "changed_code_sources": [{"source": ".github/sync-manifest.yml", "status": "included", "included_chars": 77897, "total_chars": 77897}, {"source": ".github/workflows/maint-coverage-guard.yml", "status": "included", "included_chars": 30663, "total_chars": 30663}, {"source": "config/template-drift-allowlist.txt", "status": "included", "included_chars": 57512, "total_chars": 57512}, {"source": "docs/INTEGRATION_GUIDE.md", "status": "included", "included_chars": 65488, "total_chars": 65488}, {"source": "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml", "status": "included", "included_chars": 31015, "total_chars": 31015}, {"source": "tests/test_coverage_guard.py", "status": "included", "included_chars": 54200, "total_chars": 54200}, {"source": "tests/workflows/test_maint_coverage_guard_artifacts.py", "status": "included", "included_chars": 2679, "total_chars": 2679}, {"source": "tools/coverage_guard.py", "status": "included", "included_chars": 26653, "total_chars": 26653}], "acceptance_sources": [{"source": "https://github.com/stranske/Workflows/issues/4254", "status": "included", "included_chars": 4027, "total_chars": 4027}], "acceptance_evidence_sources": [{"source": "evidence/EVIDENCE_INDEX.json", "status": "included", "included_chars": 2788, "total_chars": 2788}, {"source": "evidence/broken.junit.xml", "status": "included", "included_chars": 11175, "total_chars": 11175}, {"source": "evidence/broken.pytest.log", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/current-review-runner.py", "status": "included", "included_chars": 5280, "total_chars": 5280}, {"source": "evidence/mutation.patch", "status": "included", "included_chars": 456, "total_chars": 456}, {"source": "evidence/original-two-named-tests.stderr", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/original-two-named-tests.stdout", "status": "included", "included_chars": 98, "total_chars": 98}, {"source": "evidence/original.junit.xml", "status": "included", "included_chars": 1538, "total_chars": 1538}, {"source": "evidence/original.pytest.log", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/receipt.json", "status": "included", "included_chars": 8218, "total_chars": 8218}, {"source": "evidence/removed-current-append.stderr", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/removed-current-append.stdout", "status": "included", "included_chars": 12803, "total_chars": 12803}, {"source": "evidence/restored-two-named-tests.stderr", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/restored-two-named-tests.stdout", "status": "included", "included_chars": 98, "total_chars": 98}, {"source": "evidence/restored.junit.xml", "status": "included", "included_chars": 1538, "total_chars": 1538}, {"source": "evidence/restored.pytest.log", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/sandbox-and-runtime-probe.stderr", "status": "included", "included_chars": 0, "total_chars": 0}, {"source": "evidence/sandbox-and-runtime-probe.stdout", "status": "included", "included_chars": 218, "total_chars": 218}, {"source": "evidence/sandbox.sb", "status": "included", "included_chars": 213, "total_chars": 213}, {"source": "evidence/setup-attempt-1-receipt.json", "status": "included", "included_chars": 2490, "total_chars": 2490}, {"source": "evidence/setup-attempt-2-receipt.json", "status": "included", "included_chars": 2554, "total_chars": 2554}, {"source": "evidence/setup-attempt-3-receipt.json", "status": "included", "included_chars": 4406, "total_chars": 4406}], "acceptance_source_discovery": {"required": false, "status": "included"}, "full_diff_artifact": {"source": "verifier-pr-diff.patch", "status": "included", "chars": 31667}}
```

## CI Information
Current reviewer verification is supplied below: the two original named tests pass (9 parametrized cases), removing only the current-history sample produces 5 assertion failures, and exact-byte restoration returns all 9 cases to passing. This is current reviewer execution against the original PR head, not a claim about what the PR author historically ran. No hosted CI or whole-suite execution is supplied.

## Plan sources (scope, tasks, acceptance)
Original public Issue https://github.com/stranske/Workflows/issues/4254 (current retrieved original-issue body, not PR outcome summary). PR https://github.com/stranske/Workflows/pull/4265 explicitly closes this issue.

#### Acceptance criteria
## Why (verified evidence)
The Maint Coverage Guard closes a baseline-breach issue only when the last `recovery_days` (default 3) history records are all at or above the baseline: `tools/coverage_guard.py:593` returns `False` when `len(records) < recovery_window`. The history it reads is the `gate-coverage-trend-history` artifact of ONE Gate run, and that artifact only ever holds one record: nothing restores the previous history before the append (`.github/workflows/reusable-10-ci-python.yml:3002-3010` appends to a workspace file that starts empty; `scripts/coverage_history_append.py:53` loads whatever exists, which is nothing), and the guard downloads it under a run-id-scoped cache key (`.github/workflows/maint-coverage-guard.yml:425`, `cache-key-base: gate-coverage-trend-history-${{ steps.discover.outputs.run_id }}`), so no earlier record can ever be restored. While `recovery_days` is above 1 the window cannot be satisfied.
- The five newest `gate-coverage-trend-history` artifacts of stranske/Workflows (ids 12609676623 to 12614843725, 2026-10-25 18:36 to 21:53 UTC): the two read (12614843725 and 12614304625) hold exactly 1 NDJSON record each.
- The guard's own log, run 40171029582 (2026-10-25 07:00Z): "Coverage 90.88% meets baseline 85.00% - no open issue needed", then "Coverage recovered, but configured recovery window is not satisfied; leaving any breach issue open".
- Workflows #4011 "[coverage] baseline breach" (opened 2026-10-17, 83.17% against a baseline of 85.0) is still open and has had no update since 2026-10-18, although the guard succeeded on all 8 daily runs since 10-18 and read 90.88%, almost six points above the baseline.
- Across the account the guard has filed 3 breach issues in a year (search `"baseline breach" in:title user:stranske`): Trend #2933 (open 2025-10-23 to 2026-05-25, 214 days), Orchestrator #180 (2026-08-31 to 2026-09-04) and Workflows #4011 (open, 8 days and counting). The long gaps are what a window that cannot fill produces: a person closes them.
The consequence is a gate whose clear path (N consecutive records) is fed by a source that holds one: every breach issue the guard opens stays open until someone closes it by hand.

## Tasks
- [ ] `.github/workflows/maint-coverage-guard.yml:425`: make the history cache key repository-scoped instead of producer-run-scoped, with a restore prefix, so the previous guard run's accumulated history is restored before the check.
- [ ] `tools/coverage_guard.py:593` (`_recovery_window_satisfied`) and its caller near `:763`: before the check, append the current trend record to the restored history (replacing a record with the same run id), keep at most 30 records, and write the file back so the cache saves it.
- [ ] `tools/coverage_guard.py:763`: say in the message how many records the window holds and how many it needs, for example "recovered, 2 of 3 records at or above the baseline".

## Acceptance Criteria
- Named test: `tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs`: a restored history of two records at or above the baseline plus the current record satisfies a 3-record window; the current record alone does not; the same run id is not counted twice.
- Deliberate-break → revert: remove the append of the current record to the restored history, confirm the named test FAILS, then revert.
- Named test: `tests/test_coverage_guard.py::test_recovery_message_names_records_held_and_needed` asserts the "N of M records" text.

## Non-Goals
- Do NOT change any baseline value, `warn_drop`, the `recovery_days` default or any repository's coverage floor.
- Do NOT make the guard block anything: it stays a report that files and closes one issue.
- No scaffolding / TODO-only changes; every task is a concrete edit verified by the tests above.

_Surfaced by the coverage autopilot's fleet watch (2026-10-25) while checking the daily guard as a second signal; verified from the artifact contents, the guard's log and the files at the cited lines of main@2f66049fd4._


## PR Diff Summary
- Files changed: 8
- Base: 8f3b249871a134e1caf39be4e63a6c9fac990c23
- Head: 40622701645e1c9c13ff28861ba606a3f78d2e4a

### File changes
- .github/sync-manifest.yml
- .github/workflows/maint-coverage-guard.yml
- config/template-drift-allowlist.txt
- docs/INTEGRATION_GUIDE.md
- templates/consumer-repo/.github/workflows/maint-coverage-guard.yml
- tests/test_coverage_guard.py
- tests/workflows/test_maint_coverage_guard_artifacts.py
- tools/coverage_guard.py

## PR Diff (full)

```diff
diff --git a/.github/sync-manifest.yml b/.github/sync-manifest.yml
index 9acaab031ebd3af0f3b5d7d211659ff481a5c1b1..6ce0aa93248f09902f851117db012e1d6275e052 100644
--- a/.github/sync-manifest.yml
+++ b/.github/sync-manifest.yml
@@ -163,7 +163,7 @@ workflows:
 
   # Maintenance workflows
   - source: .github/workflows/maint-coverage-guard.yml
-    description: "Coverage guard - daily baseline monitoring with automatic issue creation. Intentional full-workflow sync exception: ships the complete guard implementation to consumers instead of a thin reusable caller because the workflow embeds repo-specific artifact discovery and download logic tied to tools/coverage_guard.py."
+    description: "Coverage guard - daily baseline monitoring with automatic issue creation and repository-scoped recovery history. Intentional full-workflow sync exception: ships the complete guard implementation to consumers instead of a thin reusable caller because the workflow embeds repo-specific artifact discovery and download logic tied to tools/coverage_guard.py."
 
   - source: .github/workflows/maint-76-claude-code-review.yml
     description: "Claude Code review (opt-in) - Workflows owns the pinned action digest; runs only on labeled PRs or manual dispatch"
diff --git a/.github/workflows/maint-coverage-guard.yml b/.github/workflows/maint-coverage-guard.yml
index e6727a50b180dd50f21bc8e613168d70f9387639..7e488240ee4350740cf72492a29a971b97ec7bfd 100644
--- a/.github/workflows/maint-coverage-guard.yml
+++ b/.github/workflows/maint-coverage-guard.yml
@@ -417,17 +417,17 @@ jobs:
           producer-run-id: ${{ steps.discover.outputs.run_id }}
           fail-fast: 'true'
 
-      - name: Download coverage trend history artifact
-        if: ${{ steps.discover.outputs.history_artifact_name }}
+      # Each immutable cache saves the accumulated history after this guard run.
+      # Restore the newest repository history, independently of the producer run.
+      - name: Restore coverage recovery history
+        if: ${{ steps.discover.outputs.run_id }}
         id: coverage-trend-history-cache
-        uses: ./.github/actions/artifact-cache
+        uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
         with:
-          cache-key-base: gate-coverage-trend-history-${{ steps.discover.outputs.run_id }}
-          window-resolution: weekly
-          artifact-name: ${{ steps.discover.outputs.history_artifact_name }}
-          artifact-path: coverage_artifacts/history
-          producer-run-id: ${{ steps.discover.outputs.run_id }}
-          fail-fast: 'false'
+          path: coverage_artifacts/history
+          key: coverage-guard-history-v1-${{ github.repository }}-${{ github.run_id }}-${{ github.run_attempt }}
+          restore-keys: |
+            coverage-guard-history-v1-${{ github.repository }}-
 
       - name: Download coverage payload artifact
         if: ${{ steps.discover.outputs.coverage_artifact_name }}
@@ -451,7 +451,7 @@ jobs:
           # Try multiple possible artifact paths (workflow uses different naming)
           TREND_PATH=""
           COVERAGE_PATH=""
-          HISTORY_PATH=""
+          HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"
 
           # Check for trend artifact
           for candidate in \
@@ -551,6 +551,13 @@ jobs:
 
           python tools/coverage_guard.py "${ARGS[@]}"
 
+      - name: Save coverage recovery history
+        if: ${{ always() && steps.discover.outputs.run_id && hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson') != '' }}
+        uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
+        with:
+          path: coverage_artifacts/history
+          key: ${{ steps.coverage-trend-history-cache.outputs.cache-primary-key }}
+
   # A SKIPPED GUARD USED TO BE INDISTINGUISHABLE FROM A PASSING ONE. `guard` is gated on the
   # rate-limit job, so when quota is low the job is skipped and the WORKFLOW IS GREEN with nothing
   # checked. stranske/Workflows' three most recent runs all read `success` at the workflow level
diff --git a/config/template-drift-allowlist.txt b/config/template-drift-allowlist.txt
index a14ef39468407608ab95918be2ff86a74f23f595..7a8e1d5fb0a77adff2328d55196b6ceb8a5953f1 100644
--- a/config/template-drift-allowlist.txt
+++ b/config/template-drift-allowlist.txt
@@ -216,11 +216,11 @@ fingerprint_refreshed = 2026-09-14
 [pair.18]
 main = .github/workflows/maint-coverage-guard.yml
 template = templates/consumer-repo/.github/workflows/maint-coverage-guard.yml
-main_sha256 = e91eb88457e15bef38dec493824c131dceff87c3d95bdbde4c1ae0b7edee59f3
-template_sha256 = 8578fcb7859d06bf7f458f54faaffa275c59f5888d3875e936ddcb09a59a928a
-divergence = Round 2 Python matrix 2026-10-17: runtime/coverage changes applied identically to root and template; existing consumer wiring and action-pin divergence unchanged. Guard FINDS the report inside the artifact 2026-08-30, AND CORRECTS THE CLAIM BELOW. The note that follows says matrix artifacts extract to `payload/coverage/runtimes/...`. They do not, and that is why the seven hardcoded candidate paths still matched nothing after the artifact NAME was fixed the same day. MEASURED by downloading three repos' real gate-coverage-3.12-1 artifacts (stranske/Counter_Risk, stranske/Pension-Data, stranske/trip-planner): every one contains `index.ndjson` and `runtimes/<ver>/coverage.json` with NO top-level `coverage/` directory, so the extracted path is `coverage_artifacts/payload/runtimes/3.12/coverage.json` -- one level from the first candidate and matched by none. The list also hardcoded Python 3.12/3.13, so a matrix bump would break it silently and later. Literals are still tried FIRST, so a repo where resolution already worked cannot be re-resolved by this change; failing that the payload is FOUND by the property the guard actually reads -- a JSON carrying totals.percent_covered -- which cannot drift from a directory layout it never mentions, and which correctly rejects the `summary.json` sibling that carries a `coverage` key but no totals. Results are sorted, so an artifact holding two runtimes resolves identically every run. The missing-artifact message now lists what was downloaded, because it could not distinguish an empty artifact from a full one whose contents it did not recognise -- and the second is what really happened, in every repo. Applied IDENTICALLY to root and consumer; fingerprints refreshed, divergence_reviewed keeps its date. Prior divergence unchanged: Review findings fixed 2026-08-30: matrix artifacts downloaded under payload extract to `payload/coverage/runtimes/...`, so both guards probe that actual layout before legacy layouts; the three failure states now separately report no coverage artifacts, unusable payload names, and a usable payload missing its same-run trend. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Guard matches the payload artifact by PREFIX 2026-08-30: the producer runs under a version matrix, so what it publishes is gate-coverage-3.12-1 and gate-coverage-3.13-1, while this job matched the exact names gate-coverage / gate-coverage.json. MEASURED 2026-08-30 across the lane fleet: EIGHT repos published a trend, a summary and both suffixed payloads -- everything the job needs -- and every one was skipped, which is why the guard had a failing run in all 13 repos. Two more literals would not have fixed it, so the match is by prefix with -trend/-summary/-delta excluded by name (a bare prefix would have selected the TREND as the payload and compared coverage against itself); exact names are still preferred first so a repo where this already worked is untouched, and multiple suffixed matches are SORTED because the API's listing order is not stable. The failure message was split into three findings, because "coverage is not measured here", "it is measured under a name I cannot use" and "a payload but no trend" have different fixes and the single message asserted the first in all three cases -- it told eight measuring repos to go and switch coverage on. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Guard reads a per-repo workflow list 2026-08-30: which workflow carries a repo's coverage is a PER-REPO fact and was hardcoded to pr-00-gate.yml, so two repos were invisible to the guard for the same reason and neither is misconfigured -- stranske/Counter_Risk measures coverage on ci.yml by documented judgement, and stranske/Orchestrator publishes its only honest figure (80.3% combined, against the 34.11% its Gate reports for pytest alone) from a ci.yml job, because 79 of its 102 modules run under --selftest subprocesses pytest-cov cannot see. Reading source_workflows from config/coverage-baseline.json puts the answer in the file that is already the per-repo coverage config and already excluded from sync. The default is exactly the previous behaviour and an unreadable config falls back to it, so no repo changes unless it opts in. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed for it and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Coverage guard fingerprint refreshed 2026-08-26: both root and consumer selectors now recognize the downloaded `coverage_artifacts/payload/gate-coverage.json` filename, preventing the source/template artifact-name mismatch from hiding usable Gate coverage. The remaining root/template differences are still intentional: consumers use pinned public actions and an App token while Workflows uses local artifact-cache helpers and sparse checkout. Prior divergence unchanged: Coverage guard re-reviewed 2026-08-25: both selectors require the trend artifact alongside the coverage payload, because coverage_guard.py makes a missing trend a successful no-op. Checkout 2026-10-16: the root guard job dropped its second, sparse 'Checkout retry helpers' step, which deleted tools/coverage_guard.py before 'Run coverage guard' ran (the guard could not measure for 20+ days); the template already had a single full checkout, so this change reduces the divergence. Fingerprints refreshed; the existing divergence and its review date are unchanged.
+main_sha256 = da0d24f4739dd2a6e4d9df70b4a0edf418bb6e1e8667fe3137fe84302559cfea
+template_sha256 = 0aafdbd27b50b1116c724e90d870ef04a558f5403bdd76601c36bfda02cbff87
+divergence = Recovery history 2026-10-26: identical repository-scoped restore/save and default history-path changes applied to both surfaces; consumer App tokens, pinned actions and artifact downloads remain unchanged. Fingerprints refreshed only; original divergence review date retained. Prior divergence unchanged: Round 2 Python matrix 2026-10-17: runtime/coverage changes applied identically to root and template; existing consumer wiring and action-pin divergence unchanged. Guard FINDS the report inside the artifact 2026-08-30, AND CORRECTS THE CLAIM BELOW. The note that follows says matrix artifacts extract to `payload/coverage/runtimes/...`. They do not, and that is why the seven hardcoded candidate paths still matched nothing after the artifact NAME was fixed the same day. MEASURED by downloading three repos' real gate-coverage-3.12-1 artifacts (stranske/Counter_Risk, stranske/Pension-Data, stranske/trip-planner): every one contains `index.ndjson` and `runtimes/<ver>/coverage.json` with NO top-level `coverage/` directory, so the extracted path is `coverage_artifacts/payload/runtimes/3.12/coverage.json` -- one level from the first candidate and matched by none. The list also hardcoded Python 3.12/3.13, so a matrix bump would break it silently and later. Literals are still tried FIRST, so a repo where resolution already worked cannot be re-resolved by this change; failing that the payload is FOUND by the property the guard actually reads -- a JSON carrying totals.percent_covered -- which cannot drift from a directory layout it never mentions, and which correctly rejects the `summary.json` sibling that carries a `coverage` key but no totals. Results are sorted, so an artifact holding two runtimes resolves identically every run. The missing-artifact message now lists what was downloaded, because it could not distinguish an empty artifact from a full one whose contents it did not recognise -- and the second is what really happened, in every repo. Applied IDENTICALLY to root and consumer; fingerprints refreshed, divergence_reviewed keeps its date. Prior divergence unchanged: Review findings fixed 2026-08-30: matrix artifacts downloaded under payload extract to `payload/coverage/runtimes/...`, so both guards probe that actual layout before legacy layouts; the three failure states now separately report no coverage artifacts, unusable payload names, and a usable payload missing its same-run trend. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Guard matches the payload artifact by PREFIX 2026-08-30: the producer runs under a version matrix, so what it publishes is gate-coverage-3.12-1 and gate-coverage-3.13-1, while this job matched the exact names gate-coverage / gate-coverage.json. MEASURED 2026-08-30 across the lane fleet: EIGHT repos published a trend, a summary and both suffixed payloads -- everything the job needs -- and every one was skipped, which is why the guard had a failing run in all 13 repos. Two more literals would not have fixed it, so the match is by prefix with -trend/-summary/-delta excluded by name (a bare prefix would have selected the TREND as the payload and compared coverage against itself); exact names are still preferred first so a repo where this already worked is untouched, and multiple suffixed matches are SORTED because the API's listing order is not stable. The failure message was split into three findings, because "coverage is not measured here", "it is measured under a name I cannot use" and "a payload but no trend" have different fixes and the single message asserted the first in all three cases -- it told eight measuring repos to go and switch coverage on. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Guard reads a per-repo workflow list 2026-08-30: which workflow carries a repo's coverage is a PER-REPO fact and was hardcoded to pr-00-gate.yml, so two repos were invisible to the guard for the same reason and neither is misconfigured -- stranske/Counter_Risk measures coverage on ci.yml by documented judgement, and stranske/Orchestrator publishes its only honest figure (80.3% combined, against the 34.11% its Gate reports for pytest alone) from a ci.yml job, because 79 of its 102 modules run under --selftest subprocesses pytest-cov cannot see. Reading source_workflows from config/coverage-baseline.json puts the answer in the file that is already the per-repo coverage config and already excluded from sync. The default is exactly the previous behaviour and an unreadable config falls back to it, so no repo changes unless it opts in. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed for it and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Coverage guard fingerprint refreshed 2026-08-26: both root and consumer selectors now recognize the downloaded `coverage_artifacts/payload/gate-coverage.json` filename, preventing the source/template artifact-name mismatch from hiding usable Gate coverage. The remaining root/template differences are still intentional: consumers use pinned public actions and an App token while Workflows uses local artifact-cache helpers and sparse checkout. Prior divergence unchanged: Coverage guard re-reviewed 2026-08-25: both selectors require the trend artifact alongside the coverage payload, because coverage_guard.py makes a missing trend a successful no-op. Checkout 2026-10-16: the root guard job dropped its second, sparse 'Checkout retry helpers' step, which deleted tools/coverage_guard.py before 'Run coverage guard' ran (the guard could not measure for 20+ days); the template already had a single full checkout, so this change reduces the divergence. Fingerprints refreshed; the existing divergence and its review date are unchanged.
 divergence_reviewed = 2026-08-25
-fingerprint_refreshed = 2026-10-16
+fingerprint_refreshed = 2026-10-26
 
 [pair.19]
 main = .github/workflows/pr-00-gate.yml
diff --git a/docs/INTEGRATION_GUIDE.md b/docs/INTEGRATION_GUIDE.md
index b909417baa2e09de93764d3bc0a36605eb79f9fd..1abea1478c0eaad5e0351c318e886029bb7b5da7 100644
--- a/docs/INTEGRATION_GUIDE.md
+++ b/docs/INTEGRATION_GUIDE.md
@@ -636,6 +636,12 @@ breach issue closes only after coverage reaches `baseline - warn_drop` for the
 configured `recovery_days` consecutive samples (default `3`). The warning allowance
 changes the recovery threshold, not the default confirmation window.
 
+The guard restores repository-scoped recovery history, appends the current producer
+run (replacing a repeated run identity), and retains at most 30 records. It saves a
+new immutable cache after each guard run; a repository restore prefix carries the
+records across different Gate producers. An incomplete recovery reports how many
+of the required records meet the threshold. Dry runs do not persist history.
+
 **Soft vs Hard Gate:**
 
 - **Soft gate** (`enable-soft-gate: true`): Reports coverage but doesn't fail the build
diff --git a/templates/consumer-repo/.github/workflows/maint-coverage-guard.yml b/templates/consumer-repo/.github/workflows/maint-coverage-guard.yml
index ced480b0f2d4acb3e9e2fb21c1221985dd5f99b7..338a6d1fd9c3d5e7e06aaf529ffcec8c967de937 100644
--- a/templates/consumer-repo/.github/workflows/maint-coverage-guard.yml
+++ b/templates/consumer-repo/.github/workflows/maint-coverage-guard.yml
@@ -429,15 +429,17 @@ jobs:
           path: coverage_artifacts/trend
           github-token: ${{ secrets.GITHUB_TOKEN }}
 
-      - name: Download coverage trend history artifact
-        if: ${{ steps.discover.outputs.history_artifact_name }}
-        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8
-        continue-on-error: true
+      # Each immutable cache saves the accumulated history after this guard run.
+      # Restore the newest repository history, independently of the producer run.
+      - name: Restore coverage recovery history
+        if: ${{ steps.discover.outputs.run_id }}
+        id: coverage-trend-history-cache
+        uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
         with:
-          name: ${{ steps.discover.outputs.history_artifact_name }}
-          run-id: ${{ steps.discover.outputs.run_id }}
           path: coverage_artifacts/history
-          github-token: ${{ secrets.GITHUB_TOKEN }}
+          key: coverage-guard-history-v1-${{ github.repository }}-${{ github.run_id }}-${{ github.run_attempt }}
+          restore-keys: |
+            coverage-guard-history-v1-${{ github.repository }}-
 
       - name: Download coverage payload artifact
         if: ${{ steps.discover.outputs.coverage_artifact_name }}
@@ -458,7 +460,7 @@ jobs:
           # Try multiple possible artifact paths (workflow uses different naming)
           TREND_PATH=""
           COVERAGE_PATH=""
-          HISTORY_PATH=""
+          HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"
 
           # Check for trend artifact
           for candidate in \
@@ -558,6 +560,14 @@ jobs:
 
           python tools/coverage_guard.py "${ARGS[@]}"
 
+      - name: Save coverage recovery history
+        if: ${{ always() && steps.discover.outputs.run_id && hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson') != '' }}
+        uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
+        with:
+          path: coverage_artifacts/history
+          key: ${{ steps.coverage-trend-history-cache.outputs.cache-primary-key }}
+
+
   # A SKIPPED GUARD USED TO BE INDISTINGUISHABLE FROM A PASSING ONE. `guard` is gated on the
   # rate-limit job, so when quota is low the job is skipped and the WORKFLOW IS GREEN with nothing
   # checked. stranske/Workflows' three most recent runs all read `success` at the workflow level
diff --git a/tests/test_coverage_guard.py b/tests/test_coverage_guard.py
index 8f0a00ac3034a15f1e11528e37b24644898b943a..ff6bfeb12e7bb19bd120d14b2d44b6079b68ffd6 100644
--- a/tests/test_coverage_guard.py
+++ b/tests/test_coverage_guard.py
@@ -8,6 +8,12 @@ import pytest
 from tools import coverage_guard
 
 
+@pytest.fixture(autouse=True)
+def isolate_guard_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
+    """Default-path CLI calls must not share persisted samples between tests."""
+    monkeypatch.chdir(tmp_path)
+
+
 def _write_json(path: Path, payload: dict) -> None:
     path.write_text(json.dumps(payload), encoding="utf-8")
 
@@ -778,6 +784,113 @@ def test_recovery_window_counts_same_coverage_from_distinct_runs() -> None:
     )
 
 
+@pytest.mark.parametrize(
+    "restored_run_ids",
+    [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
+    ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
+)
+def test_recovery_window_counts_records_accumulated_across_runs(
+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
+) -> None:
+    """Restored runs accumulate while retries replace stale samples without inflating the window."""
+    trend_path = tmp_path / "trend.json"
+    baseline_path = tmp_path / "baseline.json"
+    history_path = tmp_path / "history.ndjson"
+    _write_json(trend_path, {"current": 90.0, "run_id": "3"})
+    _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
+    history_path.write_text(
+        "\n".join(
+            json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
+            for run_id in restored_run_ids
+        ),
+        encoding="utf-8",
+    )
+    closed = []
+    monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
+    args = [
+        "--repo",
+        "octo/repo",
+        "--trend-path",
+        str(trend_path),
+        "--baseline-path",
+        str(baseline_path),
+        "--history-path",
+        str(history_path),
+    ]
+    assert coverage_guard.main(args) == 0
+    assert len(closed) == 1
+    assert [r["run_id"] for r in coverage_guard._load_ndjson(history_path)] == ["1", "2", "3"]
+    assert coverage_guard._load_ndjson(history_path)[-1]["current"] == 90.0
+    # Retrying the same Gate run cannot supply another recovery sample.
+    assert coverage_guard.main(args) == 0
+    assert len(coverage_guard._load_ndjson(history_path)) == 3
+    history_path.unlink()
+    closed.clear()
+    assert coverage_guard.main(args) == 0
+    assert not closed
+    assert len(coverage_guard._load_ndjson(history_path)) == 1
+    assert coverage_guard.main(args) == 0
+    assert not closed
+    assert len(coverage_guard._load_ndjson(history_path)) == 1
+
+
+@pytest.mark.parametrize(
+    ("restored_coverage", "recovered_records"),
+    [((90.0,), 2), ((80.0,), 1), ((90.0, 90.0, 80.0), 2), ((), 1)],
+    ids=["two-recovered", "one-below-baseline", "latest-window-only", "current-alone"],
+)
+def test_recovery_message_names_records_held_and_needed(
+    tmp_path: Path,
+    monkeypatch: pytest.MonkeyPatch,
+    capsys: pytest.CaptureFixture[str],
+    restored_coverage: tuple[float, ...],
+    recovered_records: int,
+) -> None:
+    """Progress names the qualifying records within the latest window and the required size."""
+    trend_path = tmp_path / "trend.json"
+    baseline_path = tmp_path / "baseline.json"
+    history_path = tmp_path / "history.ndjson"
+    _write_json(trend_path, {"current": 90.0, "run_id": str(len(restored_coverage) + 1)})
+    _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
+    history_path.write_text(
+        "\n".join(
+            json.dumps({"current": current, "run_id": str(n)})
+            for n, current in enumerate(restored_coverage, start=1)
+        ),
+        encoding="utf-8",
+    )
+    monkeypatch.setattr(
+        coverage_guard, "_close_existing_issue", lambda *a, **kw: pytest.fail("premature closure")
+    )
+    assert (
+        coverage_guard.main(
+            [
+                "--repo",
+                "octo/repo",
+                "--trend-path",
+                str(trend_path),
+                "--baseline-path",
+                str(baseline_path),
+                "--history-path",
+                str(history_path),
+            ]
+        )
+        == 0
+    )
+    assert f"{recovered_records} of 3 records at or above the baseline" in capsys.readouterr().out
+
+
+def test_recovery_history_retains_latest_thirty_unique_runs() -> None:
+    history = [{"current": 90.0, "run_id": str(n)} for n in range(35)]
+    history.insert(0, {"current": 80.0, "run_id": "34"})
+    records = coverage_guard._accumulate_recovery_history(
+        {"current": 91.0, "run_id": "34"}, history, ""
+    )
+    assert len(records) == 30
+    assert [r["run_id"] for r in records] == [str(n) for n in range(5, 35)]
+    assert records[-1]["current"] == 91.0
+
+
 def test_recovery_window_accepts_aggregate_history_records() -> None:
     trend_data = {"current": 72.0, "run_id": "run-3"}
     history_records = [
diff --git a/tests/workflows/test_maint_coverage_guard_artifacts.py b/tests/workflows/test_maint_coverage_guard_artifacts.py
index f9d68cbe1d1aa7bef4c7662bdaa1a04208e843b8..b176b91b19a43308ff81c95273676e8391b5595b 100644
--- a/tests/workflows/test_maint_coverage_guard_artifacts.py
+++ b/tests/workflows/test_maint_coverage_guard_artifacts.py
@@ -3,6 +3,7 @@
 from pathlib import Path
 
 import pytest
+import yaml
 
 
 @pytest.mark.parametrize(
@@ -25,3 +26,31 @@ def test_coverage_guard_selects_only_runs_with_payload_and_trend(workflow_path:
     assert workflow.count("published coverage artifact names did not match") == 1
     assert workflow.count("coverage payloads were published without ${trendArtifactName}") == 1
     assert '"coverage_artifacts/payload/gate-coverage.json"' in workflow
+
+
+@pytest.mark.parametrize(
+    "workflow_path",
+    [
+        ".github/workflows/maint-coverage-guard.yml",
+        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
+    ],
+)
+def test_recovery_cache_survives_producer_runs_and_saves_after_guard(workflow_path: str) -> None:
+    steps = yaml.safe_load(Path(workflow_path).read_text())["jobs"]["guard"]["steps"]
+    restore = next(s for s in steps if s.get("id") == "coverage-trend-history-cache")
+    guard = next(s for s in steps if s.get("name") == "Run coverage guard")
+    save = next(s for s in steps if s.get("name") == "Save coverage recovery history")
+    assert steps.index(restore) < steps.index(guard) < steps.index(save)
+    assert restore["uses"].startswith("actions/cache/restore@")
+    assert save["uses"].startswith("actions/cache/save@")
+    assert restore["with"]["path"] == save["with"]["path"] == "coverage_artifacts/history"
+    assert "github.repository" in restore["with"]["key"]
+    assert "github.run_id" in restore["with"]["key"]
+    assert "github.run_attempt" in restore["with"]["key"]
+    assert "discover.outputs.run_id" not in restore["with"]["key"]
+    prefix = restore["with"]["restore-keys"].strip()
+    assert "github.repository" in prefix and "run_id" not in prefix
+    assert restore["with"]["key"].startswith(prefix)
+    assert 'HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"' in guard["run"]
+    assert "cache-primary-key" in save["with"]["key"]
+    assert "hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson')" in save["if"]
diff --git a/tools/coverage_guard.py b/tools/coverage_guard.py
index ed7251efa929791d36288dde3216c86e42a4d8c1..6ce725e48749884d2ef81094a69e3b466b594a32 100755
--- a/tools/coverage_guard.py
+++ b/tools/coverage_guard.py
@@ -609,6 +609,27 @@ def _coverage_record_key(record: dict[str, Any]) -> tuple[str, str | float | Non
     return ("coverage", _coverage_value_for_recovery(record))
 
 
+def _accumulate_recovery_history(
+    trend_data: dict[str, Any], history_records: list[dict[str, Any]] | None, run_url: str
+) -> list[dict[str, Any]]:
+    """Retain up to 30 samples, replacing repeated producer-run identities."""
+    previous = history_records if history_records is not None else trend_data.get("history", [])
+    sample = {key: value for key, value in trend_data.items() if key != "history"}
+    if run_url:
+        sample.setdefault("run_url", run_url)
+    records: list[dict[str, Any]] = []
+    for record in [*(previous if isinstance(previous, list) else []), sample]:
+        if not isinstance(record, dict):
+            continue
+        key = _coverage_record_key(record)
+        if key[0] != "coverage":
+            records = [item for item in records if _coverage_record_key(item) != key]
+        elif record is sample and records and _coverage_record_key(records[-1]) == key:
+            records.pop()
+        records.append(record)
+    return records[-30:]
+
+
 def main(args: list[str] | None = None) -> int:
     """Main entry point for coverage guard."""
     parser = argparse.ArgumentParser(description="Coverage guard - maintain baseline breach issues")
@@ -732,6 +753,12 @@ def main(args: list[str] | None = None) -> int:
         print(body)
         return 0
 
+    history_records = _accumulate_recovery_history(trend_data, history_records, parsed.run_url)
+    parsed.history_path.parent.mkdir(parents=True, exist_ok=True)
+    parsed.history_path.write_text(
+        "".join(json.dumps(record) + "\n" for record in history_records), encoding="utf-8"
+    )
+
     # Create or update issue
     if is_coverage_breach(current, baseline, warn_drop):
         try:
@@ -754,13 +781,21 @@ def main(args: list[str] | None = None) -> int:
             print(f"Coverage {current:.2f}% meets baseline {baseline:.2f}% - no open issue needed")
         recovery_check_threshold = baseline if current >= baseline else recovery_threshold
         if not _recovery_window_satisfied(
-            trend_data,
+            history_records[-1],
             recovery_check_threshold,
             configured_recovery_window,
             history_records,
         ):
+            recovered_records = sum(
+                (value := _coverage_value_for_recovery(record)) is not None
+                and value >= recovery_check_threshold
+                for record in history_records[-configured_recovery_window:]
+            )
+            threshold_name = "baseline" if current >= baseline else "warning threshold"
             print(
-                "Coverage recovered, but configured recovery window is not satisfied; "
+                f"Coverage recovered, {recovered_records} of {configured_recovery_window} "
+                f"records at or above the {threshold_name}; "
+                "configured recovery window is not satisfied; "
                 "leaving any breach issue open"
             )
             return 0
```

## Complete changed-file head sources and direct data dependencies

### .github/sync-manifest.yml @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
# Sync Manifest - Single Source of Truth for Consumer Repo Synchronization
#
# This manifest declares ALL files that should be synced from Workflows to consumer repos.
# The sync workflow (maint-68-sync-consumer-repos.yml) reads this manifest.
# A validation CI workflow ensures this manifest is complete.
#
# POLICY: Any file intended for consumer repos MUST be listed here.
# Verifier destination grammar also binds artifact-provenance property delivery
# without treating checked provenance enforcement as a new artifact obligation.
# Exact quoted review destination names retain channel binding; parser examples stay opaque.
# Nominal no-need/requirement/obligation governors share evidence polarity across channels.
# Partial OR parsing fails closed; punctuated ORs and property storage retain their semantics.
# Files not listed will NOT be synced, even if they exist in templates/consumer-repo/.
#
# Last sync trigger: 2026-02-10 - manifest audit + sync trigger expansion
#
# Categories:
#   workflows: Thin caller workflows that consumers run directly
#   prompts: Codex prompt files for agent operations
#   scripts: JavaScript/Python scripts required by workflows
#   codex_config: Codex configuration files (AGENT_INSTRUCTIONS.md, etc.)
#   docs: Documentation files synced to consumer repos
#
# Each entry can specify:
#   - source: Safe path relative to the declared source_tree
#   - source_tree: Optional `template` or `root`; defaults to the section owner.
#       Template-owned sections fail closed when their consumer-template source is absent.
#   - target: Path in consumer repo (defaults to same as source)
#   - description: What this file does (required for documentation)
#   - skip_repos: Optional list of repo-specific exclusions with a reason.
#       Use only when a consumer has an intentional incompatible path or policy.
#   - include_repos: Optional non-empty owner/repo allowlist. Omitted means every
#       registered consumer; it cannot overlap skip_repos.
#   - overwrite_repos: Optional list of repos that should ignore create_only and
#       stay byte-aligned with the canonical template (for example stranske/Template).

version: 1

# Workflows that run in consumer repos (thin callers)
workflows:
  # Core CI/CD
  - source: .github/workflows/pr-00-gate.yml
    description: "Gate workflow - binds current PR metadata to the exact head for classifier/seal checks and consumes it in the summary Python action, then runs tests, lint and type checking before merge. It remains create-only and not yet fresh-consumer deployable under the documented workaround (resolved: #2158) because consumers own their coverage and runtime policy."
    # New-template defaults: Python 3.13/3.14; existing explicit runtime policies migrate separately.
    sync_mode: create_only  # Do not overwrite consumer-specific Gate coverage, runtime, or policy.
    overwrite_repos:
      - stranske/Template
    skip_repos:
      - repo: stranske/Manager-Database
        reason: "Maintains a fully custom Gate workflow; never overwrite (replaces the hard-coded custom_gate_repos list in maint-68)."

  - source: .github/workflows/pr-00-gate-fork-status.yml
    description: "Trusted default-branch publisher for exact-head Gate / gate statuses on fork pull requests. Create-only during staged rollout so consumer policy can be audited before replacement."
    sync_mode: create_only
    overwrite_repos:
      - stranske/Template

    skip_repos:
      - repo: stranske/Manager-Database
        reason: "Maintains a fully custom Gate workflow and is excluded with the canonical Gate source."

  - source: .github/workflows/agents-guard-fork-status.yml
    description: "Trusted default-branch publisher for exact-head Health 45 Agents Guard / guard statuses on fork pull requests; centrally managed so existing consumers receive the required context."

  - source: .github/workflows/ci.yml
    description: "CI workflow - main continuous integration entry point"
    sync_mode: create_only  # Don't overwrite - repos customize coverage-min, python versions
    overwrite_repos:
      - stranske/Template

  - source: .github/workflows/autofix.yml
    description: "Autofix workflow - repairs failed/timed-out checks; cancellations do not trigger repairs"

  - source: .github/workflows/pr-46-dependency-repair-contract.yml
    description: "Dependency repair contract - keeps bot PRs bot-owned and validates agent repair promotion provenance"

  - source: .github/workflows/agents-issue-intake.yml
    description: "Issue intake - processes new issues for agent assignment"

  - source: .github/workflows/agents-80-pr-event-hub.yml
    description: "PR event hub - consolidates PR meta, bot comments, and verify-to-issue handlers"

  - source: .github/workflows/agents-81-gate-followups.yml
    description: "Gate followups hub - keepalive and autofix; forwards evaluated PR base to Codex; budgets count Gate failures with failed jobs"

  - source: .github/workflows/agents-keepalive-sweep.yml
    description: "Keepalive sweep - periodic level-based resync; dispatches the loop for open agent PRs so silent zero-commit stalls resurface"

  # Agent system - execution
  - source: .github/workflows/agents-keepalive-loop-reporter.yml
    description: "Keepalive reporter - posts PR completion or an attributed run diagnostic when target resolution fails"

  - source: .github/workflows/agents-71-codex-belt-dispatcher.yml
    description: "Codex belt dispatcher - selects issues and creates agent branches for work"

  - source: .github/agents/belt-labels.json
    description: "Canonical belt queue labels shared by dispatcher, worker, auto-pilot, and cleanup tooling"

  - source: .github/workflows/agents-72-codex-belt-worker.yml
    description: "Codex belt worker - executes agent on issues with full prompt and context"

  - source: .github/workflows/agents-72-codex-belt-worker-dispatch.yml
    description: "Codex belt worker dispatch wrapper - allows workflow_dispatch for the worker"

  - source: .github/workflows/agents-73-codex-belt-conveyor.yml
    description: "Codex belt conveyor - orchestrates belt worker execution and handles completion"

  - source: .github/workflows/agents-autofix-dispatcher.yml
    description: "Autofix dispatch bridge - acknowledges legacy Gate repository_dispatch events; agents-81-gate-followups handles repair work"

  # Post-merge trusted-base execution, job-scoped permissions and declared secrets.
  - source: .github/workflows/agents-verifier.yml
    description: "Verifier - optional inert launch-basis correlation and bounded chunked acceptance review, expanded evidence recovery and typed provider-free retained-output recovery; guarded PASS/UNVERIFIABLE_INPUT source closure; consumer dedup binds canonical PR and linked-source Tasks/Acceptance Criteria"

  - source: .github/workflows/list-llm-models.yml
    description: "List LLM Models - helper to show available models for verifier"

  - source: .github/workflows/agents-issue-optimizer.yml
    description: "Issue optimizer - LangChain-based issue formatting and optimization (Phase 1)"

  - source: .github/workflows/agents-issue-format-guard.yml
    description: "Issue format guard - validates issues on open/edit/reopen/closed, hold/exemption-label changes, and manual dispatch against AGENT_ISSUE_FORMAT, while durable/wontfix, automated, and bot issues remain exempt and have stale agents:format leases cleared. Closed issues also clear agents:auto-pilot-pause only after a fresh state read confirms they remain closed. Pause and needs-human labels hold dispatch. Any invalid non-exempt issue change on those triggers clears stale agents:formatted state, and hold removal revalidates on resume. Non-conforming unheld work gets agents:format so the optimizer repairs it. Requires .github/scripts/issue_format.py."
    template_sync: exact

  - source: .github/workflows/agents-verify-to-new-pr.yml
    description: "Verify to new PR - authenticates native GitHub Actions report authors, binds terminal gating and generated follow-up to the latest report, then dispatches auto-pilot (bridge inlined)"

  - source: .github/workflows/agents-auto-label.yml
    description: "Auto-label - suggests/applies labels based on semantic matching (Phase 5A); installs exact-synced canonical LLM requirements independently of consumer optional extras"
    requires:
      - tools/requirements-llm.txt

  - source: .github/workflows/agents-capability-check.yml
    description: "Capability check - pre-flight agent feasibility gate (Phase 3A); installs exact-synced canonical LLM requirements independently of consumer optional extras"
    requires:
      - tools/requirements-llm.txt

  - source: .github/workflows/agents-decompose.yml
    description: "Task decomposition - breaks large issues into sub-tasks (Phase 3B); installs exact-synced canonical LLM requirements independently of consumer optional extras"
    requires:
      - tools/requirements-llm.txt

  - source: .github/workflows/agents-dedup.yml
    description: "Duplicate detection - flags similar open issues (Phase 3C); installs exact-synced canonical LLM requirements independently of consumer optional extras"
    requires:
      - tools/requirements-llm.txt

  - source: .github/workflows/agents-guard.yml
    description: "Requires exactly one explicit enabled boolean per registry agent and current PR/run/attempt bindings before registry-error corrective writes; bounded trusted-registry retries and unavailable-policy stale-success invalidation; Agents guard - binds evaluated policy to enabled registry routing labels (Health 45)"
    requires:
      - .github/agents/registry.yml

  - source: .github/workflows/agents-pr-health.yml
    description: "PR health scanner - periodic conflict resolution and failing check re-dispatch"

  - source: .github/workflows/agents-auto-pilot.yml
    source_tree: template
    target: .github/workflows/agents-auto-pilot.yml
    description: "Auto-pilot - end-to-end automation orchestrator (format → optimize → agent → verify)"

  - source: .github/workflows/agents-weekly-metrics.yml
    description: "Weekly metrics - aggregates auto-pilot, keepalive, autofix and verifier metrics into summary reports"

  # Maintenance workflows
  - source: .github/workflows/maint-coverage-guard.yml
    description: "Coverage guard - daily baseline monitoring with automatic issue creation and repository-scoped recovery history. Intentional full-workflow sync exception: ships the complete guard implementation to consumers instead of a thin reusable caller because the workflow embeds repo-specific artifact discovery and download logic tied to tools/coverage_guard.py."

  - source: .github/workflows/maint-76-claude-code-review.yml
    description: "Claude Code review (opt-in) - Workflows owns the pinned action digest; runs only on labeled PRs or manual dispatch"

  - source: .github/workflows/maint-87-docs-drift-fix-agent.yml
    description: "Docs drift fix agent - reports deterministic documentation drift weekly and creates idempotent repair issues only on an explicit apply dispatch"
    template_sync: exact

  # Renovate configuration - extends the shared fleet preset (renovate-presets/fleet.json).
  # create_only so a consumer that already onboarded (e.g. a Mend generic config) is not clobbered;
  # supersedes per-repo Renovate onboarding by giving consumers the fleet preset (dev-tool exclusions
  # owned by autofix-versions.env, grouped automerge, vendored-minimatch cascade).
  - source: .github/renovate.json
    description: "Renovate config - extends stranske/Workflows//renovate-presets/fleet (shared fleet preset)"
    sync_mode: create_only

  # Reusable PR context workflow (medium-effort rate limit optimization)
  - source: .github/workflows/reusable-pr-context.yml
    description: "Reusable PR context workflow - centralized PR data fetching via GraphQL"

  - source: .github/workflows/cross-repo-smoke.yml
    description: "Cross-repo smoke caller - opt-in host + pinned dependency integration test via reusable-13-cross-repo-smoke.yml"
    sync_mode: create_only

  # Research-backplane run-contract/v1 conformance caller (opt-in, role-based)
  - source: .github/workflows/backplane-conformance.yml
    description: "Backplane conformance caller stub - calls reusable-backplane-conformance.yml@main to validate a repo's emitted run-contract/v1 envelope (producer) or ingested object (consumer). No-op for non-participants (opt-in); editable install runs only for real project/build metadata, not tool-only pyproject.toml. Template lives under templates/consumer-repo/.github/workflows/."

# Files to remove from consumer repos (obsolete / harmful when present)
removals:
  - target: .github/workflows/dependabot-automerge.yml
    description: "Remove the retired Dependabot auto-merge workflow - the fleet is on Renovate (platformAutomerge covers auto-merge); see renovate-presets/fleet.json."
  - target: .github/workflows/agents-63-issue-intake.yml
    description: "Remove deprecated issue intake workflow (replaced by agents-64/70)"
  - target: .workflows-lib
    description: "Remove deprecated workflows lib submodule"
  - target: .github/workflows/agents-verify-to-new-pr-autopilot.yml
    description: "Remove the retired verify-to-new-pr auto-pilot bridge (logic now lives in agents-verify-to-new-pr.yml)"
  - target: .github/workflows/agents-pr-meta.yml
    description: "Remove deprecated PR metadata template workflow past the 2026-02-15 removal deadline (replaced by agents-80-pr-event-hub.yml)"
  - target: .github/workflows/agents-keepalive-loop.yml
    description: "Remove deprecated keepalive loop template workflow past the 2026-02-15 removal deadline (replaced by agents-81-gate-followups.yml)"
  - target: .github/workflows/agents-autofix-loop.yml
    description: "Remove deprecated autofix loop template workflow past the 2026-02-15 removal deadline (replaced by agents-81-gate-followups.yml)"
  - target: .github/workflows/agents-bot-comment-handler.yml
    description: "Remove deprecated bot comment handler template workflow past the 2026-02-15 removal deadline (replaced by agents-80-pr-event-hub.yml)"
  - target: .github/workflows/agents-verify-to-issue.yml
    description: "Remove deprecated verify-to-issue v1 template workflow past the 2026-02-15 removal deadline (replaced by agents-80-pr-event-hub.yml)"
  - target: .github/workflows/agents-verify-to-issue-v2.yml
    description: "Remove deprecated verify-to-issue v2 template workflow past the 2026-02-15 removal deadline (replaced by agents-80-pr-event-hub.yml)"
  - target: .github/workflows/agents-70-orchestrator.yml
    description: "Remove deprecated orchestrator workflow from template consumers (replaced by agents-80-pr-event-hub.yml and agents-81-gate-followups.yml)"
  - target: .github/workflows/agents-orchestrator.yml
    description: "Remove deprecated legacy orchestrator workflow from template consumers (replaced by agents-80-pr-event-hub.yml and agents-81-gate-followups.yml)"
  - target: .github/workflows/maint-sync-workflows.yml
    description: "Remove stale consumer-local workflow syncer that can re-fetch retired agents-63/70 workflows after central manifest removals"
  - target: .github/workflows/agents-belt-dispatcher.yml
    description: "Remove retired belt dispatcher alias wrapper from template consumers (callers rewired to agents-71-codex-belt-dispatcher.yml)"
  - target: .github/workflows/agents-belt-worker.yml
    description: "Remove retired belt worker alias wrapper from template consumers (callers rewired to agents-72-codex-belt-worker.yml)"
  - target: .github/workflows/agents-belt-conveyor.yml
    description: "Remove retired belt conveyor alias wrapper from template consumers (callers rewired to agents-73-codex-belt-conveyor.yml)"
  - target: .github/scripts/rate-limit-aware-client.js
    description: "Remove retired rate-limit-aware client from template consumers (superseded by github-rate-limited-wrapper.js)"
# Codex prompts for agent operations
prompts:
  - source: .github/codex/prompts/keepalive_next_task.md
    description: "Keepalive prompt - instructs Codex on next task in PR"

  - source: .github/codex/prompts/autofix_from_ci_failure.md
    description: "Autofix prompt - instructs Codex to fix CI/Gate failures"

  - source: .github/codex/prompts/fix_ci_failures.md
    description: "CI fix prompt - general CI failure resolution instructions"

  - source: .github/codex/prompts/fix_bot_comments.md
    description: "Bot comments prompt - instructs Codex to address bot review comments"

  - source: .github/codex/prompts/verifier_acceptance_check.md
    description: "Verifier prompt - acceptance criteria validation"

  - source: .github/codex/prompts/fix_merge_conflicts.md
    description: "Conflict resolution prompt - instructs Codex to resolve merge conflicts"

# Codex configuration
codex_config:
  - source: .github/codex/AGENT_INSTRUCTIONS.md
    description: "Agent instructions - base instructions for all Codex runs"
  - source: config/source_of_truth_docs.yml
    description: "Defines consumer-local documentation paths without distributing the Workflows fleet registry"

# Scripts required by consumer workflows
# Note: These scripts are synced because they're referenced by reusable workflows
# that run in the consumer repo context
scripts:
  - source: .github/scripts/gate-fork-status-publication.js
    description: "Validates trusted Gate identity and attempt/head binding; publishes Gate / gate with an authenticated status-id receipt from immutable default-branch code."

  - source: .github/scripts/agents-guard-fork-status-publication.js
    description: "Validates trusted Health 45 Agents Guard identity, attempt/head and registry-backed evaluated-policy-label binding, failing closed on missing agent enabled booleans or missing/ambiguous attempt receipts; publishes the required fork guard status with an authenticated status-id receipt from immutable default-branch code."
    requires:
      - .github/agents/registry.yml

  # Tools directory - Python helpers used by reusable-10-ci-python.yml

  # Dev dependency sync script
  - source: scripts/sync_dev_dependencies.py
    description: "Syncs every marker-qualified dev-tool pin and safely regenerates transitive uv requirements locks with their recorded scope"
    template_sync: exact
  - source: scripts/check_agents_md_freshness.py
    description: "Warns when the generated Orchestrator AGENTS.md playbook section cites stale repo paths or commands"
    template_sync: exact
  - source: scripts/check_docs_drift.py
    description: "Detects workflow-inventory and repository-path documentation drift for the docs drift fix agent"
    template_sync: exact
  - source: scripts/docs_drift_fix_agent.py
    description: "Builds bounded deterministic documentation-drift repair plans and idempotent issue batches"
    template_sync: exact
  - source: scripts/sync_status_file_ignores.py
    description: "Validates and updates the managed consumer .gitignore status-file block, including legacy conflict cleanup"
    template_sync: exact
  - source: .github/scripts/issue_format.py
    description: "Pure-stdlib validator for AGENT_ISSUE_FORMAT compliance. Single fleet definition of agent-processable; used by agents-issue-format-guard.yml and callable directly by local filers to pre-flight before gh issue create (non-zero exit = unfit). Do not fork per repo."
    template_sync: exact
  - source: tools/resolve_mypy_pin.py
    description: "Resolves mypy version pinning - required by reusable CI workflow"

  - source: tools/requirements-llm.txt
    description: "Pinned LLM dependencies - exact-sync guarded for agent workflows"
    template_sync: exact

  - source: tools/coverage_trend.py
    description: "Generates coverage trend summaries - required by reusable CI workflow"

  - source: tools/coverage_guard.py
    description: "Checks coverage guard artifacts - required by maint-coverage-guard.yml"

  - source: tools/__init__.py
    description: "Tools package marker for Python helpers imported by synced workflows"

  - source: tools/ci_failure_triage.py
    description: "Classifies CI failure logs - required by pr-00-gate.yml summary generation"
    template_sync: exact

  - source: tools/post_ci_summary.py
    description: "Builds consolidated Gate summary comments - required by pr-00-gate.yml"

  # Scripts directory - CI helpers used by reusable-10-ci-python.yml
  - source: scripts/state_fingerprint.py
    description: "Computes workflow state fingerprints for unchanged-state skip gates"

  - source: scripts/ledger_validate.py
    description: "Validates belt task ledgers (.agents/issue-*-ledger.yml); required by the ledger-validation job in pr-00-gate.yml, whose result feeds the required summary check on every belt PR"

  - source: scripts/belt_ledger_completion.py
    description: "Changed-artifact belt ledger completion helpers imported by scripts/ledger_validate.py (duplicate_artifact_errors); delivered with it so the Gate ledger-validation job can import"

  - source: scripts/check_deliberate_break.py
    template_sync: exact
    description: "Opt-in Gate helper that proves named deliberate-break acceptance tests fail against the base implementation"

  - source: scripts/reference_packs.py
    description: "Validates and resolves reference pack configuration for shared runner prompt assembly"

  - source: scripts/orchestrator_skill.py
    description: "Validates and resolves exported Orchestrator skill context for remote Codex lanes"

  - source: scripts/runner_lib/
    is_directory: true
    description: "Shared runner prompt assembly, output parsing, and dispatch debounce helpers"

  - source: scripts/aggregate_agent_metrics.py
    description: "Aggregates downloaded weekly agent metrics - required by agents-weekly-metrics.yml"
    template_sync: exact

  - source: scripts/coverage_history_append.py
    description: "Appends coverage data to history file - required by reusable CI workflow"

  - source: scripts/ci_metrics.py
    description: "Collects CI metrics for dashboard - required by reusable CI workflow"

  - source: scripts/ci_history.py
    description: "Manages CI history data - required by reusable CI workflow"

  - source: scripts/ci_coverage_delta.py
    description: "Computes coverage delta between runs - required by reusable CI workflow"

  - source: scripts/reusable_ci_scope.py
    description: "Selects changed-input reusable CI scenarios including flat-layout/root Python modules and requirements lock files - required by reusable CI workflows"

  - source: scripts/sync_test_dependencies.py
    description: "Syncs test dependency pins - required by reusable CI workflow"

  - source: scripts/check_test_dependencies.sh
    description: "Checks test dependencies match - required by reusable CI workflow"

  # Python scripts for auto-pilot metrics
  - source: scripts/autopilot_step_timer.py
    description: "Emits step timing timestamps for auto-pilot workflows - required by agents-auto-pilot.yml"

  - source: scripts/autopilot_metrics_collector.py
    description: "Collects and appends structured auto-pilot metrics to NDJSON log - required by agents-auto-pilot.yml"

  # Python scripts for ChatGPT topic sync
  - source: .github/scripts/decode_raw_input.py
    description: "Decodes raw input from ChatGPT connector"

  - source: .github/scripts/parse_chatgpt_topics.py
    description: "Parses ChatGPT conversation into issue topics"

  - source: .github/scripts/fallback_split.py
    description: "Fallback topic splitting when parsing fails"

  # JavaScript scripts for CI/Gate operations
  - source: .github/scripts/detect-changes.js
    description: "Detects changed files for CI path-based filtering"

  - source: .github/scripts/agents-guard.js
    description: "Health 45 agents guard logic used by the workflow protections"

  - source: .github/scripts/coverage-normalize.js
    description: "Normalizes coverage data across different report formats"

  - source: .github/scripts/maint-post-ci.js
    description: "Post-CI maintenance tasks and cleanup"

  - source: .github/scripts/gate-docs-only.js
    description: "Gate check for docs-only changes to skip full CI"

  - source: .github/scripts/checkout_source.js
    description: "Source checkout utilities for CI workflows"

  - source: .github/scripts/package.json
    description: "Node package manifest for .github scripts (vendored minimatch)"
    skip_repos:
      - repo: stranske/trip-planner
        reason: "Repo installs .github/scripts dependencies from package-lock.json and forbids tracked node_modules"

  - source: .github/agents/registry.yml
    description: "Agent registry - source of truth for agent keys and runner workflow mapping"

  - source: .github/scripts/agent_registry.js
    description: "Agent registry helper - loads registry and resolves agent key from labels"

  - source: .github/scripts/belt_claim_reclaim.js
    description: "Shared stale belt-claim timeout and audited reclaim logic for scheduled health sweeps"

  - source: .github/scripts/rate_limit_receipt.json
    description: "Single provider rate-limit receipt TTL shared by runner writer and routing reader"

  - source: .github/scripts/rate_limit_receipt.js
    description: "Time-based expiry for provider rate-limit receipts"

  - source: .github/scripts/agent_delegation_policy.js
    description: "Agent delegation policy - system-driven routing for agent:auto label"

  - source: .github/scripts/agent_stall_rotation.js
    description: "Auto-pilot stall rotation - registry-driven bounded belt-agent rotation before needs-human"

  - source: .github/scripts/node_modules/minimatch/
    is_directory: true
    description: "Vendored minimatch dependency for .github scripts"
    skip_repos:
      - repo: stranske/trip-planner
        reason: "Repo installs .github/scripts dependencies from package-lock.json and forbids tracked node_modules"

  - source: .github/scripts/node_modules/brace-expansion/
    is_directory: true
    description: "Vendored brace-expansion dependency (transitive dep of minimatch)"
    skip_repos:
      - repo: stranske/trip-planner
        reason: "Repo installs .github/scripts dependencies from package-lock.json and forbids tracked node_modules"

  - source: .github/scripts/node_modules/balanced-match/
    is_directory: true
    description: "Vendored balanced-match dependency (transitive dep of brace-expansion)"
    skip_repos:
      - repo: stranske/trip-planner
        reason: "Repo installs .github/scripts dependencies from package-lock.json and forbids tracked node_modules"

  # JavaScript scripts for issue/PR handling
  - source: .github/scripts/issue_pr_locator.js
    description: "Locates PRs associated with issues"

  - source: .github/scripts/source_context.js
    description: "Classifies PR workflow sources with bounded historical fix references, unresolved explicit issue ambiguity, repository/author-bound Release Please inference, related-issue bindings, explicit title/metadata conflict rejection and declared non-issue precedence"

  - source: .github/scripts/issue_context_utils.js
    description: "Utilities for issue context extraction"

  - source: .github/scripts/terminal_disposition.js
    description: "Machine-readable terminal disposition records and source summaries"

  - source: .github/scripts/terminal_disposition_coverage.js
    description: "Warning-only terminal disposition source coverage preflight"

  - source: .github/scripts/bot_comment_auth_coverage.js
    description: "Warning-only bot-comment App auth coverage preflight"

  - source: .github/scripts/coverage_monitor_summary.js
    description: "Machine-readable weekly coverage monitor checkpoint"

  - source: .github/scripts/weekly_metrics_artifacts.js
    description: "Bounded weekly metrics artifact selection contract"

  - source: .github/scripts/weekly_metrics_download_manifest.js
    description: "Weekly metrics artifact download and extraction manifest contract"

  - source: .github/scripts/issue_scope_parser.js
    description: "Parses issue scope and requirements; preserves authored checklists in marker-less summaries and owns the shared PR template skeleton"

  - source: .github/scripts/keepalive_instruction_template.js
    description: "Generates keepalive instructions for Codex"

  - source: .github/scripts/keepalive_loop.js
    description: "Core keepalive loop logic with evidence-gated authority reconciliation and full criterion cache binding"

  - source: .github/scripts/keepalive_challenge_due.js
    description: "Selects due automation-owned authority challenges for the hourly keepalive sweep"

  - source: .github/scripts/keepalive_authority_state.js
    description: "PR-wide conditional authority generation, immutable attempt index, pinned-tree replay reads, exact-attempt release retry, single-use receipt ledger, and versioned per-entry attempt-presence manifests with pinned delta validation and a conditional checkpoint for PR classification"

  - source: .github/scripts/keepalive_worker_evidence.js
    description: "Attempt-bound worker job evidence from the originating registry revision for keepalive authority recovery"

  - source: .github/scripts/keepalive_reporter_applicability.js
    description: "Fail-closed exact-run classification, verified no-ledger replay, and active-attempt deferral for keepalive dispatches"

  - source: .github/scripts/token_load_balancer.js
    description: "Dynamic token load balancer for API rate limit management"

  - source: .github/scripts/keepalive_prompt_routing.js
    description: "Prompt routing logic for keepalive - determines which prompt template to use"

  - source: .github/scripts/keepalive_state.js
    description: "Keepalive state management and recovered authority summary projection"

  - source: .github/scripts/timeout_config.js
    description: "Timeout configuration parser for keepalive - required by keepalive_loop.js"

  - source: .github/scripts/keepalive_guard_utils.js
    description: "Guard utilities for keepalive state protection"

  - source: .github/scripts/keepalive_contract.js
    description: "Keepalive contract definitions and validation"

  - source: .github/scripts/keepalive_gate.js
    description: "Gate evaluation logic for keepalive workflow"

  - source: .github/scripts/keepalive_worker_gate.js
    description: "Worker gate logic for keepalive workflow"

  - source: .github/scripts/keepalive_orchestrator_gate_runner.js
    description: "Orchestrator gate runner for keepalive"

  - source: .github/scripts/keepalive_post_work.js
    description: "Post-work handling for keepalive rounds"

  - source: .github/scripts/keepalive_prompt_composer.js
    description: "Composes prompts for keepalive Codex calls"

  - source: .github/scripts/capability_bundle.js
    description: "Validates and selects capability-bundle/v1 fragments for keepalive prompts and metrics"

  - source: .github/scripts/autopilot_metrics.js
    description: "AutoPilot metrics collection and reporting"

  - source: .github/scripts/auto_pilot_transitions.js
    description: "Auto-pilot transition contract and next-step helper"

  - source: .github/scripts/github-api-with-retry.js
    description: "GitHub API retry wrapper with exponential backoff and pagination support - required by agents-auto-pilot.yml"

  - source: .github/scripts/sync_tracker_state/
    is_directory: true
    description: "Shared durable tracker and open PR state helpers for consumer sync workflows"

  - source: .github/scripts/github-rate-limited-wrapper.js
    description: "Transparent rate-limit proxy - wraps all github.rest.* calls with automatic retry and token switching"

  - source: .github/scripts/prompt_injection_guard.js
    description: "Security guard against prompt injection attacks"

  - source: .github/scripts/prompt_integrity_guard.js
    description: "Integrity validation for prompts"

  - source: .github/scripts/error_classifier.js
    description: "Classifies CI errors for agent handling"

  - source: .github/scripts/error_diagnostics.js
    description: "Diagnostic utilities for error analysis"

  - source: .github/scripts/failure_comment_formatter.js
    description: "Formats failure comments for PR status updates"

  - source: .github/scripts/conflict_detector.js
    description: "Conflict detector - identifies merge conflicts for targeted resolution"

  - source: .github/scripts/merge_manager.js
    description: "Manages PR merge operations"

  - source: .github/scripts/runtime_ac_merge_guard.js
    description: "Blocks external merge lanes for PRs that require local Orchestrator runtime acceptance checks"

  - source: .github/scripts/sync_pr_lease_contract.js
    description: "Validates generated delivery lifecycle records and owns the shared seal-precondition reasons"

  - source: .github/scripts/comment-dedupe.js
    description: "Deduplicates bot comments on issues/PRs"

  - source: .github/scripts/bot-comment-dismiss.js
    description: "Collects ignored bot review comments for auto-dismiss handling"

  - source: .github/scripts/bot-comment-handler.js
    description: "Bot comment handler logic - processes bot review comments for dispatch"

  - source: .github/scripts/autofix_emit_report.py
    description: "Emits autofix report - required by reusable-18-autofix.yml"

  - source: .github/scripts/gate_summary.py
    description: "Gate summary renderer - shared and consumer copies isolate untrusted diagnostics"

  - source: .github/scripts/should-post-review.js
    description: "Evaluates whether a progress review comment should be posted"

  - source: .github/scripts/keepalive_review_guard.js
    description: "Guards against posting empty/null progress review comments"

  - source: .github/scripts/post_completion_comment.js
    description: "Posts completion comments on PRs"

  - source: .github/scripts/verifier_closure.js
    description: "Closes source issues only with nonempty exact-merge CI proof on PASS or successful exact-merge CI proof and deterministic gates for UNVERIFIABLE_INPUT"

  - source: .github/scripts/verifier_ci_query.js
    description: "Queries CI status for verifier workflow"

  - source: .github/scripts/verifier_issue_formatter.js
    description: "Formats issues for verifier output"

  - source: .github/scripts/verifier_verdict_json.py
    description: "Extracts structured post-merge verifier verdict JSON without trusting diff text"

  - source: .github/scripts/verifier_plan_fingerprint.js
    description: "Hashes canonical parsed Tasks/Acceptance Criteria and linked source lineage for consumer verifier deduplication"
    delivery: copy

  - source: .github/scripts/verifier_gzip_assets.js
    description: "Capture bounded gzip UTF-8 evidence assets from the immutable target Git tree without changing patches"
    delivery: copy

  - source: .github/scripts/verification_event.js
    description: "Carries inert optional launch-basis correlation and authenticated exact-terminal dedup references; binds repeat verification and strict recovery selectors to authoritative code, original requests, typed comparison-baseline material and explicitly required retained evidence; authenticates known-no-evaluation causal predecessors, preserves the original edge on exact-event retries and reconciles older pending attempts through authoritative Actions reads and retains full-history completion deduplication without reparenting history"
    delivery: copy

  - source: .github/scripts/verifier_pending_execution.js
    description: "Reconciles pending verifier attempts and authenticates provider-free retained-output origin, applicability and once-only publication; publishes provenance-only input-repair markers for already-retained mixed results"
    delivery: copy

  - source: .github/scripts/agents_orchestrator_resolve.js
    description: "Resolves agent orchestrator state"

  - source: .github/scripts/agents_pr_meta_keepalive.js
    description: "PR metadata handling for keepalive"

  - source: .github/scripts/agents_pr_meta_orchestrator.js
    description: "PR metadata orchestrator logic"

  - source: .github/scripts/agents_pr_meta_update_body.js
    description: "Updates PR body while preserving authored descriptions; stable completed dependency-provenance results, observer exclusion, and exact-head Gate visibility"

  - source: .github/scripts/agents_verifier_context.js
    description: "Verifier context with authenticated explicitly selected ancestor comparison baselines scoped to byte-identical named sources, bounded selected artifact members with exact-ID metadata fallback independently of optional discovery counts and truthful unselected sibling inventories, plus authenticated provider-free retained revalidation under its recovery-key guard independently of ordinary exact-event completion deduplication, explicitly selected PR and linked-source comments retaining authenticated actor/time/body before optional chatter and lossless selected-proof prompt fitting, mandatory unavailable linked-issue discovery, known non-closing source-issue retrieval, independent body/comment/artifact evidence, independently bounded run/artifact pages with stable count presence, positive safe IDs and full-page continuation, positive channel-local paginated comment identities and stable ordering with bounded full-page signature revalidation against deletion shifts, safe NDJSON proof alongside JSONL, raw extraction byte accounting before UTF-8 decoding, bounded archive/member occurrence hash inventories with duplicate-name rejection and retained unavailable suffixes, complete exact-head typed/positive-clause-labelled including trailing negative URL predicates and Markdown section/reference scope explicit-union artifact scope selected before budgeting, shared bounded descriptor-aware URL-token and negative-subject classification with fail-closed oversized prose scope and descriptive affirmative declarations for positive evidence and diagnostic-local incidental fallback, coordinated comma-and/or URL subjects and independent non-URL/contrast clauses, and associated discovery, fail-closed aggregate availability, literal destination metadata, single-normalization filename-whitespace-preserving text/binary patch offsets and complete post-merge diffs"

  - source: .github/scripts/agents_dispatch_summary.js
    description: "Summarizes agent dispatch operations"

  - source: .github/scripts/agents_belt_scan.js
    description: "Scans agent belt for available tools"

  # Agent helper scripts and copy-delivered LangChain workflow support
  #
  # delivery: channel annotation (resolved: issue #2347)
  #   copy    = physically copy-synced into the consumer tree by maint-68 and
  #             read from the consumer's own working directory at runtime.
  #   runtime = NOT copy-synced; the consuming consumer-template workflow does a
  #             runtime sparse-checkout of stranske/Workflows `scripts/langchain`
  #             (whole-directory) and runs the script from that fetched tree.
  # Entries with `delivery: runtime` MUST NOT appear in any copy-synced section
  # (they live under `runtime_fetched:` below); see
  # tests/workflows/test_sync_manifest_delivery.py.
  - source: scripts/api_client.py
    description: "Shared GitHub API client used by synced Python automation scripts"

  # Issue optimization (Phase 1) - agents-issue-optimizer.yml
  - source: scripts/langchain/issue_optimizer.py
    description: "Issue optimizer - analyzes issues and suggests improvements"
    # delivery: copy -- read from the consumer working tree by agents-auto-pilot.yml
    # (optimize/apply steps: `python scripts/langchain/issue_optimizer.py` +
    # `sys.path.insert(0, 'scripts/langchain')`), which does NOT runtime-fetch
    # scripts/langchain. Must stay copy-synced.
    delivery: copy

  - source: scripts/langchain/structured_output.py
    description: "Shared structured output helpers for LangChain workflows"
    # delivery: copy -- imported transitively by issue_optimizer.py on auto-pilot's
    # copy-path (`from scripts.langchain.structured_output import ...`).
    delivery: copy

  - source: scripts/langchain/trace_utils.py
    description: "Shared LangSmith trace metadata helpers for LangChain workflows"
    delivery: copy

  - source: scripts/langchain/_llm_client.py
    description: "Shared LangChain chat-client construction (get_llm_client/get_llm_clients)"
    # delivery: copy -- imported transitively by copy-delivered LangChain scripts
    # such as issue_optimizer.py, issue_formatter.py, and task_validator.py.
    delivery: copy

  - source: scripts/langchain/verifier_config.py
    description: "Shared verifier prompt budgets, schema-repair policy, and terminal artifact validation"
    delivery: copy

  - source: scripts/langchain/checklist_utils.py
    description: "Shared checklist parsing helpers for issue and follow-up generation"
    delivery: copy

  - source: scripts/langchain/issue_formatter.py
    description: "Issue formatter - converts raw text to AGENT_ISSUE_TEMPLATE format"
    # delivery: copy -- read from the consumer working tree by agents-auto-pilot.yml
    # (format step: `python scripts/langchain/issue_formatter.py`), which does NOT
    # runtime-fetch scripts/langchain. Must stay copy-synced.
    delivery: copy
    template_sync: exact

  - source: scripts/langchain/issue_pr_context.py
    description: "Issue/PR context assembly helper with shared token budget caps"
    delivery: copy

  - source: scripts/langchain/issue_dedup.py
    description: "Issue deduplication - finds similar open issues"
    delivery: copy

  - source: scripts/langchain/injection_guard.py
    description: "Prompt injection guard - validates prompts before LLM submission"
    delivery: copy

  - source: scripts/langchain/progress_reviewer.py
    description: "Progress reviewer - evaluates agent progress for keepalive rounds"
    delivery: copy

  # Context and semantic analysis
  - source: scripts/langchain/context_extractor.py
    description: "Context extractor - extracts relevant context from issues/PRs"
    delivery: copy

  - source: scripts/langchain/semantic_matcher.py
    description: "Semantic matcher - vector similarity for issues/labels"
    delivery: copy

  # Agent capability and task management
  - source: scripts/langchain/capability_check.py
    description: "Capability check - pre-flight agent feasibility assessment"
    delivery: copy

  - source: scripts/langchain/task_decomposer.py
    description: "Task decomposer - breaks large issues into sub-tasks"
    delivery: copy

  - source: scripts/langchain/task_validator.py
    description: "Task validator - refines generated issue tasks for actionability"
    delivery: copy

  - source: scripts/langchain/label_matcher.py
    description: "Label matcher - suggests labels based on semantic matching"
    delivery: copy

  # PR verification and follow-up
  # Direct/pronoun/qualified proofs and CI/build/execution logs reuse shared governors;
  # bounded concrete destination ORs preserve every independent AND obligation.
  # Body-component alternatives and checklist nouns share polarity/modality boundaries.
  # Blank paragraphs end checklist inheritance; optional either-in alternatives stay optional.
  # All supported list markers and structurally product-owned terminal components share those guards.
  # Temporal/relative qualifiers terminate recognized components without suppressing bare review destinations.
  # OR expansion shares independent review-predicate boundaries with channel classification.
  # Named checklist destinations retain channels before temporal/relative continuations;
  # attached destination availability keeps OR alternatives without erasing independent proof.
  # Postposed conditional/negative checklist qualifiers retain shared governor semantics.
  # Shared independent actor boundaries preserve relative polarity and copular availability.
  # Canonical shared operations and contrast-aware negative governors retain required destinations.
  # Nominal exists-negation and review-comment product subjects preserve independent delivery floors.
  # Product generation/structural destinations and always-qualified availability retain actor/OR boundaries.
  # Canonical product operations and per-item coordination preserve bare sibling review obligations.
  # Shared passive-agent normalization preserves actor, modality, aspect and review destinations in either word order.
  # Shared progressive inflections and perfect aspects preserve product alternatives and independent relative body duties.
  # Irregular left and channel-symmetric relative presence retain independent and parent alternative semantics.
  # First/final relative attachments preserve the complete bounded parent destination tail and availability alternatives.
  # Shared relative evidence conditions retain their own governor without consuming parent sibling destinations.
  # Comma-relative attachments and qualified only-if/solely-when conditions share those parent-tail guards.
  # Shared lexical aliases retain passive reviewer/product actors before channel and alternative classification.
  # Component-qualified availability stays inside complete passive destination lists and preserves bare sibling floors.
  # Shared presence relatives preserve parent lists; component content is not an extra review delivery, bare-channel duties remain independent.
  # Parent trailing conditions and local relative conditions retain separate scope; availability metadata cannot obstruct either.
  # Final availability metadata retains the trailing parent delivery condition in either voice and channel order.
  # Passive both/either destination quantifiers preserve product actor binding and bare sibling obligations.
  # Coordinated product destinations retain optional modality and independent reviewer obligations.
  # Irregular perfect delivery and repeated product operations retain shared actor/polarity binding.
  # Multi-operation chains inherit the latest explicit governor/aspect, never stale head state.
  # Product-only AND/OR chains preserve latest state without changing genuine bare-destination alternatives.
  # Passive agents respect unquoted criterion boundaries; object adjectives preserve mandatory governor and soft wraps.
  # Component start/end guards reuse all destination prepositions, retaining bare review transport qualifiers.
  # Criterion splitting protects multiline quoted literals, retaining only independent external delivery duties.
  # Shared participial content boundaries preserve bare duties and terminate real product components symmetrically.
  # Content-object negative adjectives share modality grammar without inventing overall proof obligations after passive agents.
  # Passive quantifiers on either side of prepositions and blank-paragraph relative boundaries share both classifiers.
  # Artifact payload relatives retain shared parent modality; PR presence relatives remain independent.
  # Filename dots and opaque prose payload punctuation preserve siblings; embedded product nouns do not create channel duties.
  # Counted standalone duties and pre-preposition both/either share the guarded channel and destination grammars.
  # Coordinated counts retain real duties; proof-object and product-recipient guards prevent domain artifacts becoming evidence.
  # Product actor normalization and channel suppression share one grammar.
  # Proof pronouns retain artifact destinations; bounded pure grammar caching returns fresh containers.
  - source: scripts/langchain/pr_verifier.py
    # Original requirements and minimum evidence admission are shared by both
    # judge modes; native counting covers generation, synthesis and schema repair.
    # Evaluate CLI accepts the existing OpenAI, GitHub Models and Anthropic routes.
    # Bare/qualified review-comment discovery and ORs share literal-safe normalization;
    # copy delivery and destination-first checklists retain shared polarity floors.
    # Repeated governors, object polarity, passive capabilities and channel-symmetric
    # product coordination preserve independent mandatory delivery clauses.
    # Bounded save/persist/log product storage keeps independent reviewer duties
    # and canonicalizes only its already-bound shared review destinations.
    # Passive capability normalization is shared before mixed artifact/PR ORs.
    # Plain and qualified artifact OR members retain mandatory alternative floors.
    # Bare artifact AND lists and reverse product ORs share destination normalization.
    # Independent comma/and/but/while boundaries reuse shared qualified recipient
    # prefixes, preserving product-domain nouns and genuine review delivery.
    # Same-subject predicate boundaries retain real destination lists/delivery
    # pronouns; hyphenated qualified review aliases keep mandatory comment floors.
    # Negative-content conditions cannot migrate onto mandatory parent deliveries.
    # Shared complete-object boundaries reject evidence/review-comment product compounds
    # while retaining shared proof payloads, bounded content, inherited destination
    # prepositions and independent proof antecedents through AND/OR lists.
    # Expanded v5 comparison requires every configured provider/model arm to be
    # complete, used_llm=true, error-free and PASS; no availability filtering.
    # Expanded v9 preserves a valid configured FAIL despite incomplete sibling results.
    # Source-owned exact Terra Responses and Sonnet native Models/count binding;
    # explicit independent input/context/output facts and actual request reserve.
    # Terra context 1050000/input 922000; Sonnet native input/context 1000000.
    # Exact facts come from managed registry/helper validation; expanded v7 retains
    # up to 524288 evidence characters before unchanged native capacity preflight.
    # Reusable expanded aggregation imports the fresh Workflows checkout, not stale caller code.
    # Standard review packs whole-file chunks; a required single file reaches native
    # counting without rough-budget clipping. Descriptive evidence sentences do not
    # inherit unrelated later mandates; abbreviation periods keep real duties.
    # Fitted necessary proof above its soft bound also requires native admission;
    # omitted optional history leaves bounded legacy compatibility unchanged.
    # Opt-in expanded diagnostic partitions preserve all loaded input ranges and
    # findings within native-count bounds; global dependencies always withhold PASS.
    # Every diagnostic request repeats the complete governing plan without clipping.
    description: "PR verifier - retains complete single-file requests for native capacity admission and scopes evidence mandates to their governing sentences, scopes chunk omissions to assigned paths, retains raw chunk evidence and reconciles explicitly attributed sibling concerns without waiving real findings; retains active as-artifact proof delivery, literal-safe PR/inline review-comment destinations and common-proof checklist nouns through shared polarity/product/OR grammar; normalizes actor-bound common test-result/log/screenshot/recording proof objects with early canonical contracted governors, offset-preserving literal-free proof contexts, bounded active/passive object qualifiers and literal-safe explicit pronoun antecedents across finite actor clause separators and shared negative-governor actor boundaries and structurally bounded PR-contained comment nouns through shared polarity/modality/product/literal grammar and validates independent acceptance-list items and destination-specific evidence with clause-bound mandatory evidence/artifact comment-presence predicates with shared negative requirement governors for bare be-in destinations, subject-level no polarity and canonical comment destinations, product permit capability and shared share/put/place/submit/deliver/supply aliases with shared finite compound-role subjects and possession-safe verbal guards with bounded adverb-and-polarity-aware optional-inspection noun spans and prove operations, contracted and bare prohibition polarity with additive not-only/not-merely/not-just and negative embedded-auxiliary guards with complete passive/active-perfect negative requirement actions, shared adverb-aware active-perfect/passive contrast-aware elided actor/governors and prohibition-safe checklist fallback, shared bounded multiword component and comma-availability grammar with order-symmetric single/coordinated destination OR options and actual floors and leading either alternatives, complete product-response vocabulary, bounded product-capability spans, qualified recipients and evidence-object modifiers, bound product storage/client aspects, optional-modal polarity, named and elided actor governor and finite-past sentence boundaries, attached reviewer predicates through shared destinations, complete body predicates, non-PASS concerns and rename-safe diff coverage; native-capable routes count complete standard/comparison/chunk/synthesis and schema-repair requests; registered standard routes without optional capacity facts preserve their original transport, while explicit expanded invocation always requires native capacity; evidence floors and isolated receipt I/O warnings remain"
    delivery: copy

  # NOTE (resolved: issue #2347): scripts/langchain/followup_issue_generator.py was MOVED
  # out of this copy-sync set into the `runtime_fetched:` section below. It is
  # delivered to consumers ONLY via runtime sparse-checkout (see that section).

  # Integration layer for LangChain components
  - source: scripts/langchain/integration_layer.py
    description: "Integration layer - coordinates LangChain components"
    delivery: copy

  - source: scripts/langchain/topic_splitter.py
    description: "Topic splitter - splits conversations into discrete issues"
    delivery: copy

  # LangChain prompt templates
  - source: scripts/langchain/prompts/format_issue.md
    description: "Prompt template for LLM-based issue formatting"
    delivery: copy

  - source: scripts/langchain/prompts/analyze_issue.md
    description: "Prompt template for issue analysis/optimization"
    delivery: copy

  - source: scripts/langchain/prompts/apply_suggestions.md
    description: "Prompt template for applying optimization suggestions"
    delivery: copy

  - source: scripts/langchain/prompts/context_extract.md
    description: "Prompt template for context extraction"
    delivery: copy

  - source: scripts/langchain/prompts/decompose_task.md
    description: "Prompt template for task decomposition"
    delivery: copy

  - source: scripts/langchain/prompts/pr_evaluation.md
    description: "Prompt template for PR evaluation/verification"
    delivery: copy

  - source: scripts/langchain/prompts/refine_tasks.md
    description: "Prompt template for task refinement and validation"
    delivery: copy

  - source: scripts/langchain/verdict_extract.py
    description: "Verdict extractor - parses verification verdicts from LLM output"
    delivery: copy

  - source: scripts/langchain/verdict_policy.py
    description: "Verdict policy engine - applies pass/fail rules to verification results"
    delivery: copy

  - source: tools/llm_provider.py
    description: "LLM provider configuration - GitHub Models and OpenAI client setup"

  - source: tools/langchain_client.py
    description: "LangChain client builder - multi-provider client with slot-based fallback and configuration"

  - source: tools/llm_registry.py
    description: "LLM model registry helper - shared selection/blocked-model enforcement plus exact optional native capacity facts; missing records raise the stable public NativeCapacityUnavailable exception (including naming-rule compatibility), malformed facts raise ValueError"
    template_sync: exact

  # Raw UTF-8 and CRLF identities must match loaded semantic inputs without newline normalization.
  - source: tools/verifier_gzip_assets.py
    description: "Validate exact Git gzip evidence identities, bounded single-member UTF-8 views and complete review coverage"
    template_sync: exact

  - source: tools/verifier_artifact_capture.py
    description: "Verify immutable raw artifact sidecars independently from bounded rendering"
    template_sync: exact

  - source: tools/verifier_capture_obligation_manifest.py
    description: "Capture obligations and context-bound snapshots; optional typed unrenderable media is availability, required media and integrity failures remain blocking"
    template_sync: exact

  - source: tools/verifier_semantic_acceptance.py
    description: "Reviewed semantic closure, proof joins and exact judge matrix admission"
    template_sync: exact

  - source: tools/verifier_semantic_rules.py
    description: "Fixed source-owned reviewed byte-span rules, grouped shared joins and complete per-package prompts"
    template_sync: exact

  - source: config/verifier_semantic_rules.json
    description: "Reviewed immutable semantic decomposition registry; unknown captures retain an all-input residual"
    template_sync: exact

  - source: tools/verifier_semantic_execution.py
    description: "Frozen all-cell native preflight and runner-owned semantic execution ledger"
    template_sync: exact

  - source: tools/verifier_proof_resource_plan.py
    description: "Offline full-capture archive resource accounting; no semantic/native admission"
    template_sync: exact

  - source: tools/embedding_provider.py
    description: "Embedding provider registry used by synced semantic matching helpers"
    template_sync: exact

  - source: tools/check_model_registry_freshness.py
    description: "Model-registry freshness gate - validates dated decisions, evidence, lifecycle, and profile-based slots"

  - source: tools/discover_model_catalog.py
    description: "Advisory provider-catalog discovery - proposes new model candidates without changing reviewed selections"

  - source: tools/evaluate_model_benchmark.py
    description: "Deterministic paired model benchmark evaluator - computes confidence-bound quality gates and cost/latency ranking"

  # Research-backplane run-contract/v1 validator (run locally + in the conformance gate)
  - source: scripts/validate_run_contract.py
    description: "Validates a repo's emitted run-contract/v1 run envelope (producer/bridge) or ingested satellite object (consumer) against the canonical Workflows schemas + opt-in participant registry. Offline/deterministic; opt-in skip for non-participants. Synced so participants can validate locally and the reusable conformance gate can invoke it."
    requires:
      - docs/contracts/schemas/run-contract-v1.schema.json
      - docs/contracts/schemas/artifact-manifest-v1.schema.json
      - docs/contracts/schemas/evidence-object-v1.schema.json
      - docs/contracts/schemas/tracked-variable-v1.schema.json
      - docs/contracts/schemas/capability-bundle-v1.schema.json
      - docs/contracts/schemas/mosaic-core-v1.schema.json
      - docs/contracts/schemas/document-mirror-v1.schema.json
      - docs/contracts/schemas/output-substrate-v1.schema.json

  # GraphQL-based PR context fetcher (medium-effort rate limit optimization)
  - source: .github/scripts/pr-context-graphql.js
    description: "GraphQL PR context fetcher - reduces 4+ REST calls to 1 GraphQL call"

  - source: .github/scripts/github-api-cache.js
    description: "Shared cache utilities for GitHub API requests used by PR context scripts"

  - source: .github/scripts/github-api-cache-client.js
    description: "Client wrapper for cached GitHub API requests"
# Templates required by keepalive system
templates:
  - source: .github/templates/keepalive-instruction.md
    description: "Keepalive instruction template - directives for Codex on each round"

  - source: .github/PULL_REQUEST_TEMPLATE.md
    description: "Pull request template with Workflow Source fields for direct GitHub and non-issue work"

  - source: .github/path-classification.yml
    description: "Path classification config used by the path-classifier composite action"

  - source: .github/workflows/ci-python-versions.env
    source_tree: template
    description: "Shared Python 3.14 CI defaults and compatible test/lint tool pins; repo-owned autofix pins take precedence"

# Actions required by reusable workflows
actions:
  - source: .github/actions/agent-event-eligibility/
    is_directory: true
    description: "Agent event eligibility action - early no-op gate for agent workflows"

  - source: .github/actions/setup-api-client/
    is_directory: true
    description: "Unified API client setup - installs @octokit deps and exports all load balancer tokens"

  - source: .github/actions/agent-run-base/
    source_tree: root
    is_directory: true
    description: "Shared agent runner setup action - required by reusable-codex-run.yml and reusable-claude-run.yml"

  - source: .github/actions/resolve-default-branch/
    is_directory: true
    description: "Resolves repository default branches for Workflows dual-checkout patterns"

  - source: .github/actions/export-load-balancer-tokens/
    is_directory: true
    description: "Export load balancer tokens action - required by reusable-10-ci-python.yml (deprecated, use setup-api-client)"

  - source: .github/actions/path-classifier/
    is_directory: true
    description: "Classifies changed PR paths for path-aware expensive job gating"
    requires:
      - .github/scripts/sync_pr_lease_contract.js

  - source: .github/actions/artifact-cache/
    is_directory: true
    description: "Restores, discovers, and caches workflow artifacts by daily, weekly, or run window"

# Configuration files for LLM providers and workflows
llm_config:
  - source: config/llm_slots.json
    description: "LLM slot configuration - defines provider/model slots for multi-provider workflows"
    sync_mode: create_only  # Don't overwrite - repos may customize provider preferences

  - source: config/model_registry.json
    description: "Model registry - available LLM models, selections and optional reviewed exact native capacity/transport facts"

  - source: config/model_selection_policy.json
    description: "Model selection policy - benchmark gates, measurements, optimization order, and review triggers"

# Documentation synced to consumer repos
docs:
  - source: docs/CI_FAILURE_PLAYBOOK.md
    source_tree: root
    target: docs/CI_FAILURE_PLAYBOOK.md
    description: "Shared CI failure triage playbook with locally resolvable diagnostic links"

  - source: docs/MODEL_SELECTION_POLICY.md
    source_tree: root
    target: docs/MODEL_SELECTION_POLICY.md
    description: "Auditable auxiliary-model evaluation, selection, and refresh policy"

  - source: docs/AGENT_ISSUE_FORMAT.md
    target: docs/AGENT_ISSUE_FORMAT.md
    description: "Format specification for agent-compatible issues"

  - source: docs/CI_SYSTEM_GUIDE.md
    target: docs/CI_SYSTEM_GUIDE.md
    description: "Guide to the CI system for agents"

  - source: docs/LABELS.md
    source_tree: template
    target: docs/LABELS.md
    description: "Label definitions and usage"

  - source: docs/CODEX_TOKEN_REFRESH.md
    target: docs/CODEX_TOKEN_REFRESH.md
    description: "Codex OAuth token refresh guide"

  - source: docs/TARGET_WORK_ENVIRONMENT.md
    target: docs/TARGET_WORK_ENVIRONMENT.md
    description: "Confirmed target work-environment capabilities and blocked delivery shapes"

  - source: AGENTS.md
    target: AGENTS.md
    description: "Context file for agents and coding assistants"
    skip_repos:
      - repo: stranske/Trend_Model_Project
        reason: "Repo keeps historical Agents.md casing to avoid case-only path conflicts"
      - repo: stranske/Fine-Art-Archive
        reason: >-
          Sync commit faee7246 (2026-08-25) overwrote this file and silently deleted 60 lines of
          repo-owned research guidance ("Identifying a Work: Reverse Image Search Is the Next
          Step"). That guidance is archive-specific and belongs to the consumer, not the shared
          template; the docs section is overwrite-synced, so the only protection is skipping the
          repo here. Incident: resolved: #3275.
      - repo: stranske/Orchestrator
        reason: >-
          Orchestrator owns a terminal merge invariant in AGENTS.md that requires its local
          src/merge_guard.py for every repository-local terminal merge. Overwrite-sync removes
          that safety rule and fails tests/test_merge_entrypoint_contract.py on generated
          workflow-sync delivery. Keep this tool-owned guidance local, as with its CLAUDE.md
          exception.

  - source: CLAUDE.md
    target: CLAUDE.md
    description: "Context file for Claude/AI assistants"
    skip_repos:
      - repo: stranske/Fine-Art-Archive
        reason: >-
          Same incident as the AGENTS.md skip above: sync commit faee7246 (2026-08-25) deleted the
          identical 60-line repo-owned reverse-image-search section from this file too. The repo
          maintains its own CLAUDE.md with archive-specific rules; overwrite-sync would delete
          them again. Incident: resolved: #3275.
      - repo: stranske/Orchestrator
        reason: >-
          Orchestrator is the local agent-orchestration TOOL, not a product consumer. Its CLAUDE.md
          is the tool's own safety net: the tool-vs-evidence split, the three-trees rule (clone /
          launchd mirror / $ORCH_STATE_DIR), and the requirement to verify with verify.py rather
          than a shell loop over test files. CLAUDE.md is the file agents auto-load every session,
          so it is the enforcement mechanism; overwriting it with the consumer template would
          silently remove those rules. Consumer conventions are referenced FROM that file instead.

  - source: docs/contracts/agent-runner-output.md
    target: docs/contracts/agent-runner-output.md
    description: "Agent runner output contract specification - required for implementing new agent runners"

  # Research-backplane run-contract/v1 contract set (spec + schemas + identity conventions).
  # The registry (config/backplane_participants.json) and the program doc
  # (docs/contracts/research-backplane-contract.md) are intentionally NOT synced
  # (Workflows-only single source of truth); see research-backplane-contract.md.
  - source: docs/contracts/run-contract-v1.md
    source_tree: root
    target: docs/contracts/run-contract-v1.md
    description: "Research-backplane run-contract/v1 wire-format spec - participants need it to implement an emitter/ingest adapter"

  - source: docs/contracts/identity-map-conventions.md
    source_tree: root
    target: docs/contracts/identity-map-conventions.md
    description: "Canonical entity-ID conventions for run-contract/v1 identity_refs / evidence entity_ref - participants emit against these"

  - source: docs/contracts/capability-bundle-v1.md
    target: docs/contracts/capability-bundle-v1.md
    description: "Capability-bundle/v1 prompt-fragment and gate metadata contract for Workflows Keepalive"

  - source: docs/contracts/schemas/capability-bundle-v1.schema.json
    target: docs/contracts/schemas/capability-bundle-v1.schema.json
    description: "JSON Schema (draft 2020-12) for capability-bundle/v1 keepalive prompt fragments and gate metadata"

  - source: docs/contracts/schemas/run-contract-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/run-contract-v1.schema.json
    description: "JSON Schema (draft 2020-12) for run-contract/v1 run envelopes - loaded by the validator and local helpers so participants validate without a Workflows checkout"

  - source: docs/contracts/schemas/artifact-manifest-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/artifact-manifest-v1.schema.json
    description: "JSON Schema (draft 2020-12) for artifact-manifest/v1 - the named-artifact manifest a run envelope references"

  - source: docs/contracts/schemas/evidence-object-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/evidence-object-v1.schema.json
    description: "JSON Schema (draft 2020-12) for evidence-object/v1 - attributable evidence objects (the satellite schema consumers like the LMS would ingest)"

  - source: docs/contracts/schemas/evidence-object-v1.schema.json
    source_tree: root
    target: src/deliverable_render/store/evidence-object-v1.schema.json
    include_repos:
      - stranske/Deliverable-Render
    description: "JSON Schema (draft 2020-12) for evidence-object/v1 - Deliverable-Render packaged-evidence schema"

  - source: docs/contracts/schemas/evidence-object-v1.schema.json
    source_tree: root
    target: src/manager_mosaic/schemas/evidence-object-v1.schema.json
    include_repos:
      - stranske/Manager-Mosaic
    description: "JSON Schema (draft 2020-12) for evidence-object/v1 - Manager-Mosaic packaged-evidence schema"

  - source: docs/contracts/document-identity-conventions.md
    source_tree: root
    target: docs/contracts/document-identity-conventions.md
    description: "Fleet contract for content-first document identity, secondary keys, supersession, and text-basis attribution"

  - source: docs/contracts/tracked-variable-v1.md
    source_tree: root
    target: docs/contracts/tracked-variable-v1.md
    description: "Tracked-variable/v1 specification and clause-variable alias for backplane consumers"

  - source: docs/contracts/schemas/tracked-variable-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/tracked-variable-v1.schema.json
    description: "Tracked-variable/v1 schema with embedded evidence and document/mirror provenance"

  - source: docs/contracts/mosaic-core-v1.md
    source_tree: root
    target: docs/contracts/mosaic-core-v1.md
    description: "Mosaic-core/v1 record types and fact-key join semantics"
    requires:
      - docs/contracts/schemas/mosaic-core-v1.schema.json
      - docs/contracts/schemas/artifact-manifest-v1.schema.json

  - source: docs/contracts/schemas/mosaic-core-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/mosaic-core-v1.schema.json
    description: "Mosaic-core/v1 schema for facts, discrepancies, thesis claims and checks"

  - source: docs/contracts/document-mirror-v1.md
    source_tree: root
    target: docs/contracts/document-mirror-v1.md
    description: "Document-mirror/v1 specification for offline blob catalogs and triple-link resolvers"
    requires:
      - docs/contracts/schemas/document-mirror-v1.schema.json

  - source: docs/contracts/schemas/document-mirror-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/document-mirror-v1.schema.json
    description: "Document-mirror/v1 schema for mirror_root catalogs with content_sha256 blobs and source_refs"

  - source: docs/contracts/output-substrate-v1.md
    source_tree: root
    target: docs/contracts/output-substrate-v1.md
    description: "Output-substrate/v1 renderer profiles, workspace bundle refs, and manifest CSV exports"
    requires:
      - docs/contracts/schemas/output-substrate-v1.schema.json
      - docs/contracts/schemas/artifact-manifest-v1.schema.json

  - source: docs/contracts/schemas/output-substrate-v1.schema.json
    source_tree: root
    target: docs/contracts/schemas/output-substrate-v1.schema.json
    description: "Output-substrate/v1 schema for vendored renderer wiring and view-bundle pointers"

  - source: docs/SETUP_CHECKLIST.md
    target: docs/SETUP_CHECKLIST.md
    description: "Consumer repo setup checklist. Includes the default_workflow_permissions=write step in section 3.3.1 that prevents a Gate startup_failure on fresh consumers (resolved: #2157). Synced so it no longer drifts across the fleet."

  # ---- Shared design system (fleet UX consistency) ----
  # CSS tokens/components + a Streamlit adapter kit + the presentation-patterns
  # standard, synced into each consumer's design-system/. Apps consume a PATTERN
  # (theme / empty-state / error / dev-notice / availability-badge / no-raw-ids)
  # rather than inventing bespoke fixes. Per-app overrides go in an app stylesheet
  # loaded AFTER tokens.css; never fork components.css. Grouped here with the other
  # synced reference assets (cf. the run-contract JSON schemas above).
  - source: design-system/tokens.css
    target: design-system/tokens.css
    description: "Design-system theme tokens (theme-air/theme-paper + density axis). Override tokens in an app stylesheet loaded after this; do not fork."
  - source: design-system/components.css
    target: design-system/components.css
    description: "Design-system component layer (.ds): panels/appbar/kpis/tables/fields + presentation-state patterns (.notice, .empty-state, .badge, .skeleton)."
  - source: design-system/ds_streamlit.py
    target: design-system/ds_streamlit.py
    description: "Streamlit adapter for the design system (inject_theme/empty_state/notice/error/translate_error/dev_note/availability_badge/humanize_id) so Streamlit apps consume the same presentation patterns."
  - source: design-system/PRESENTATION_PATTERNS.md
    target: design-system/PRESENTATION_PATTERNS.md
    description: "The presentation-patterns standard (P1-P6): the rule behind each pattern + per-app-type application + the finding->pattern map from the 2026-06 UX-Review fleet baseline."
  - source: design-system/README.md
    target: design-system/README.md
    description: "Design-system usage guide: how to apply the theme + components/kit per app type."

# Issue templates synced to consumer repos
issue_templates:
  - source: .github/ISSUE_TEMPLATE/agent_task.yml
    description: "Agent task issue template - structured format for agent-compatible issues"

  - source: .github/ISSUE_TEMPLATE/config.yml
    description: "Issue template chooser config - controls which templates appear in the UI"

# User-facing documentation
user_docs:
  - source: WORKFLOW_USER_GUIDE.md
    target: WORKFLOW_USER_GUIDE.md
    description: "Workflow user guide - explains the CI/agent system for repo consumers"

# Git configuration files for merge strategies
git_config:
  - source: .gitattributes
    description: "Git attributes - merge strategies to prevent pr_body.md conflicts"
  - source: .coderabbit.yaml
    description: "CodeRabbit auto-review config - skips maintenance-bot PRs (renovate/dependabot/github-actions/keepalive) and generated sync/draft PRs, while keeping substantial agent-authored PR reviews enabled. High-level summaries stay in the walkthrough comment so release-note bullets cannot inflate keepalive checklists. Advisory/non-gating per fleet rule."


# Workflows-owned runtime-fetched scripts (resolved: issue #2347)
#
# These files are intentionally NOT copy-synced into consumer repos. The
# consumer-template workflows that use them perform a runtime sparse-checkout of
# stranske/Workflows `scripts/langchain` (whole-directory) and run the script
# directly from that fetched tree, so a copy in the consumer working tree would
# only create a second, skew-prone delivery path during the daily sync window.
#
# This section is deliberately NOT in the list of sections processed by the
# sync engine (maint-68-sync-consumer-repos.yml) or the drift checker
# (scripts/check_consumer_sync_drift.py), so entries here are never copied and
# never drift-probed. Each entry MUST carry `delivery: runtime`.
# Enforced by tests/workflows/test_sync_manifest_delivery.py.
runtime_fetched:
  - source: scripts/langchain/followup_issue_generator.py
    delivery: runtime
    description: "Follow-up issue generator - creates issues from verification feedback. Runtime-fetched only."
    # Runtime-fetch evidence (consumer-delivered workflows, both in the manifest
    # `workflows:` set):
    #   * templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml
    #     - L315-323: actions/checkout repository: stranske/Workflows,
    #       sparse-checkout includes `scripts/langchain` + `tools`, NO `path:`
    #       (lands in the workspace root).
    #     - L434: `python scripts/langchain/followup_issue_generator.py ...`
    #       runs from that runtime-fetched root.
    #   * templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml
    #     - L67-83: the ONLY checkout is repository: stranske/Workflows with
    #       `scripts/langchain` in sparse-checkout and NO `path:`; the consumer's
    #       own repo is never checked out into root in this job.
    #     - L576: `python scripts/langchain/followup_issue_generator.py ...`.
    # No consumer-delivered workflow reads this module from the copy-synced tree,
    # and no script/tool imports it (grep: zero importers), so dropping it from
    # copy-sync is safe.

excluded:

  - path: .gitignore
    reason: "Repo-specific ignore patterns; the managed Workflows status-file block is propagated by scripts/sync_status_file_ignores.py instead of generic sync targets"
  - path: README.md
    reason: "Repo-specific documentation"
  - path: config/coverage-baseline.json
    reason: "Each repo maintains its own coverage baseline - template provided for reference"
  - path: scripts/__pycache__
    reason: "Python bytecode cache - never synced"
  - path: .github/workflows/autofix-versions.env
    reason: "Repo-specific CI version pins; consumers copy or override per docs/ci/WORKFLOWS.md. Intentionally not synced (see CLAUDE.md)."

# Copilot configuration - skills and instructions for AI assistants
copilot_config:
  - source: .github/copilot-instructions.md
    description: "Repository-specific instructions for GitHub Copilot"

  # Skills folder - synced as a directory
  - source: .github/copilot-skills/
    is_directory: true
    description: "Copilot skill definitions - patterns for CI, GitHub ops, etc."

```

### .github/workflows/maint-coverage-guard.yml @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
name: Maint Coverage Guard

'on':
  schedule:
    - cron: '45 6 * * *'
  workflow_dispatch:

permissions:
  contents: read
  actions: read
  issues: write

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # Rate limit gate: skip non-critical coverage checks when API quota is low
  # This ensures keepalive and core workflows get priority (threshold: 2000)
  rate-limit-check:
    name: Rate limit gate
    runs-on: ubuntu-latest
    outputs:
      proceed: ${{ steps.check.outputs.proceed || 'true' }}
      remaining: ${{ steps.check.outputs.remaining || '' }}
    steps:
      - name: Checkout retry helpers
        uses: actions/checkout@v7
        with:
          sparse-checkout: |
            .github/actions/setup-api-client
            .github/actions/artifact-cache
            .github/scripts/error_classifier.js
            .github/scripts/github-api-with-retry.js
            .github/scripts/token_load_balancer.js
          sparse-checkout-cone-mode: false

      - name: Setup API client
        uses: ./.github/actions/setup-api-client
        with:
          # named inputs, not the whole secrets context (see #3185)
          github_token: ${{ github.token }}
          service_bot_pat: ${{ secrets.SERVICE_BOT_PAT }}
          actions_bot_pat: ${{ secrets.ACTIONS_BOT_PAT }}
          owner_pr_pat: ${{ secrets.OWNER_PR_PAT }}
          agents_automation_pat: ${{ secrets.AGENTS_AUTOMATION_PAT }}
          workflows_app_id: ${{ secrets.WORKFLOWS_APP_ID }}
          workflows_app_private_key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}
          keepalive_app_id: ${{ secrets.KEEPALIVE_APP_ID }}
          keepalive_app_private_key: ${{ secrets.KEEPALIVE_APP_PRIVATE_KEY }}
          gh_app_id: ${{ secrets.GH_APP_ID }}
          gh_app_private_key: ${{ secrets.GH_APP_PRIVATE_KEY }}
          app_1_id: ${{ secrets.APP_1_ID }}
          app_1_private_key: ${{ secrets.APP_1_PRIVATE_KEY }}
          app_2_id: ${{ secrets.APP_2_ID }}
          app_2_private_key: ${{ secrets.APP_2_PRIVATE_KEY }}



      - name: Check API quota
        id: check
        uses: actions/github-script@v9
        env:
          # Higher threshold than orchestrator (1000) so keepalive runs first
          RATE_LIMIT_THRESHOLD: '2000'
        with:
          script: |
            // # best-effort: this ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative.
            const threshold = parseInt(process.env.RATE_LIMIT_THRESHOLD || '2000', 10);
            const fs = require('fs');
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { withRetry } = retryHelpers;
            try {
              const { data } = await withRetry(() => github.rest.rateLimit.get());
              const remaining = data?.resources?.core?.remaining || 0;
              const limit = data?.resources?.core?.limit || 5000;
              const proceed = remaining >= threshold;

              core.setOutput('proceed', proceed ? 'true' : 'false');
              core.setOutput('remaining', String(remaining));

              if (!proceed) {
                const reset = data?.resources?.core?.reset || 0;
                const resetTime = new Date(reset * 1000).toISOString();
                const notice = `Deferring coverage guard: API quota low (${remaining}/${limit}).`;
                core.notice(`${notice} Resets at ${resetTime}`);
                const quotaMessage = [
                  'API quota too low for non-critical health checks',
                  `(${remaining}/${limit} remaining).`,
                ].join(' ');
                await core.summary
                  .addHeading('Coverage Guard Deferred', 3)
                  .addRaw(quotaMessage)
                  .addEOL()
                  .addRaw(`Threshold: ${threshold}. Resets at: ${resetTime}`)
                  .write();
              }
            } catch (error) {
              core.warning(`Rate limit check failed: ${error.message}. Proceeding anyway.`);
              core.setOutput('proceed', 'true');
            }

  guard:
    name: coverage baseline monitor
    needs: rate-limit-check
    if: >-
      ${{ needs.rate-limit-check.outputs.proceed == 'true' }}
    runs-on: ubuntu-latest
    steps:
      # ONE checkout of the whole repository. A second `actions/checkout` with `sparse-checkout` into the same workspace re-applies a
      # sparse set and removes everything outside it, including `tools/coverage_guard.py`, which `Run coverage guard` runs: the guard
      # failed with "can't open file tools/coverage_guard.py" on its first run after the artifact fixes. The full checkout already
      # carries `.github/actions/artifact-cache` and the retry helpers under `.github/scripts/`.
      - name: Checkout repository
        uses: actions/checkout@v7

      - name: Locate latest Gate workflow run
        id: discover
        uses: actions/github-script@v9
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const { owner, repo } = context.repo;
            const fs = require('fs');
            // WHICH WORKFLOW CARRIES THIS REPO'S COVERAGE IS A PER-REPO FACT, AND IT WAS HARDCODED.
            //
            // Two repos are invisible to this guard for the same reason, and neither is
            // misconfigured. stranske/Counter_Risk deliberately measures coverage on ci.yml -- its
            // Gate carries an explicit "PR Gate is optimized for fast feedback. Full coverage
            // enforcement runs on main" rationale. stranske/Orchestrator publishes its only honest
            // figure (80.3% combined, against the 34.11% its Gate reports for pytest alone) from a
            // job in ci.yml, because 79 of its 102 modules are exercised by --selftest subprocesses
            // that pytest-cov cannot see. A guard that can only ever look at pr-00-gate.yml reports
            // "no coverage" for both, which is indistinguishable from a repo that has none.
            //
            // Read from config/coverage-baseline.json, which is the right home: it is already the
            // per-repo coverage config and is explicitly EXCLUDED from template sync ("Each repo
            // maintains its own coverage baseline"), so a repo can answer this without diverging
            // from the synced workflow.
            //
            // The default is exactly the previous behaviour, so no repo changes unless it opts in,
            // and an unreadable or malformed config falls back to it rather than failing: a guard
            // that died on its own config would be worse than one that looks in one place.
            const DEFAULT_WORKFLOWS = ['.github/workflows/pr-00-gate.yml'];
            const configuredWorkflowIds = (declared) =>
              Array.isArray(declared)
                ? declared
                    .filter((workflow) => typeof workflow === 'string')
                    .map((workflow) => workflow.trim())
                    .filter(Boolean)
                : [];
            const errorMessage = (error) =>
              error instanceof Error ? error.message : String(error);
            let workflowIds = DEFAULT_WORKFLOWS;
            let workflowSource = 'default';
            try {
              const cfgRaw = fs.readFileSync('config/coverage-baseline.json', 'utf8');
              const cfg = JSON.parse(cfgRaw);
              const declared = configuredWorkflowIds(cfg.source_workflows);
              if (declared.length) {
                workflowIds = declared;
                workflowSource = 'config/coverage-baseline.json';
              }
            } catch (err) {
              core.info(
                `coverage-baseline.json not read for source_workflows (${errorMessage(err)}); ` +
                  'using the default workflow list'
              );
            }
            core.info(`Searching for coverage in: ${workflowIds.join(', ')} (from ${workflowSource})`);
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { paginateWithRetry, withRetry } = retryHelpers;

            // Every configured workflow is listed and the runs POOLED, rather than stopping at the
            // first that returns anything. A repo can legitimately publish coverage from more than
            // one workflow, and taking only the first would make the ORDER of a config list into a
            // silent filter.
            let runs = [];
            const searched = [];
            for (const wf of workflowIds) {
              try {
                const found = await paginateWithRetry(
                  github, github.rest.actions.listWorkflowRuns,
                  {
                    owner,
                    repo,
                    workflow_id: wf,
                    status: 'completed',
                    per_page: 50,
                  },
                );
                const successfulForWorkflow = found
                  .filter((run) => ['success', 'neutral'].includes(run.conclusion || ''))
                  .sort(
                    (a, b) =>
                      new Date(b.run_started_at || b.created_at || 0) -
                      new Date(a.run_started_at || a.created_at || 0),
                  )
                  .slice(0, 10);
                searched.push(
                  `${wf} (${found.length} run(s); ${successfulForWorkflow.length} successful probed)`,
                );
                runs = runs.concat(successfulForWorkflow);
              } catch (err) {
                // A workflow named in config that does not exist here is a CONFIG error worth
                // naming, not a reason to abandon the others.
                searched.push(`${wf} (UNAVAILABLE: ${errorMessage(err)})`);
              }
            }

            if (!runs.length) {
              core.warning(`No successful or neutral completed runs found in: ${searched.join('; ')}`);
              core.setOutput('run_id', '');
              core.setFailed(
                'Coverage verification requires at least one successful or neutral completed run ' +
                  `in a configured workflow. Searched: ${searched.join('; ')}. If this repo ` +
                  'publishes coverage elsewhere, add source_workflows to config/coverage-baseline.json.'
              );
              return;
            }

            const runsToProbe = runs.sort(
              (a, b) =>
                new Date(b.run_started_at || b.created_at || 0) -
                new Date(a.run_started_at || a.created_at || 0),
            );
            // THE PAYLOAD IS THE ONLY REQUIREMENT, AND IT HAS TWO NAMES IN THE WILD.
            // pr-00-gate.yml uploads it under the ARTIFACT name `gate-coverage.json` (the FILE
            // inside is gate-coverage.json; the step conflated the two), while this guard was
            // written against `gate-coverage`. A paired literal in two files that disagreed, so
            // the guard probed ten successful runs, found two of three artifacts every time, and
            // reported no usable run at all -- in every consumer repo, for as long as it existed.
            //
            // Accept BOTH here rather than renaming the producer: pr-00-gate.yml is distributed
            // create-only, so a producer rename reaches NEW repos only, while this file is
            // sync-managed and reaches all of them.
            //
            // AND IT HAS A THIRD SHAPE, WHICH IS THE ONE ALMOST EVERY REPO ACTUALLY USES. The
            // producer runs under a version matrix, so the artifact it publishes is suffixed:
            // `gate-coverage-3.12-1` and `gate-coverage-3.13-1`. Measured 2026-08-30 across the
            // lane fleet, EIGHT repos published a trend, a summary and both suffixed payloads --
            // everything this job needs -- and every one was skipped, because an exact-name list
            // can never match a name that carries a matrix suffix. The guard had failed in all 13
            // repos, continuously; two more names would not have fixed it, so the match is by
            // PREFIX with the non-payload artifacts excluded by name.
            //
            // Note what the exclusions are: `-trend`, `-trend-history`, `-summary` and `-delta`
            // all share the `gate-coverage` prefix, so a bare prefix match would have selected the
            // TREND as the payload and compared coverage against itself.
            const coveragePayloadNames = ['gate-coverage', 'gate-coverage.json'];
            const payloadPrefix = 'gate-coverage';
            const notAPayload = /^gate-coverage-(trend|summary|delta)/;
            const payloadCandidates = (names) => {
              const exact = coveragePayloadNames.filter((name) => names.has(name));
              const suffixed = [...names]
                .filter((name) => name.startsWith(payloadPrefix) && !notAPayload.test(name))
                .filter((name) => !coveragePayloadNames.includes(name))
                .sort();
              // Exact names first so a repo where this already worked is untouched; the suffixed
              // ones are SORTED rather than taken in listing order, because the API's order is not
              // stable and a coverage figure that depends on it would move for no reason.
              return [...exact, ...suffixed];
            };
            // The guard cannot evaluate a baseline from the payload alone: coverage_guard.py
            // deliberately treats a missing trend payload as a no-op.  Only select runs that
            // carry the trend artifact, otherwise this job can report success without checking
            // coverage or updating a breach issue.
            const trendArtifactName = 'gate-coverage-trend';
            const historyArtifactName = 'gate-coverage-trend-history';
            let candidate = null;
            let resolvedPayloadName = '';
            let resolvedTrendName = '';
            let resolvedHistoryName = '';
            const seenCoverageArtifacts = new Set();
            const seenPayloadArtifacts = new Set();
            for (const run of runsToProbe) {
              let artifacts = [];
              try {
                artifacts = await paginateWithRetry(
                  github,
                  github.rest.actions.listWorkflowRunArtifacts,
                  {
                    owner,
                    repo,
                    run_id: run.id,
                    per_page: 100,
                  },
                );
              } catch (error) {
                core.warning(
                  `Skipping Gate run ${run.id}; artifact lookup failed: ${error.message}`,
                );
                continue;
              }

              // Accumulated ACROSS runs so the failure message can distinguish "no coverage
              // artifacts anywhere" from "artifacts under names this job cannot use". Those are
              // opposite findings and only one of them means coverage is off.
              const availableCoverageArtifactNames = new Set(
                artifacts
                  .filter((artifact) => !artifact.expired)
                  .map((artifact) => artifact.name),
              );
              for (const name of availableCoverageArtifactNames) {
                if (name.startsWith(payloadPrefix)) seenCoverageArtifacts.add(name);
              }
              const candidateNames = payloadCandidates(availableCoverageArtifactNames);
              for (const name of candidateNames) seenPayloadArtifacts.add(name);
              const payloadName = candidateNames[0] || '';
              if (candidateNames.length > 1) {
                core.info(
                  `Gate run ${run.id} carries ${candidateNames.length} coverage payloads ` +
                    `(${candidateNames.join(', ')}); using ${payloadName}. They are the same ` +
                    'suite on different interpreters, so the choice is fixed rather than left ' +
                    'to listing order.',
                );
              }
              const hasTrend = availableCoverageArtifactNames.has(trendArtifactName);
              if (payloadName && hasTrend) {
                candidate = run;
                resolvedPayloadName = payloadName;
                resolvedTrendName = trendArtifactName;
                resolvedHistoryName = availableCoverageArtifactNames.has(historyArtifactName)
                  ? historyArtifactName
                  : '';
                break;
              }
              core.info(
                [
                  `Skipping Gate run ${run.id}; required coverage artifacts are incomplete.`,
                  payloadName
                    ? `Found payload ${payloadName} but no ${trendArtifactName}.`
                    : seenCoverageArtifacts.size
                      ? `No usable payload among ${[...seenCoverageArtifacts].sort().join(', ')}.`
                      : 'This run published no gate-coverage artifacts at all.',
                ].join(' '),
              );
            }

            if (!candidate) {
              // THREE FINDINGS, NOT ONE. "This repo does not measure coverage", "it measures it
              // and publishes it under a name I do not recognise" and "it publishes a payload but
              // no trend" have completely different fixes, and the single message this replaced
              // asserted the first in all three cases. It told eight repos that were measuring
              // coverage, and publishing it, to go and switch coverage on.
              core.warning(
                seenCoverageArtifacts.size === 0
                  ? [
                      'Unable to locate a recent successful Gate workflow run carrying any',
                      'gate-coverage artifact. Coverage is most likely not being measured here:',
                      'check that the reusable CI caller sets coverage: true and',
                      'enable-soft-gate: true.',
                    ].join(' ')
                  : seenPayloadArtifacts.size === 0
                    ? [
                        'Gate runs DID publish gate-coverage artifacts, but none matched a',
                        'supported payload shape.',
                        `Seen: ${[...seenCoverageArtifacts].sort().join(', ')}.`,
                        `A payload is any gate-coverage* artifact except ${'-trend'}/-summary/-delta.`,
                        'Coverage IS being measured in this repo, but the payload names are',
                        'unusable by this guard; align the producer name or matcher.',
                      ].join(' ')
                    : [
                        'Gate runs DID publish usable coverage payloads, but none had the required',
                        `${trendArtifactName} on the same run.`,
                        `Payloads seen: ${[...seenPayloadArtifacts].sort().join(', ')}.`,
                        'Coverage IS being measured in this repo; publish the missing trend',
                        'artifact rather than enabling coverage again.',
                      ].join(' '),
              );
              core.setOutput('run_id', '');
              const missingPairReason =
                seenCoverageArtifacts.size === 0
                  ? 'no gate-coverage artifacts were published'
                  : seenPayloadArtifacts.size === 0
                    ? 'published coverage artifact names did not match a supported payload shape'
                    : `coverage payloads were published without ${trendArtifactName}`;
              core.setFailed(`Coverage verification could not proceed: ${missingPairReason}.`);
              return;
            }

            core.setOutput('run_id', String(candidate.id || ''));
            core.setOutput('run_number', String(candidate.run_number || ''));
            // The downloader learns the names from the producer's actual artifact list instead of
            // repeating a literal. A name that is discovered cannot drift from the name that
            // exists, which is the whole defect this replaces.
            core.setOutput('coverage_artifact_name', resolvedPayloadName);
            core.setOutput('trend_artifact_name', resolvedTrendName);
            core.setOutput('history_artifact_name', resolvedHistoryName);
            core.setOutput('run_url', candidate.html_url || '');
            const url = candidate.html_url || 'no url';
            core.notice(`Using Gate workflow run ${candidate.id} (${url})`);

      - name: Download coverage trend artifact
        if: ${{ steps.discover.outputs.trend_artifact_name }}
        id: coverage-trend-cache
        uses: ./.github/actions/artifact-cache
        with:
          cache-key-base: gate-coverage-trend-${{ steps.discover.outputs.run_id }}
          window-resolution: weekly
          artifact-name: ${{ steps.discover.outputs.trend_artifact_name }}
          artifact-path: coverage_artifacts/trend
          producer-run-id: ${{ steps.discover.outputs.run_id }}
          fail-fast: 'true'

      # Each immutable cache saves the accumulated history after this guard run.
      # Restore the newest repository history, independently of the producer run.
      - name: Restore coverage recovery history
        if: ${{ steps.discover.outputs.run_id }}
        id: coverage-trend-history-cache
        uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
        with:
          path: coverage_artifacts/history
          key: coverage-guard-history-v1-${{ github.repository }}-${{ github.run_id }}-${{ github.run_attempt }}
          restore-keys: |
            coverage-guard-history-v1-${{ github.repository }}-

      - name: Download coverage payload artifact
        if: ${{ steps.discover.outputs.coverage_artifact_name }}
        id: coverage-payload-cache
        uses: ./.github/actions/artifact-cache
        with:
          cache-key-base: gate-coverage-${{ steps.discover.outputs.run_id }}
          window-resolution: weekly
          artifact-name: ${{ steps.discover.outputs.coverage_artifact_name }}
          artifact-path: coverage_artifacts/payload
          producer-run-id: ${{ steps.discover.outputs.run_id }}
          fail-fast: 'true'

      - name: Run coverage guard
        if: ${{ steps.discover.outputs.run_id }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          COVERAGE_RUN_URL: ${{ steps.discover.outputs.run_url }}
          COVERAGE_RUN_NUMBER: ${{ steps.discover.outputs.run_number }}
        run: |
          # Try multiple possible artifact paths (workflow uses different naming)
          TREND_PATH=""
          COVERAGE_PATH=""
          HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"

          # Check for trend artifact
          for candidate in \
            "coverage_artifacts/trend/coverage-trend.json" \
            "coverage_artifacts/coverage-trend.json"; do
            if [ -f "$candidate" ]; then
              TREND_PATH="$candidate"
              break
            fi
          done

          # Check for trend history artifact
          for candidate in \
            "coverage_artifacts/history/coverage-trend-history.ndjson" \
            "coverage_artifacts/trend/coverage-trend-history.ndjson" \
            "coverage_artifacts/coverage-trend-history.ndjson"; do
            if [ -f "$candidate" ]; then
              HISTORY_PATH="$candidate"
              break
            fi
          done

          # Check for coverage json
          # THE ARTIFACT IS FOUND AND THE FILE INSIDE IT IS NOT. This list is the same shape of
          # defect as the artifact-NAME list one step earlier: seven hardcoded paths against a
          # producer that writes somewhere else. Verified 2026-08-30 by downloading
          # stranske/Counter_Risk's real `gate-coverage-3.12-1` -- it holds `index.ndjson` and
          # `runtimes/3.12/coverage.json`, extracting to
          # `coverage_artifacts/payload/runtimes/3.12/coverage.json`, one directory level from the
          # first candidate and matched by none of them. The list also hardcodes the Python
          # versions, so a matrix change breaks it silently and later.
          #
          # Literals first, so a repo where they already work is untouched and this change cannot
          # alter a working resolution. Then FIND the payload rather than guess where it is: a
          # file is the payload when it PARSES and carries `totals.percent_covered`, which is what
          # the guard actually reads. That test cannot drift from the producer's directory layout,
          # because it does not mention the layout.
          for candidate in \
            "coverage_artifacts/payload/coverage/runtimes/3.14/coverage.json" \
            "coverage_artifacts/payload/coverage/runtimes/3.13/coverage.json" \
            "coverage_artifacts/payload/artifacts/coverage/runtimes/3.14/coverage.json" \
            "coverage_artifacts/payload/artifacts/coverage/runtimes/3.13/coverage.json" \
            "coverage_artifacts/payload/gate-coverage.json" \
            "coverage_artifacts/payload/coverage.json" \
            "coverage_artifacts/coverage.json"; do
            if [ -f "$candidate" ]; then
              COVERAGE_PATH="$candidate"
              break
            fi
          done
          # `sort` so an artifact holding two runtimes resolves to the SAME file every run: they
          # are one suite on different interpreters, and a figure that moved with directory order
          # would be noise reported as a coverage change.
          if [ -z "$COVERAGE_PATH" ]; then
            while IFS= read -r found; do
              if python -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if isinstance(d,dict) and 'percent_covered' in (d.get('totals') or {}) else 1)" "$found" 2>/dev/null; then
                COVERAGE_PATH="$found"
                echo "::notice title=Coverage payload located by search::No known path matched; found ${found} by looking for a JSON carrying totals.percent_covered."
                break
              fi
            done < <(find coverage_artifacts -type f -name '*.json' 2>/dev/null | sort)
          fi

          # Build args
          ARGS=(
            --repo "${{ github.repository }}"
            --run-url "${{ steps.discover.outputs.run_url }}"
          )

          if [ -n "$TREND_PATH" ]; then
            ARGS+=(--trend-path "$TREND_PATH")
          fi

          if [ -n "$COVERAGE_PATH" ]; then
            ARGS+=(--coverage-path "$COVERAGE_PATH")
          fi

          if [ -n "$HISTORY_PATH" ]; then
            ARGS+=(--history-path "$HISTORY_PATH")
          fi

          if [ -f "config/coverage-baseline.json" ]; then
            ARGS+=(--baseline-path "config/coverage-baseline.json")
          fi

          if [ -z "$TREND_PATH" ] || [ -z "$COVERAGE_PATH" ]; then
            echo "Required coverage artifacts are missing after download."
            echo "TREND_PATH=${TREND_PATH:-<missing>}"
            echo "COVERAGE_PATH=${COVERAGE_PATH:-<missing>}"
            # WHAT WAS ACTUALLY THERE. Without this, the message says a file is missing and gives
            # no way to tell "the artifact was empty" from "the artifact was full and nothing in
            # it looked like a coverage report" -- and the second is what really happened.
            echo "--- files downloaded (the search covered every .json among these) ---"
            find coverage_artifacts -type f 2>/dev/null | head -50 || echo "(coverage_artifacts is absent or empty)"
            exit 1
          fi

          python tools/coverage_guard.py "${ARGS[@]}"

      - name: Save coverage recovery history
        if: ${{ always() && steps.discover.outputs.run_id && hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson') != '' }}
        uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
        with:
          path: coverage_artifacts/history
          key: ${{ steps.coverage-trend-history-cache.outputs.cache-primary-key }}

  # A SKIPPED GUARD USED TO BE INDISTINGUISHABLE FROM A PASSING ONE. `guard` is gated on the
  # rate-limit job, so when quota is low the job is skipped and the WORKFLOW IS GREEN with nothing
  # checked. stranske/Workflows' three most recent runs all read `success` at the workflow level
  # and `coverage baseline monitor: skipped` at the job level -- which is how a monitor that has
  # never once executed came to look healthy for months. This job always runs and says which
  # happened, so the run's own summary distinguishes "checked, and it was fine" from "did not
  # check". It deliberately does NOT fail on a deferral: the quota gate is legitimate, and turning
  # a deferral into a red would train everyone to ignore the red.
  report:
    name: coverage guard outcome
    needs: [rate-limit-check, guard]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Record whether the guard actually evaluated
        env:
          PROCEED: ${{ needs.rate-limit-check.outputs.proceed }}
          GUARD_RESULT: ${{ needs.guard.result }}
        run: |
          if [ "${GUARD_RESULT}" = "skipped" ]; then
            if [ "${PROCEED}" = "true" ]; then
              REASON="the guard job was skipped for a reason other than API quota"
            else
              REASON="API quota was below the threshold, so the check was deferred"
            fi
            {
              echo "### Coverage guard: NOT EVALUATED"
              echo ""
              echo "Coverage was **not** checked on this run - ${REASON}."
              echo "A green run here does not mean coverage is healthy."
            } >> "$GITHUB_STEP_SUMMARY"
            echo "::notice title=Coverage guard not evaluated::${REASON}"
          else
            echo "### Coverage guard: evaluated (${GUARD_RESULT})" >> "$GITHUB_STEP_SUMMARY"
          fi

```

### config/template-drift-allowlist.txt @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
# Baseline allowlist for Health 74 Template Drift.
#
# Each entry permits exactly one current normalized main/template content pair.
# If either file changes, the fingerprint no longer matches and Health 74 fails
# until the template is aligned or this baseline is deliberately re-reviewed.
#
# 2026-07-24b re-baseline: fingerprints regenerated after check_template_drift.py
# gained action-pin canonicalization (uses:<action>@<ref> collapses to @<pinned>).
# From here, Renovate action-pin bumps and the intentional pinned-vs-floating
# divergence no longer change these fingerprints, so this allowlist stops going
# stale on dependency bumps; only a genuine logic change to a root workflow will.
#
# 2026-08-05 re-baseline: auto-label now isolates the preliminary eligibility
# sparse checkout under eligibility-source/ in both root and consumer workflows.
# The remaining root/template differences are the already-reviewed consumer
# action-pin and auth-plumbing contract.
#
# 2026-07-24 re-baseline: refreshed fingerprints for 13 entries (belt 71/72/73,
# auto-label, autofix-dispatcher, capability-check, decompose, dedup, guard,
# issue-optimizer, keepalive-loop-reporter, verifier, weekly-metrics) that went
# stale after Renovate action-pin/dep bumps (#2799 actions/checkout v7.0.1;
# #2776 coverage pins) moved the consumer templates' pinned SHAs. Verified via
# git log that the ONLY commits touching these since the last baseline were those
# dep bumps (root workflows keep floating major tags), so the divergence remains
# the intentional action-pin-contract drift, not a missing consumer improvement.
#
# 2026-06-24 re-baseline: refreshed the consumer template fingerprints for
# auto-label, capability-check, decompose, dedup, issue-optimizer, and
# weekly-metrics after the setup-python v6 digest moved to ece7cb0. The root
# workflows intentionally continue using floating major tags.
#
# 2026-06-14 re-baseline: refreshed the fingerprints of 7 entries (issue-intake,
# auto-label, capability-check, decompose, dedup, issue-optimizer, weekly-metrics)
# that went stale after action-version bumps (#2391/#2394) and root feature work.
# The divergence is intentional, not a missing consumer improvement: consumer
# template workflows SHA-pin third-party actions per the fleet action-pin contract
# (docs/HISTORY.md, PR #1925) and carry LangSmith tracing env, while the root
# Workflows-repo copies use floating major tags plus repo-internal concurrency +
# sparse-checkout (docs/fixes/sparse-checkout-audit-2026-02-03.csv). Aligning the
# template to root would strip the contractually-required consumer action pins, so
# these are re-baselined rather than aligned.

[pair.1]
main = .github/workflows/agents-63-issue-intake.yml
template = templates/consumer-repo/.github/workflows/agents-issue-intake.yml
main_sha256 = 178b989ad293ed25574bfa284969bdad5bf48672def44eef814140cf3458896b
template_sha256 = ce596e51840779fb3f2375b9fbfe3657be8553016ccd0852b1f9b3fc6b907c7a
divergence = Round 5 re-reviewed 2026-10-17: compared .github/workflows/agents-63-issue-intake.yml with templates/consumer-repo/.github/workflows/agents-issue-intake.yml. Consumer sync delegates to the root workflow at @main and therefore inherits the bot-receipted verifier-closure replay guard; root normalization/preflight and invite mode versus consumer routing/label checks and create mode, input surfaces and action pins remain intentional. No duplicate consumer sync implementation is needed. Prior history: Round 4 review 2026-10-17: clean origin/main 8fab8cb451da124beaa31ed89f7abc8194fdb99d passes drift (this mismatch is PR-specific). Root chatgpt_sync now preserves bot-receipted verifier closures during seed replay; the consumer sync job delegates to stranske/Workflows/.github/workflows/agents-63-issue-intake.yml@main, so it inherits that guard without duplicating implementation. Consumer route/check_labels and bridge/create dispatch remain distinct from root normalize_inputs/bridge_preflight and bridge/invite; existing action pins and input surfaces remain intentional. Prior history: Receipt dependency delivery 2026-10-17: both authored policy sparse checkouts include the JS helper and JSON TTL; executable checkout-payload tests verify both imports, helper behavior, and separate missing-file controls. Existing architecture and action-pin divergence unchanged; divergence_reviewed retained. Prior review: Drain review 2026-10-16: both read-only policy checkouts disable credential persistence; existing root/consumer architecture and action pin differences remain unchanged. Prior review: Intake review fixes 2026-10-16: both surfaces guard registry/module/export failures and use the actual registry loader; root retains its exactly-one-label contract and bridge-input precedence, while the minimal consumer retains its existing label routing. Root defers the empty bridge default to preflight. Existing architectural divergence is unchanged; divergence_reviewed is retained. Prior change: Route-weights intake chooser 2026-10-16: both root and consumer intake workflows resolve DEFAULT_AGENT via chooseAgentForIntake when bridge_agent is empty and log the decision to the step summary; divergence_reviewed is retained. Prior divergence: Agent-neutral intake input 2026-10-16: root gains post_agent_comment (post_codex_comment kept as an alias); the consumer template caller keeps its own input surface, so this is the only new divergence and divergence_reviewed is retained. Prior divergence: Workflows-only artifact retention reviewed 2026-10-13 for issue3844: root intake debug uploads now retain30days; consumer wrappers retain their repository-specific settings. Prior divergence: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-reviewed 2026-08-16: root and consumer intake surfaces both remove the operator draft toggle and always hand off ready-for-review automation PRs; root retains its richer failure summary while the consumer remains a pinned, minimal bridge contract.
divergence_reviewed = 2026-10-17
fingerprint_refreshed = 2026-10-17

[pair.2]
main = .github/workflows/agents-71-codex-belt-dispatcher.yml
template = templates/consumer-repo/.github/workflows/agents-71-codex-belt-dispatcher.yml
main_sha256 = ecdeda26e3c26a6df2de3524210158a9bcc624f17b01e005b4e064436fd92a7a
template_sha256 = b8ad87005dfda0db96dd3b1b16259c3fae04752bf6afcddc20f62ef47d894426
divergence = Root-only Health 40 claim recovery 2026-09-24 plus belt ready-label contract: the Workflows-local dispatcher imports the shared stale-claim timeout and advertises reclaim via Health 40 while both surfaces load belt-labels.json for ready/in-progress transitions and empty-queue discrimination. The consumer template has no Health 40 reclaim workflow and therefore must not promise that local behavior; consumer action pins and Codex-specific wording remain preserved. Prior divergence re-baselined 2026-08-16 for workflow_dispatch input handling; that prior divergence is unchanged and was not re-reviewed here.
divergence_reviewed = 2026-08-16
fingerprint_refreshed = 2026-09-24

[pair.3]
main = .github/workflows/agents-72-codex-belt-worker.yml
template = templates/consumer-repo/.github/workflows/agents-72-codex-belt-worker.yml
main_sha256 = 1026f820c615404486f7473f14710d52d5672b3697a22abcadecbca0667ccce4
template_sha256 = 95b7a5f8996577b1afa0d353d84ae437ab07afd32ae3ec31aca12aedf305c1bf
divergence = Post-checkout label-config repair 2026-09-24: root and consumer workers now load the shared belt label config from the preserved .belt-tools checkout after switching to an issue branch, so older branches cannot fail with MODULE_NOT_FOUND during status transitions. Applied identically while preserving consumer action pins and guarded-merge wording; existing divergence unchanged and not re-reviewed. Prior divergence: Belt ready-label contract 2026-09-24: root and consumer workers now load the shared belt label config for readiness checks and label transitions while preserving consumer action pins and guarded-merge wording. Existing divergence unchanged and not re-reviewed. Prior divergence: Current-transition evidence scope 2026-09-24: root and consumer final validators both pass the selected task id so historical completion debt remains audit-only and cannot block persistence of a new done/blocked result. Applied identically while preserving consumer action pins and consumer-specific guarded-merge wording; the prior divergence remains unchanged and was NOT re-reviewed. Prior divergence: Belt completion deferral 2026-09-24: root and consumer workers record start_sha after the in-progress ledger commit and evaluate substantive agent commits in start_sha..HEAD before marking done/blocked, leaving tasks doing when only ledger commits exist. Applied identically while preserving consumer action pins and consumer-specific guarded-merge wording. Prior divergence: Belt completion-evidence hardening 2026-09-23: substantive cited commit, named-artifact verification, blocked insufficient evidence, duplicate artifact rejection, full task-state counts, and final-validation gating. Prior divergence: client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Prior divergence unchanged: Named-secrets rollout 2026-08-23: both surfaces now pass the eight named setup-api-client secret inputs instead of the whole-secrets-context blob. Prior divergence unchanged: Intentional divergence re-reviewed 2026-06-20: exported Orchestrator skill inputs were added to both root and consumer worker workflow_call surfaces while preserving consumer action pinning and guarded merge wording.
divergence_reviewed = 2026-06-20
fingerprint_refreshed = 2026-09-24

[pair.4]
main = .github/workflows/agents-73-codex-belt-conveyor.yml
template = templates/consumer-repo/.github/workflows/agents-73-codex-belt-conveyor.yml
main_sha256 = 0e1002a98faad1c4444923a7924dc2fd2a1e4f0115d074cd130e8f35e3209033
template_sha256 = 07d5ef489140f7d55a6733d4e1c73d5d3bc17bad33ce9df216767ecb1395be79
divergence = client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its old date. Prior divergence unchanged: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-reviewed 2026-08-10: root conveyor labels Gate and changed-file checks as authoritative; the consumer adds explicit best-effort rationale for only post-merge cleanup calls while preserving its action pins and Codex-specific behavior.
divergence_reviewed = 2026-08-10
fingerprint_refreshed = 2026-08-24

[pair.5]
main = .github/workflows/agents-auto-label.yml
template = templates/consumer-repo/.github/workflows/agents-auto-label.yml
main_sha256 = 6cfcfec322642a8a68e460c88060ab0328227f235e1b6314cd7f147726889bac
template_sha256 = f747501ebf28bec4589f1c873fbef4faaae9e86a26a4fd80b78b6656c2d46ace
divergence = Bounded suggestions display 2026-08-31: both surfaces now derive suggestions from bounded_diverse_matches excluding auto-apply winners instead of re-scanning the full match list, applied identically to root and consumer. Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its prior date. Prior divergence unchanged: Label-matcher margin-check fix 2026-08-31: both surfaces now pass diverse=False into find_similar_labels for the auto-apply margin gate and apply bounded_diverse_matches only to the suggestions display, applied identically to root and consumer. Prior divergence unchanged: Intentional divergence re-reviewed 2026-08-31: root and consumer workflows both use the bounded shared matcher and issue-safe auto-apply gate while retaining root sparse-checkout plus App-token setup and consumer SHA-pinned actions plus token-aware retry plumbing. Do not align wholesale: that would strip the consumer security contract.
divergence_reviewed = 2026-08-31
fingerprint_refreshed = 2026-10-02

[pair.6]
main = .github/workflows/agents-autofix-dispatcher.yml
template = templates/consumer-repo/.github/workflows/agents-autofix-dispatcher.yml
main_sha256 = c7e2b1e144b7d16c030569bcddc35590bece7d87e74d65cf6a2be1682290485d
template_sha256 = 05531a5b52a65d97b35964d6faac5624de8605bc9f639b97c6ee6fe61d325705
divergence = client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its old date. Prior divergence unchanged: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-reviewed 2026-08-23: the Workflows-local dispatcher resolves and invokes the in-repository reusable autofix surface, while the consumer wrapper uses the published Workflows workflow with pinned actions and consumer secret wiring. Do not align wholesale because that would remove the consumer deployment contract.
divergence_reviewed = 2026-08-23
fingerprint_refreshed = 2026-08-24

[pair.7]
main = .github/workflows/agents-capability-check.yml
template = templates/consumer-repo/.github/workflows/agents-capability-check.yml
main_sha256 = d98c5ea59961e8776b4da0584f7f4e6ec864c6c348a84d6451ee4a8decbbe72e
template_sha256 = 647591e3d88f42d4347ac4e1a5c672b7d1209a89d69077e7f4afccc575824f4b
divergence = Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-baselined 2026-08-22 after both surfaces migrated from the retired check_capability alias to classify_capabilities. The consumer template retains SHA-pinned actions and LangSmith tracing while the root workflow retains in-repo concurrency and sparse-checkout plumbing; do not align wholesale because that would strip the consumer security contract.
divergence_reviewed = 2026-08-22
fingerprint_refreshed = 2026-10-02

[pair.8]
main = .github/workflows/agents-decompose.yml
template = templates/consumer-repo/.github/workflows/agents-decompose.yml
main_sha256 = 1105cd9791715120b2bd9179643f9172507cd029e799720d4880239aa2850499
template_sha256 = 14245c7a9644314f9bf4beeb0e4d735f6e43daaad086b1798579be26d5483ffe
divergence = Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-baselined 2026-08-09: root-only warning-only REST triage marker added; do not align wholesale because consumer pins and retry plumbing are contractually distinct.
divergence_reviewed = 2026-08-09
fingerprint_refreshed = 2026-10-02

[pair.9]
main = .github/workflows/agents-dedup.yml
template = templates/consumer-repo/.github/workflows/agents-dedup.yml
main_sha256 = 4a62e0a14579368b45f09e40b92d5426bafa9ec3221f09214da4d516f2995d6c
template_sha256 = 9fc79a43443aadb0ff03bed4cbf592047f452c90bcf2a5647552e64d008fc57c
divergence = Root sparse-checkout now also fetches pyproject.toml, README.md, scripts/__init__.py and scripts/langchain; without them `pip install -e ".[langchain]"` failed and `from scripts.langchain.issue_dedup import ...` could not resolve, so the job could never complete - hidden for 22 days by GitHub's suspicious-workflow hold. Root only: the consumer template does a full checkout and already guards the install for consumers that are not installable packages. Prior divergence unchanged: Intentional divergence (re-baselined 2026-08-23): both surfaces now pass the eight named setup-api-client secret inputs instead of `secrets: ${{ toJSON(secrets) }}`, applied identically to root and consumer so the whole-secrets-context handoff is gone from both. Fingerprints refreshed for that change. The remaining divergence is unchanged and still intentional: consumer template SHA-pins third-party actions per the fleet action-pin contract (docs/HISTORY.md, PR #1925) and sets LangSmith tracing env; root uses floating major tags with repo-internal concurrency + sparse-checkout (docs/fixes/sparse-checkout-audit-2026-02-03.csv). Do not align: would strip consumer action pins.
divergence_reviewed = 2026-08-23
fingerprint_refreshed = 2026-10-02

[pair.10]
# 2026-10-14: fork pull_request status publication is now gated on explicit
# same-repository identity while preserving trusted pull_request_target behavior.
# Applied to both surfaces; existing consumer pins/App setup and prior divergence remain unchanged.
# 2026-10-15: evaluated policy-label digest/output and attempt metadata step added
# identically; existing divergence and its review date remain unchanged.
main = .github/workflows/agents-guard.yml
template = templates/consumer-repo/.github/workflows/agents-guard.yml
main_sha256 = 77b859cd2f2fa520910af1d77685e93c4c800b9652abaac0353d6a964ac4aa6f
template_sha256 = 8eff91e77fc2451824d7cce45600620404f8c56680029b5210a22ff96bac893a
divergence = Explicit registry enabled requirement 2026-10-16: identical eight-parser finish-entry validation and current PR/run/attempt binding for registry-error corrective publication, with actions read for run evidence and REST ref-suffixed path/canonical workflow identity binding; existing source/consumer divergence unchanged and not re-reviewed. Prior divergence: Trusted registry retry/failure publication 2026-10-16: identical helper and inline publisher transforms applied to root and consumer; existing consumer pins/App-token setup divergence unchanged and not re-reviewed. Prior divergence: client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its old date. Prior divergence unchanged: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-baselined 2026-06-30: root and consumer guard workflows differ for pinned consumer actions/App-token setup; stranske/Workflows digest pins were refreshed together in root and consumer guard surfaces after Renovate moved the Workflows digest to ebef44a.
divergence_reviewed = 2026-06-30
fingerprint_refreshed = 2026-10-15

[pair.11]
# 2026-09-02: refreshed after recursion-guard comment accuracy fix; root and consumer
# retain their established in-tree versus sparse-checkout issue-update implementations.
main = .github/workflows/agents-issue-optimizer.yml
template = templates/consumer-repo/.github/workflows/agents-issue-optimizer.yml
main_sha256 = bc8581f816b12b6d6fcca88ab967776dd792fc99f4b5e812de1de7bcb7f773ad
template_sha256 = 80c487e21c16c869795cf00ff1233d9fb205c73e482850f156f461445e348233
divergence = LANGCHAIN_MODEL 2026-09-30: both surfaces moved the inline optimizer model from claude-sonnet-4-5-20250929 to claude-sonnet-5-5, applied identically; no new divergence, divergence_reviewed retained. Prior divergence: client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its old date. Prior divergence unchanged: Fingerprints refreshed 2026-08-24: both surfaces now link recursion-pause comments to the managed WORKFLOW_USER_GUIDE recovery section instead of a nonexistent Agents.md anchor. The Workflows-local surface links to templates/consumer-repo/WORKFLOW_USER_GUIDE.md because there is no root guide, while the distributed consumer links to its root WORKFLOW_USER_GUIDE.md. Prior fingerprint refresh 2026-08-24: both surfaces treat automated issues as format-ineligible, complementing the shared guard cleanup that removes stale agents:format leases from exempt issues. Underlying divergence re-reviewed 2026-08-23: root remains in-tree (scripts/langchain + .github/scripts/issue_format.py); consumer vendors those via Workflows sparse-checkout under workflows-scripts/. Do not align wholesale — that would strip consumer action pins/token setup.
divergence_reviewed = 2026-08-23
fingerprint_refreshed = 2026-09-30

[pair.12]
main = .github/workflows/agents-keepalive-loop-reporter.yml
template = templates/consumer-repo/.github/workflows/agents-keepalive-loop-reporter.yml
main_sha256 = e59f57b56a9b334a5a135daca87884f589464484a8bcb17110fa9c501169515b
template_sha256 = 6f7cdd8cc53162020f71e7c6b090789844333176777b935b24a33d072e353ef2
divergence = Cancelled index-free reporter skip 2026-10-13: identical cancellation guard added to both resolver scripts; prepared-receipt cancellation reconciliation and failed-run alarms preserved. Existing root subscriptions and consumer fingerprints remain unchanged. Prior divergence: Conflict reconciliation 2026-10-11: preserve main skip diagnostics and branch unresolved-error outcomes together; no new permissions or authority. Unresolved-run diagnostics 2026-10-11: identical read-only resolver summaries and outcomes added to both surfaces, preserving the existing root subscription/setup and consumer state-fingerprint/action-pin differences. Normalized hashes refreshed; original divergence review retained. Prior divergence: Reporter replay hardening 2026-10-01: both reporters select the resolved lock PR for replay, require completed workflow runs before reconciliation, preserve any successful projection across the replay loop, and isolate workflow_run replay errors while manual dispatch remains fail-closed. Applied identically while preserving the root subscription/setup and consumer fingerprint/action-pin deployment differences; the underlying divergence was not re-reviewed. Prior divergence: Durable authority replay 2026-10-01: both reporters expose a PR-bound manual replay entry, reconcile current ledger obligations before event-specific work, and bypass consumer fingerprint suppression for replay. Applied identically while preserving the root subscription/setup and consumer fingerprint/action-pin deployment differences; the underlying divergence was not re-reviewed. Prior divergence: Checkout credential hardening 2026-09-30: both new resolver and reporter checkouts disable credential persistence, addressing the two exact security-review findings while retaining read-only classification and App-token mutation. Applied identically; the underlying source/consumer deployment divergence was not re-reviewed. Prior divergence: PR-keyed reporter serialization 2026-09-30: both reporters now resolve the canonical PR in a read-only job, serialize mutations on that PR, and preserve the ordinary-target classification separately. Applied identically while retaining the Workflows root subscription/setup and consumer state-fingerprint/action-pin deployment differences; the underlying divergence was not re-reviewed. Prior divergence: Ordinary-target fingerprint persistence 2026-09-30: the consumer-only state-fingerprint store now receives the same recovered PR number as its compare step, preserving the documented consumer fingerprint deployment without adding that machinery to the Workflows-root reporter. The underlying divergence was not re-reviewed. Prior divergence: Superseded recovery stop 2026-09-30: both reporters now return before ordinary summary publication when the shared applicability helper proves a reconciled attempt was superseded. Applied identically while preserving the existing root subscription/setup and consumer state-fingerprint/action-pin deployment differences; the underlying divergence was not re-reviewed. Prior divergence: Delayed authority recovery boundary 2026-09-29: both reporters call the shared, directly tested applicability helper for exact-attempt reconciliation and recovered-summary projection. Prior divergence: Non-consolidated authority recovery re-reviewed 2026-09-28: both reporters remain active for failed or cancelled originating workflows regardless of sweep mode. The Workflows root reporter subscribes to both Agents Gate Followups and Agents Keepalive Loop, while the consumer reporter subscribes only to Agents Gate Followups because both consolidated and non-consolidated consumer sweeps can dispatch that workflow. Root in-repo setup and consumer state fingerprinting with exact run attempt and SHA-pinned actions remain intentional. Do not align wholesale, because it would remove either the root workflow coverage or the consumer deployment contract.
divergence_reviewed = 2026-09-28
fingerprint_refreshed = 2026-10-13

[pair.13]
main = .github/workflows/agents-keepalive-sweep.yml
template = templates/consumer-repo/.github/workflows/agents-keepalive-sweep.yml
main_sha256 = 1168e59a986eac4984885ab14cbaf9eea2ebcaf7a4a0012102ca3df4adf798a3
template_sha256 = 186908d335843e5cc1577f3e8fffc33e8c58c45d78985e048acbb541620b1927
divergence = Reviewed 2026-10-18 for #4103: compared the complete root/template diff. Root has one sweep gated on USE_CONSOLIDATED_WORKFLOWS != true and dispatches agents-keepalive-loop.yml; consumer explicitly names both modes, dispatches agents-81-gate-followups.yml in each, and includes belt-claim reclaim because consumers lack root Health 40. All three sweep paths pass sweep_recheck=true so the shared loop re-evaluates startup-failure receipts. Consumer API task names, summaries, and mode guards reflect that topology. These routing and reclaim differences are intentional; making files identical would dispatch the wrong workflow or duplicate root reclaim.
divergence_reviewed = 2026-10-18
fingerprint_refreshed = 2026-10-18

[pair.14]
main = .github/workflows/agents-verifier.yml
template = templates/consumer-repo/.github/workflows/agents-verifier.yml
main_sha256 = 24a4d8325f27c6b343493030cf751a67455a260529f3826cc36efa725fb7f122
# 2026-10-10 context-limit repair: expanded v4 separates native input, context and
# actual output limits; standard remains v2. Execution-context divergence unchanged.
# 2026-10-10 all-arms repair: expanded v5 requires both configured results;
# standard v2 and the established execution-context divergence are unchanged.
# 2026-10-10 evidence allocation repair: expanded v7 retains the observed capture
# under a finite 524288-character ceiling. Root remains without state fingerprint;
# standard v2, native preflight and reviewed execution-context divergence unchanged.
# 2026-10-11 full-diff allocation repair: expanded v8 retains the 183-file
# snapshot under a finite ceiling; reviewed execution divergence is unchanged.
template_sha256 = 8fe357e1ae009fccbcc9ad108fa46d8488a7150a101f142fb5b6fe27012e7748
# 2026-10-11 FAIL preservation: expanded v9; execution-context divergence unchanged.
divergence = Inert launch correlation 2026-10-25: both callers declare and forward the same optional lowercase SHA-256 basis to the shared collector. Removing exactly those additions restores each accepted base byte-for-byte; existing CI/concurrency and consumer checkbox fingerprint architecture is unchanged. Fingerprints refreshed only; prior divergence review date retained. Prior history: Retained-output recovery 2026-10-24: both callers declare and forward the identical optional recovery selector to the same authenticated provider-free reusable path. Removing only those identical additions reproduces each caller at the accepted base byte-for-byte; existing root CI/concurrency and consumer checkbox-only fingerprint differences are unchanged. Fingerprints refreshed only; prior divergence review date retained. Prior history: Repeat-verification lifecycle re-reviewed 2026-10-23: both callers declare and forward identical event, necessary-material and predecessor inputs to the same reusable collector/evaluator; immutable acceptance-gates remain byte-for-byte identical. Root retains repository-specific post-merge CI, caller concurrency and no coarse fingerprint. Consumer retains its existing checkbox-only fingerprint machinery; model routes deliberately bypass it for authoritative post-collection event/assessment dedup, and incomplete evaluation cannot consume its fingerprint. These differences are intentional deployment architecture, not missing lifecycle logic; source/template were compared in full and semantic parity is regression-tested. Prior history: Acceptance control-file isolation 2026-10-22: identical invocation-owned temporary plan/result directories applied to both acceptance jobs. Normalized root/template divergence is byte-for-byte unchanged against 3cc1bed6; acceptance jobs remain identical. Fingerprints refreshed only; original divergence_reviewed and history retained. Prior history: Acceptance runtime isolation 2026-10-22: identical pinned Python 3.14 setup and fresh step-local virtual environment applied to both acceptance jobs; existing immutable checkout, dependency preparation and authored command execution preserved. Existing root/consumer execution differences unchanged and not re-reviewed. Prior history: Compare-profile documentation 2026-10-19: identical standard/expanded explanatory comments added to both callers; parsed workflow YAML is unchanged against the accepted base. Fingerprints refreshed only; established root/consumer execution differences and divergence_reviewed retained. Prior history: Issue 4083: acceptance-gates and close-sources changes match in both callers; required post-merge CI selection and consumer fingerprint jobs remain the existing intentional differences. Prior history: Merge reconciliation: retained main consumer plan-source dedup via verifier_plan_fingerprint.js alongside this PR's acceptance-gates and guarded source closure. Consumer-only fingerprint and repository-specific CI selection remain intentional. Prior history: Round 5 re-reviewed 2026-10-17: compared .github/workflows/agents-verifier.yml with templates/consumer-repo/.github/workflows/agents-verifier.yml. Immutable-merge acceptance-gates match and source-closure logic matches except the intentional root pr-11-ci-smoke.yml/selftest-ci.yml versus consumer ci.yml selection. Consumer fingerprint check/skip/persist handling and root concurrency/documentation differences remain intentional; no closure logic is missing. Prior history: Round 4 review 2026-10-17: both callers add identical immutable-merge acceptance-gates and source-closure jobs. Root waits for pr-11-ci-smoke.yml and selftest-ci.yml; consumer waits for ci.yml, including the closing CI query; both exclude PR-only Gate. Consumer retains state-fingerprint check/skip/persist jobs with bounded-native-capacity-v10 expanded evidence (standard v2); root retains workflow concurrency and the LANGSMITH_API_KEY documentation comment. Consumer PR-number comment remains label-specific; root also names manual dispatch. Existing execution-context divergence is intentional; no missing closure logic. Prior history: Verifier security repair 2026-10-10: both callers retain the merged/exact-label target trigger with a node-scoped disposition, gate before checkout, execute trusted github.sha without credential persistence, use job-scoped permissions and explicitly map the six declared reusable secrets. Consumer-only fingerprint shell outputs now use env; fingerprint content and existing execution-context divergence are unchanged. Both hashes refreshed; original divergence review retained. Prior history: Native registry repair 2026-10-10: only expanded advances to bounded-native-capacity-v6 for strict configured facts. Standard v2, root hash, original review date and execution-context divergence are unchanged. Prior history: Expanded all-arms aggregation 2026-10-10: only the consumer expanded fingerprint advances to bounded-native-capacity-v5; standard v2 and existing execution-context divergence are unchanged. Template hash refreshed for this scoped contract change; the original divergence review date and prior history are retained. Prior history: Exact native recovery 2026-10-10: the consumer fingerprint changes only expanded to bounded-native-capacity-v3; standard retains v2. The root still has no state fingerprint. Reviewed changed behavior and refreshed the template hash without changing the established execution-context divergence or its original review date. Prior history: Native-capacity input contract 2026-10-10: the consumer existing state-ledger fingerprint adds bounded-native-capacity-v2 so prior expanded evaluations cannot suppress a changed evidence contract. The root has no state fingerprint path. This retains the existing execution-context divergence; only the changed template hash is refreshed, with the original divergence review retained. Prior history: Bounded input recovery 2026-10-06: both surfaces declare and pass the same standard/expanded evidence_profile. The consumer also fingerprints that input in its existing state-ledger path, which the root corpus caller does not implement. No new execution-context divergence; only fingerprints refreshed, original divergence review retained. Prior history: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence re-reviewed 2026-08-23: the Workflows verifier retains its local corpus and provider plumbing, while the consumer verifier calls the distributed surface with consumer-specific action pins and token setup. Do not align wholesale because those execution environments are intentionally different.
divergence_reviewed = 2026-10-23
fingerprint_refreshed = 2026-10-25

# 2026-10-11 discovery admission guard: expanded v10 rejects absent/malformed
# acceptance-source discovery; standard v2/execution divergence unchanged.

[pair.15]
main = .github/workflows/agents-weekly-metrics.yml
template = templates/consumer-repo/.github/workflows/agents-weekly-metrics.yml
main_sha256 = f73c20f665876d28b0c23ffe8e12603f843fd360a4871a7c10fce0e7bed37d0c
template_sha256 = b2f5e897e4a4f2ba6297ed3e75eaeb8652ec33326bc6830be0151baca90e4759
divergence = Timestamp-output repair 2026-08-30: root and consumer workflows now both prefix their weekly tracker write with Last successful write, applied while preserving the existing root/consumer execution differences. The divergence itself is unchanged and was NOT re-reviewed. Prior divergence unchanged: client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Prior divergence unchanged: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence (re-baselined 2026-07-14): consumer template SHA-pins third-party actions per the fleet action-pin contract (docs/HISTORY.md, PR #1925) and sets LangSmith tracing env; root uses floating major tags with repo-internal concurrency + sparse-checkout (docs/fixes/sparse-checkout-audit-2026-02-03.csv). Do not align: would strip consumer action pins.
divergence_reviewed = 2026-07-14
fingerprint_refreshed = 2026-08-30

[pair.16]
main = .github/workflows/agents-auto-pilot.yml
template = templates/consumer-repo/.github/workflows/agents-auto-pilot.yml
main_sha256 = e2b3692d8cba171c2290bc3051b0569e801b3bbabf9d063131a62a71051ad60d
template_sha256 = 9feb4605b37e6aad9dd1df5a355eb00ac9c7cf25ce60ef76656fa385009ce1a5
divergence = Belt credential filtering 2026-10-16: identical availability filtering and presence-only flags added to root and template; existing consolidated-consumer versus local dispatch differences unchanged, original review date retained. Prior divergence: Muse routing 2026-10-16: HAS_META_API_KEY env line added identically to root and consumer; no new divergence, divergence_reviewed retained. Prior divergence: LANGCHAIN_MODEL 2026-09-30: both surfaces moved the inline optimizer model from claude-sonnet-4-5-20250929 to claude-sonnet-5-5, applied identically; no new divergence, divergence_reviewed retained. Prior divergence: Formatter pause wakeup 2026-09-24: root and consumer auto-pilot surfaces now both preserve recovery labels, publish the pause issue as a job output, wait one bounded backoff, clear the pause, and redispatch the format step. The recovery behavior and pinned actions are applied identically; established root versus consumer execution-context differences remain unchanged and were not re-reviewed. Prior divergence: Formatter recovery 2026-09-24 added one unchanged-input retry, preserved both audits, released the current claim on repeat failure, and rendered integer progress banners. Prior divergence: Belt readiness write path 2026-09-24: root and consumer auto-pilot surfaces now apply the shared ready label with the selected agent label while preserving the consumer-only consolidated Agents 80/81 dispatch contract. Existing divergence unchanged and not re-reviewed. Prior divergence: client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its old date. Prior divergence unchanged: Fingerprints refreshed 2026-08-23: both surfaces now pass the named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer so it introduces no new divergence. Underlying divergence unchanged: Intentional divergence reviewed 2026-08-21: the Workflows-local auto-pilot retains Workflows-only PR-meta and keepalive fallbacks, while the consumer template dispatches only the consolidated Agents 80 and Agents 81 entry points.
divergence_reviewed = 2026-08-21
fingerprint_refreshed = 2026-10-16

[pair.17]
main = .github/workflows/autofix.yml
template = templates/consumer-repo/.github/workflows/autofix.yml
main_sha256 = 96c8131203431b7da850474e06fa169a2580fa5fa4759674be712ea408f17d16
template_sha256 = 73536de641ae21b89b5de24848a850e2753f5bc4d608f90498b44007fc2b8cfe
divergence = Timeout handling 2026-09-14: four identical conclusion-filter edits applied to source and consumer autofix; both still exclude cancellations. Verified the exact same transformation against origin/main on both sides. Fingerprints refreshed; existing divergence and its review date are unchanged. Prior divergence: Intentional divergence reviewed 2026-08-23: the Workflows source runs its local reusable autofix workflow and uses the repository's CI concurrency/context contract; the consumer template calls the published reusable workflow with SHA-pinned actions, SERVICE_BOT_PAT, and workflow-run PR context recovery. Do not align wholesale because the consumer is a deployable wrapper rather than the source implementation.
divergence_reviewed = 2026-08-23
fingerprint_refreshed = 2026-09-14

[pair.18]
main = .github/workflows/maint-coverage-guard.yml
template = templates/consumer-repo/.github/workflows/maint-coverage-guard.yml
main_sha256 = da0d24f4739dd2a6e4d9df70b4a0edf418bb6e1e8667fe3137fe84302559cfea
template_sha256 = 0aafdbd27b50b1116c724e90d870ef04a558f5403bdd76601c36bfda02cbff87
divergence = Recovery history 2026-10-26: identical repository-scoped restore/save and default history-path changes applied to both surfaces; consumer App tokens, pinned actions and artifact downloads remain unchanged. Fingerprints refreshed only; original divergence review date retained. Prior divergence unchanged: Round 2 Python matrix 2026-10-17: runtime/coverage changes applied identically to root and template; existing consumer wiring and action-pin divergence unchanged. Guard FINDS the report inside the artifact 2026-08-30, AND CORRECTS THE CLAIM BELOW. The note that follows says matrix artifacts extract to `payload/coverage/runtimes/...`. They do not, and that is why the seven hardcoded candidate paths still matched nothing after the artifact NAME was fixed the same day. MEASURED by downloading three repos' real gate-coverage-3.12-1 artifacts (stranske/Counter_Risk, stranske/Pension-Data, stranske/trip-planner): every one contains `index.ndjson` and `runtimes/<ver>/coverage.json` with NO top-level `coverage/` directory, so the extracted path is `coverage_artifacts/payload/runtimes/3.12/coverage.json` -- one level from the first candidate and matched by none. The list also hardcoded Python 3.12/3.13, so a matrix bump would break it silently and later. Literals are still tried FIRST, so a repo where resolution already worked cannot be re-resolved by this change; failing that the payload is FOUND by the property the guard actually reads -- a JSON carrying totals.percent_covered -- which cannot drift from a directory layout it never mentions, and which correctly rejects the `summary.json` sibling that carries a `coverage` key but no totals. Results are sorted, so an artifact holding two runtimes resolves identically every run. The missing-artifact message now lists what was downloaded, because it could not distinguish an empty artifact from a full one whose contents it did not recognise -- and the second is what really happened, in every repo. Applied IDENTICALLY to root and consumer; fingerprints refreshed, divergence_reviewed keeps its date. Prior divergence unchanged: Review findings fixed 2026-08-30: matrix artifacts downloaded under payload extract to `payload/coverage/runtimes/...`, so both guards probe that actual layout before legacy layouts; the three failure states now separately report no coverage artifacts, unusable payload names, and a usable payload missing its same-run trend. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Guard matches the payload artifact by PREFIX 2026-08-30: the producer runs under a version matrix, so what it publishes is gate-coverage-3.12-1 and gate-coverage-3.13-1, while this job matched the exact names gate-coverage / gate-coverage.json. MEASURED 2026-08-30 across the lane fleet: EIGHT repos published a trend, a summary and both suffixed payloads -- everything the job needs -- and every one was skipped, which is why the guard had a failing run in all 13 repos. Two more literals would not have fixed it, so the match is by prefix with -trend/-summary/-delta excluded by name (a bare prefix would have selected the TREND as the payload and compared coverage against itself); exact names are still preferred first so a repo where this already worked is untouched, and multiple suffixed matches are SORTED because the API's listing order is not stable. The failure message was split into three findings, because "coverage is not measured here", "it is measured under a name I cannot use" and "a payload but no trend" have different fixes and the single message asserted the first in all three cases -- it told eight measuring repos to go and switch coverage on. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Guard reads a per-repo workflow list 2026-08-30: which workflow carries a repo's coverage is a PER-REPO fact and was hardcoded to pr-00-gate.yml, so two repos were invisible to the guard for the same reason and neither is misconfigured -- stranske/Counter_Risk measures coverage on ci.yml by documented judgement, and stranske/Orchestrator publishes its only honest figure (80.3% combined, against the 34.11% its Gate reports for pytest alone) from a ci.yml job, because 79 of its 102 modules run under --selftest subprocesses pytest-cov cannot see. Reading source_workflows from config/coverage-baseline.json puts the answer in the file that is already the per-repo coverage config and already excluded from sync. The default is exactly the previous behaviour and an unreadable config falls back to it, so no repo changes unless it opts in. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed for it and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Coverage guard fingerprint refreshed 2026-08-26: both root and consumer selectors now recognize the downloaded `coverage_artifacts/payload/gate-coverage.json` filename, preventing the source/template artifact-name mismatch from hiding usable Gate coverage. The remaining root/template differences are still intentional: consumers use pinned public actions and an App token while Workflows uses local artifact-cache helpers and sparse checkout. Prior divergence unchanged: Coverage guard re-reviewed 2026-08-25: both selectors require the trend artifact alongside the coverage payload, because coverage_guard.py makes a missing trend a successful no-op. Checkout 2026-10-16: the root guard job dropped its second, sparse 'Checkout retry helpers' step, which deleted tools/coverage_guard.py before 'Run coverage guard' ran (the guard could not measure for 20+ days); the template already had a single full checkout, so this change reduces the divergence. Fingerprints refreshed; the existing divergence and its review date are unchanged.
divergence_reviewed = 2026-08-25
fingerprint_refreshed = 2026-10-26

[pair.19]
main = .github/workflows/pr-00-gate.yml
template = templates/consumer-repo/.github/workflows/pr-00-gate.yml
main_sha256 = 47487015cb994f1b9876f1d601828a74fcea1ba3ed219855c337863f60288019
template_sha256 = 2546b252f4774f86e63259e2e1cff2af1320d1e22f0d2758cca621a674f49b14
divergence = Untrusted Gate diagnostics 2026-10-26: identical environment-based enforcement on root/template; seal and check requirements unchanged. Prior divergence unchanged: Nullable origin diagnostics 2026-10-26: both identical same-action summary preambles now tolerate a null repo object for identity comparison; wrong origins still reject and the existing stable-delivery seal refuses missing origin identity. Existing divergence and review date retained. Prior divergence unchanged: Same-action summary snapshot consumption 2026-10-25: identical identity-checked Python preamble and summary invocation now run in one action on both surfaces, surviving per-action event resets. Existing divergence and review date retained. Prior divergence unchanged: Exact-head mutable PR snapshot recovery 2026-10-25: the resolver and snapshot-restoration changes are applied identically to shared root/template jobs; independently reviewed existing source-only CI and consumer policy differences remain unchanged. Fingerprints refreshed; original divergence review date retained. Prior divergence unchanged: Round 2 Python matrix 2026-10-17: runtime/coverage changes applied identically to root and template; existing consumer wiring and action-pin divergence unchanged. Intentional divergence reviewed 2026-10-17: Upstream #3983 label-event removal, resolved same-repository dispatch PR context, non-cancelling manual dispatch concurrency, and summary behavior are preserved on both surfaces. Root canonical CI now enforces the full-suite 70% minimum formerly repeated by six optional-feature profiles; the consumer template retains its explicit per-repository coverage policy. Python parity uses 3.13/3.14, four workers and a 3.14 coverage reference on both surfaces. Root-only non-doc PR selection and matching PYTHON_REQUIRED preserve assertions moved out of the duplicate Selftest suite; consumer Gates retain their Python-path classification because they did not run that first-party Selftest suite. Root invokes the local reusable and same-commit helper; consumer invokes published @main without a consumer SHA as a Workflows ref. Existing source-only package/ledger/diff-quality/sync checks, pinned consumer actions and bootstrap-safe omissions remain intentional. Prior history: Intentional divergence reviewed 2026-10-06: Workflows-local helper pin; the root Gate invokes a local reusable workflow and now passes workflows_ref=${{ github.sha }} so its helper comes from the same tested commit. The consumer Gate invokes the published remote workflow and retains main; passing a consumer SHA into the Workflows checkout would be invalid. Only this additional source-only input was changed and reviewed; prior differences remain the documented consumer contract. Prior history: Explicit Gate success enforcement 2026-09-28: both Gates now reject every state other than literal success so missing, pending, neutral, or malformed summaries cannot be treated as passing. Applied identically; no new divergence, original divergence_reviewed retained. Prior history: Install-report isolation hardening 2026-09-20: both Gates identify the requested head distribution from the pip install report, supporting setup.py-only metadata, and fail closed on missing identity or uninstall failure before running archived-base tests. Applied identically; no new divergence, original divergence_reviewed retained. Prior history: Deliberate-break gate installs the project 2026-09-17: the test-quality job ran `pip install --upgrade pip pytest` and nothing else, so any PR whose named acceptance test imported a runtime dependency failed at pytest collection no matter how correctly the PR declared it -- a gate demanding a passing named test while refusing to create an environment that could run one. MEASURED on stranske/Deliverable-Render#20: `ModuleNotFoundError: No module named 'docx'` while pyproject.toml:24 declared python-docx==1.1.2, which then absorbed five autofix attempts against a threshold of three and sat on needs-human for two days. Both surfaces now install the project (editable, non-editable fallback, then the first requirements file present) and warn rather than fail when a repo is not pip-installable. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Fork read-only token tolerated 2026-09-06: both surfaces now let the summary job survive a read-only fork token on the two writes it makes -- the consolidated summary comment and the `Gate / gate` commit status -- warning and falling back to the job summary instead of rethrowing, so a fork PR with green CI reports the verdict it computed rather than a red Gate (observed in stranske/Fine-Art-Archive#716, run 34017696018). Keyed on the head repo differing from the base repo, so a same-repo 403 still fails loudly; #2278 recorded the opposite defect. Applied IDENTICALLY to root and consumer, so it introduces NO NEW divergence; fingerprints refreshed and divergence_reviewed deliberately keeps its old date. Prior divergence unchanged: Gate label catch annotated 2026-08-31: both surfaces note the acceptance-criteria label apply is best-effort, applied identically; fingerprints refreshed. Prior: Acceptance-criteria label step hardened 2026-08-31: both surfaces now catch API failures and use continue-on-error so installation rate limits cannot fail Gate after deliberate-break already passed, applied identically; fingerprints refreshed. Prior divergence unchanged: client-id rename 2026-08-24 and named-secrets rollout 2026-08-23 were applied identically. Prior divergence unchanged: Gate commit-status token pinned 2026-08-23: both surfaces pass `env: {}` to createTokenAwareRetry for the `gate-commit-status` call so credential rotation cannot select a token without statuses scope. Prior divergence unchanged: the source Gate retains Workflows-only package, ledger, diff-quality, and live sync-manifest checks; the consumer template uses published reusable workflows, pinned actions, and bootstrap-safe omissions.
divergence_reviewed = 2026-10-17
fingerprint_refreshed = 2026-10-26

[pair.20]
main = .github/workflows/reusable-pr-context.yml
template = templates/consumer-repo/.github/workflows/reusable-pr-context.yml
main_sha256 = 5737cde9fcd21c31c244eef632a5db469052d6e92dcc3a56f5bafebde83a12ab
template_sha256 = 4c9b90b908eaa50d982ce711f709c21725743559c76f303dd6240b6edcd1fb11
divergence = client-id rename 2026-08-24: every create-github-app-token step moved from the deprecated `app-id` input to `client-id`, applied identically to root and consumer, with the secret VALUE unchanged (the action forwards either input to the same appId slot -- main.js:21, lib/main.js:37). Fingerprints refreshed for that change; the divergence itself is unchanged and was NOT re-reviewed, which is why divergence_reviewed keeps its old date. Prior divergence unchanged: Named-secrets rollout 2026-08-23: both surfaces now pass named setup-api-client secret inputs instead of the whole-secrets-context blob, applied identically to root and consumer, and scoped to each workflow's DECLARED workflow_call secrets where that context is a closed set. Removing that handoff is the demonstrated remedy for GitHub's suspicious-workflow hold (agents-dedup then ran at run_attempt 1 with nothing approved after 22 days held). Prior divergence unchanged: Intentional divergence reviewed 2026-08-23: Workflows keeps local setup-api-client, cancellation, and full multi-agent label detection; the consumer uses pinned actions, App-token setup, and only the consumer-supported routing labels. These execution contexts are intentionally not byte-identical.
divergence_reviewed = 2026-08-23
fingerprint_refreshed = 2026-08-24

```

### docs/INTEGRATION_GUIDE.md @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
# Integration Guide: Using Workflows in Your Repository

This guide explains how to integrate the stranske/Workflows workflow library into your Python project.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Integration Methods](#integration-methods)
3. [Reusable Workflows](#reusable-workflows)
4. [Template Workflows](#template-workflows)
5. [Required Setup](#required-setup)
6. [Common Patterns](#common-patterns)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Minimal Setup (5 minutes)

1. **Create `.github/workflows/ci.yml`** in your repo:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.12'
```

2. **Commit and push** - CI will run on your next PR!

---

## Versioning Strategy

**`@main` is the single supported pin.** Reference every reusable workflow at
`@main`:

| Reference | When to use it | Behavior |
|-----------|----------------|----------|
| **Default branch (`@main`)** | The supported pin for all consumers. | Tracks the latest reusable workflow behavior used by the synced consumer templates. |
| **Pinned commit SHA** | Only for a one-off reproducible build or a controlled rollout you manage yourself. | Locked to a specific revision; **not** kept current and **unsupported** for ongoing use — the reusable's helper checkouts resolve against `main` (see below), so a SHA pin is no longer self-consistent. |

> **No floating version tags.** The repository previously published a floating
> `v1` tag (auto-refreshed to track `main`). That scheme has been **removed** —
> the `v1` tag never delivered isolation from `main` and added maintenance cost
> without benefit. Do not pin reusable workflows at the `v1` tag or any other
> tag; use `@main`.
>
> **Why `@main` is self-consistent and a SHA pin is not.** Inside
> `reusable-10-ci-python.yml`, the helper-code checkouts use `ref: main`
> intentionally (the helper layer is only validated as a unit on `main`). A
> caller pinned at `@main` therefore runs helper code that matches its pin. A
> caller pinned at an arbitrary SHA would still execute the helper scripts from
> `main`, so SHA pins are not supported for ongoing use.

Example (the supported pattern):

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.12'
```

---

## Integration Methods

### Method 1: Reusable Workflows (Recommended)

Call workflows directly from this library. Changes propagate automatically.

```yaml
jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.12'
    secrets: inherit
```

**Pros:**
- Always up-to-date
- No maintenance needed
- Consistent across repos

**Cons:**
- Less customizable
- Depends on external repo

### Method 2: Template Workflows

Copy templates from `/templates/` and customize for your project.

```bash
# Copy template to your repo
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/ci-basic.yml \
  -o .github/workflows/ci.yml
```

**Pros:**
- Full control
- No external dependencies
- Easy customization

**Cons:**
- Manual updates needed
- Can drift from best practices

First-party registered consumers use the managed form of this method. Maint 68
coalesces copied-file changes into stable candidate/delivery PRs, and Maint 71
alone merges them after bounded reviewer settlement, an exact-head seal, a
fresh Gate, a valid GitHub-generated commit signature, and zero active review
threads. Maint 68 fails before publishing any generated head whose API-created
tree or signature does not match the staged delivery. A reviewer capacity outage
cannot require responses from every configured bot or keep the PR open indefinitely.
Maint 71 requires one substantive response when available; it never waits for
all configured reviewers. A successful status
whose own description says the review was skipped or not performed is recorded
as unavailable, not as reviewer quorum. Generated-branch Gate completions wake
Maint 71 immediately; the durable campaign queue supplies the timed fallback for
review windows and pending checks. Complete exact-plan candidate evidence starts
promotion automatically while the stable candidate PRs remain open. Promotion
prepares the non-canary stable PRs; Maint 71 merges candidate and delivery heads
only after one fleet-wide exact-head authorization. Active review findings remain
held until resolved or covered by an authenticated exact-head Workflows
source-fix proof.

### Method 3: Hybrid Approach

Use reusable workflows for standard CI, templates for custom needs.

```yaml
jobs:
  # Standard CI via reusable workflow
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main

  # Custom job specific to your project
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./run-integration-tests.sh
```

---

## Reusable Workflows

### CI Workflows

| Workflow | Purpose | Inputs |
|----------|---------|--------|
| `reusable-10-ci-python.yml` | Full Python CI pipeline | `python-version`, `coverage-min` |
| `reusable-99-selftest.yml` | Run self-tests on workflow files | - |

## Workflow Outputs

Caller-facing outputs are available only from a subset of reusable workflows. The quick index below highlights the most common `workflow_call` outputs and artifact-only reusable workflows; consult the exhaustive catalog before assuming an unlisted workflow has no caller-facing outputs.

All registry-backed agent runners expose the optional provider-neutral
capability evidence outputs `capability-id`, `effect-fingerprint`,
`evidence-artifact-ref`, `supervision-mode`,
`capability-evidence-status`, and `terminal-disposition`. They are empty by
default and are accepted only as one complete validated record; callers must
not derive them from free-form agent output.

The exhaustive output reference is [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md). It documents each exported `workflow_call` output with its type, description, and usage expression, and it also lists reusable workflows that intentionally publish artifacts or logs without job outputs. Use that page as the source of truth when wiring dependent jobs; the table below is a quick index for the most common chaining surfaces.

Coverage evidence: `tests/workflows/test_reusable_workflow_outputs_doc.py` loads every `.github/workflows/reusable-*.yml` declaration, compares each `on.workflow_call.outputs` key and description against the catalog table, and verifies reusable workflows with no caller-facing outputs appear in the no-output list. That test is the audit guard for the acceptance requirement that all reusable workflow outputs are documented.

| Workflow | Outputs (name → description) |
|----------|-----------------------------|
| `reusable-16-agents.yml` | `readiness_report` → JSON payload from the readiness probe; `readiness_table` → Markdown table summarizing assignable agents. |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe`, `rate_limit_state`, `credential_pool_id`, `has_work`, `token_source`; keepalive/run toggles (`enable_keepalive`, `keepalive_pause_label`, `keepalive_round`, `keepalive_pr`, `keepalive_max_retries`, `keepalive_trace`); readiness/diagnostic toggles (`enable_readiness`, `readiness_agents`, `readiness_custom_logins`, `require_all`, `enable_preflight`, `enable_diagnostic`, `diagnostic_attempt_branch`, `diagnostic_dry_run`, `enable_verify_issue`, `verify_issue_number`, `verify_issue_valid_assignees`); bootstrap/worker settings (`enable_bootstrap`, `bootstrap_issues_label`, deprecated always-false `draft_pr`, `dispatcher_force_issue`, `worker_max_parallel`, `conveyor_max_merges`); misc orchestrator options (`codex_user`, `codex_command_phrase`, `enable_watchdog`, `dry_run`, `options_json`). |
| `reusable-10-ci-python.yml` | None (artifacts only: coverage, metrics, summaries). |
| `reusable-11-ci-node.yml` | None (artifacts only: coverage + junit when enabled). |
| `reusable-12-ci-docker.yml` | None (logs only). |
| `reusable-13-cross-repo-smoke.yml` | None (logs only). |
| `reusable-18-autofix.yml` | None (patch artifacts + summaries). |
| `reusable-70-orchestrator-main.yml` | None (consumes init outputs; exports status via summaries). |
| `reusable-agents-issue-bridge.yml` | None (bridge PR creation artifacts/logs). |

### Reusable workflow output audit

This guide now carries the issue #10 acceptance evidence directly. The audit covers every reusable workflow declaration under `.github/workflows/reusable-*.yml`; update the exhaustive catalog in [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md) first, then mirror changed rows here when adding, renaming, or removing a reusable workflow output.

Reusable workflows with caller-facing `workflow_call` outputs:

| Workflow | Output | Type | Description | Example |
| --- | --- | --- | --- | --- |
| `reusable-16-agents.yml` | `readiness_report` | string (JSON) | JSON report emitted by the readiness probe when enabled. | `needs.agents.outputs.readiness_report` |
| `reusable-16-agents.yml` | `readiness_table` | string (Markdown) | Markdown table emitted by the readiness probe when enabled. | `needs.agents.outputs.readiness_table` |
| `reusable-20-pr-meta.yml` | `keepalive_detected` | string (boolean-like) | Whether a keepalive comment was detected. | `needs.pr_meta.outputs.keepalive_detected` |
| `reusable-20-pr-meta.yml` | `keepalive_reason` | string | Reason for the keepalive dispatch decision. | `needs.pr_meta.outputs.keepalive_reason` |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe` | string (boolean-like) | Whether rate limit is safe to proceed. | `needs.orchestrator-init.outputs.rate_limit_safe` |
| `reusable-70-orchestrator-init.yml` | `rate_limit_state` | string | Rate-limit preflight state: `safe`, `low`, or `unknown`. | `needs.orchestrator-init.outputs.rate_limit_state` |
| `reusable-70-orchestrator-init.yml` | `credential_pool_id` | string | Non-secret pool consumed by idle-precheck, or the initial pool if deferred. | `needs.orchestrator-init.outputs.credential_pool_id` |
| `reusable-70-orchestrator-init.yml` | `has_work` | string (boolean-like) | Whether there is work to do. | `needs.orchestrator-init.outputs.has_work` |
| `reusable-70-orchestrator-init.yml` | `token_source` | string | Which token source downstream jobs should use. | `needs.orchestrator-init.outputs.token_source` |
| `reusable-70-orchestrator-init.yml` | `enable_readiness` | string (boolean-like) | Resolved flag for the readiness probe. | `needs.orchestrator-init.outputs.enable_readiness` |
| `reusable-70-orchestrator-init.yml` | `readiness_agents` | string | Comma-separated agent keys for readiness. | `needs.orchestrator-init.outputs.readiness_agents` |
| `reusable-70-orchestrator-init.yml` | `readiness_custom_logins` | string | Comma-separated custom logins for readiness. | `needs.orchestrator-init.outputs.readiness_custom_logins` |
| `reusable-70-orchestrator-init.yml` | `require_all` | string (boolean-like) | Whether readiness should fail if any requested agent is missing. | `needs.orchestrator-init.outputs.require_all` |
| `reusable-70-orchestrator-init.yml` | `enable_preflight` | string (boolean-like) | Resolved flag for the Codex preflight probe. | `needs.orchestrator-init.outputs.enable_preflight` |
| `reusable-70-orchestrator-init.yml` | `codex_user` | string | Codex connector login override for preflight or bootstrap. | `needs.orchestrator-init.outputs.codex_user` |
| `reusable-70-orchestrator-init.yml` | `codex_command_phrase` | string | Command phrase to post when triggering Codex. | `needs.orchestrator-init.outputs.codex_command_phrase` |
| `reusable-70-orchestrator-init.yml` | `enable_diagnostic` | string (boolean-like) | Resolved flag for the bootstrap diagnostic job. | `needs.orchestrator-init.outputs.enable_diagnostic` |
| `reusable-70-orchestrator-init.yml` | `diagnostic_attempt_branch` | string (boolean-like) | Whether the diagnostic attempts to create a branch. | `needs.orchestrator-init.outputs.diagnostic_attempt_branch` |
| `reusable-70-orchestrator-init.yml` | `diagnostic_dry_run` | string (boolean-like) | Whether the diagnostic runs in dry-run mode. | `needs.orchestrator-init.outputs.diagnostic_dry_run` |
| `reusable-70-orchestrator-init.yml` | `enable_verify_issue` | string (boolean-like) | Whether the issue-verification step should run. | `needs.orchestrator-init.outputs.enable_verify_issue` |
| `reusable-70-orchestrator-init.yml` | `verify_issue_number` | string (number-like) | Issue number to verify when issue verification is enabled. | `needs.orchestrator-init.outputs.verify_issue_number` |
| `reusable-70-orchestrator-init.yml` | `enable_watchdog` | string (boolean-like) | Resolved flag for watchdog checks. | `needs.orchestrator-init.outputs.enable_watchdog` |
| `reusable-70-orchestrator-init.yml` | `enable_keepalive` | string (boolean-like) | Resolved flag for keepalive sweeps. | `needs.orchestrator-init.outputs.enable_keepalive` |
| `reusable-70-orchestrator-init.yml` | `keepalive_pause_label` | string | Label name that pauses keepalive when present. | `needs.orchestrator-init.outputs.keepalive_pause_label` |
| `reusable-70-orchestrator-init.yml` | `keepalive_max_retries` | string (number-like) | Maximum keepalive retries permitted for the run. | `needs.orchestrator-init.outputs.keepalive_max_retries` |
| `reusable-70-orchestrator-init.yml` | `enable_bootstrap` | string (boolean-like) | Resolved flag for Codex bootstrap. | `needs.orchestrator-init.outputs.enable_bootstrap` |
| `reusable-70-orchestrator-init.yml` | `bootstrap_issues_label` | string | Label to select issues for bootstrap. | `needs.orchestrator-init.outputs.bootstrap_issues_label` |
| `reusable-70-orchestrator-init.yml` | `draft_pr` | string (boolean-like) | Deprecated compatibility output; always `false` because automation PRs are ready for review. | `needs.orchestrator-init.outputs.draft_pr` |
| `reusable-70-orchestrator-init.yml` | `verify_issue_valid_assignees` | string | Comma-separated logins considered valid for issue verification. | `needs.orchestrator-init.outputs.verify_issue_valid_assignees` |
| `reusable-70-orchestrator-init.yml` | `dry_run` | string (boolean-like) | Global dry-run toggle for downstream jobs. | `needs.orchestrator-init.outputs.dry_run` |
| `reusable-70-orchestrator-init.yml` | `options_json` | string (JSON) | Resolved options JSON passed to the orchestrator. | `needs.orchestrator-init.outputs.options_json` |
| `reusable-70-orchestrator-init.yml` | `dispatcher_force_issue` | string (number-like) | Forced issue number for the dispatcher, when set. | `needs.orchestrator-init.outputs.dispatcher_force_issue` |
| `reusable-70-orchestrator-init.yml` | `worker_max_parallel` | string (number-like) | Maximum parallel worker runs to allow. | `needs.orchestrator-init.outputs.worker_max_parallel` |
| `reusable-70-orchestrator-init.yml` | `conveyor_max_merges` | string (number-like) | Maximum merges the conveyor should perform. | `needs.orchestrator-init.outputs.conveyor_max_merges` |
| `reusable-70-orchestrator-init.yml` | `keepalive_trace` | string | Keepalive trace identifier propagated to downstream runs. | `needs.orchestrator-init.outputs.keepalive_trace` |
| `reusable-70-orchestrator-init.yml` | `keepalive_round` | string | Keepalive round identifier. | `needs.orchestrator-init.outputs.keepalive_round` |
| `reusable-70-orchestrator-init.yml` | `keepalive_pr` | string (number-like) | Keepalive target PR number, when set. | `needs.orchestrator-init.outputs.keepalive_pr` |
| `reusable-bot-comment-handler.yml` | `comments_found` | string (boolean-like) | Whether unresolved bot comments were found. | `needs.bot-comments.outputs.comments_found` |
| `reusable-bot-comment-handler.yml` | `comments_count` | string (number-like) | Number of unresolved bot comments found. | `needs.bot-comments.outputs.comments_count` |
| `reusable-bot-comment-handler.yml` | `agent_triggered` | string (boolean-like) | Whether the agent was triggered to address comments. | `needs.bot-comments.outputs.agent_triggered` |
| `reusable-bot-comment-handler.yml` | `app_auth_mode` | string enum | Selected App auth mode: client-id, legacy-app-id, or none. | `needs.bot-comments.outputs.app_auth_mode` |
| `reusable-pr-context.yml` | `pr_number` | string (number-like) | PR number. | `needs.pr-context.outputs.pr_number` |
| `reusable-pr-context.yml` | `pr_title` | string | PR title. | `needs.pr-context.outputs.pr_title` |
| `reusable-pr-context.yml` | `pr_body` | string | PR body, possibly truncated for very long bodies. | `needs.pr-context.outputs.pr_body` |
| `reusable-pr-context.yml` | `pr_state` | string | PR state: OPEN, CLOSED, or MERGED. | `needs.pr-context.outputs.pr_state` |
| `reusable-pr-context.yml` | `pr_is_draft` | string (boolean-like) | Whether the PR is a draft. | `needs.pr-context.outputs.pr_is_draft` |
| `reusable-pr-context.yml` | `pr_merged` | string (boolean-like) | Whether the PR is merged. | `needs.pr-context.outputs.pr_merged` |
| `reusable-pr-context.yml` | `pr_author` | string | PR author login. | `needs.pr-context.outputs.pr_author` |
| `reusable-pr-context.yml` | `head_ref` | string | Head branch name. | `needs.pr-context.outputs.head_ref` |
| `reusable-pr-context.yml` | `base_ref` | string | Base branch name. | `needs.pr-context.outputs.base_ref` |
| `reusable-pr-context.yml` | `head_sha` | string | Head commit SHA. | `needs.pr-context.outputs.head_sha` |
| `reusable-pr-context.yml` | `labels_json` | string (JSON array) | JSON array of label names. | `needs.pr-context.outputs.labels_json` |
| `reusable-pr-context.yml` | `has_agent_label` | string (boolean-like) | Whether the PR has any `agent:*` label. | `needs.pr-context.outputs.has_agent_label` |
| `reusable-pr-context.yml` | `has_keepalive_label` | string (boolean-like) | Whether the PR has the `agents:keepalive` label. | `needs.pr-context.outputs.has_keepalive_label` |
| `reusable-pr-context.yml` | `files_count` | string (number-like) | Number of changed files. | `needs.pr-context.outputs.files_count` |
| `reusable-pr-context.yml` | `files_json` | string (JSON array) | JSON array of changed file paths. | `needs.pr-context.outputs.files_json` |
| `reusable-pr-context.yml` | `has_src_changes` | string (boolean-like) | Whether changes include source files. | `needs.pr-context.outputs.has_src_changes` |
| `reusable-pr-context.yml` | `has_test_changes` | string (boolean-like) | Whether changes include test files. | `needs.pr-context.outputs.has_test_changes` |
| `reusable-pr-context.yml` | `has_workflow_changes` | string (boolean-like) | Whether changes include `.github/workflows/`. | `needs.pr-context.outputs.has_workflow_changes` |
| `reusable-pr-context.yml` | `ci_status` | string | Overall CI status, such as SUCCESS, FAILURE, or PENDING. | `needs.pr-context.outputs.ci_status` |
| `reusable-pr-context.yml` | `checks_json` | string (JSON array) | JSON array of check results. | `needs.pr-context.outputs.checks_json` |
| `reusable-pr-context.yml` | `full_context_json` | string (JSON) | Full PR context as JSON; use sparingly because it can be large. | `needs.pr-context.outputs.full_context_json` |
| `reusable-codex-run.yml` | `final-message` | string (base64) | Full Codex output message, base64 encoded. | `needs.codex.outputs.final-message` |
| `reusable-codex-run.yml` | `final-message-summary` | string | First 500 characters of Codex output, safe for PR comments. | `needs.codex.outputs.final-message-summary` |
| `reusable-codex-run.yml` | `error-summary` | string | Failure summary message from Codex output or preflight errors. | `needs.codex.outputs.error-summary` |
| `reusable-codex-run.yml` | `exit-code` | string (number-like) | Codex CLI exit code. | `needs.codex.outputs.exit-code` |
| `reusable-codex-run.yml` | `changes-made` | string (boolean-like) | Whether Codex made file changes. | `needs.codex.outputs.changes-made` |
| `reusable-codex-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed. | `needs.codex.outputs.commit-sha` |
| `reusable-codex-run.yml` | `files-changed` | string (number-like) | Number of files changed by Codex. | `needs.codex.outputs.files-changed` |
| `reusable-codex-run.yml` | `agent-execution-started` | string (boolean-like) | Whether the Run Codex step started. | `needs.codex.outputs.agent-execution-started` |
| `reusable-codex-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.codex.outputs.capability-id` |
| `reusable-codex-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.codex.outputs.effect-fingerprint` |
| `reusable-codex-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.codex.outputs.evidence-artifact-ref` |
| `reusable-codex-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.codex.outputs.supervision-mode` |
| `reusable-codex-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.codex.outputs.capability-evidence-status` |
| `reusable-codex-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.codex.outputs.terminal-disposition` |
| `reusable-codex-run.yml` | `error-category` | string | Error category if failure occurred. | `needs.codex.outputs.error-category` |
| `reusable-codex-run.yml` | `error-type` | string | Error type if failure occurred. | `needs.codex.outputs.error-type` |
| `reusable-codex-run.yml` | `error-recovery` | string | Suggested recovery action if failure occurred. | `needs.codex.outputs.error-recovery` |
| `reusable-codex-run.yml` | `watchdog-saved` | string (boolean-like) | Whether the pre-timeout watchdog saved uncommitted work. | `needs.codex.outputs.watchdog-saved` |
| `reusable-codex-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed. | `needs.codex.outputs.llm-analysis-run` |
| `reusable-codex-run.yml` | `llm-provider` | string | LLM provider used for analysis. | `needs.codex.outputs.llm-provider` |
| `reusable-codex-run.yml` | `llm-model` | string | Specific model used for analysis. | `needs.codex.outputs.llm-model` |
| `reusable-codex-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis. | `needs.codex.outputs.llm-confidence` |
| `reusable-codex-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions. | `needs.codex.outputs.llm-completed-tasks` |
| `reusable-codex-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected. | `needs.codex.outputs.llm-has-completions` |
| `reusable-codex-run.yml` | `llm-raw-confidence` | string (number-like) | Raw confidence before BS detection adjustment. | `needs.codex.outputs.llm-raw-confidence` |
| `reusable-codex-run.yml` | `llm-effort-score` | string (number-like) | Estimated effort score based on session activity. | `needs.codex.outputs.llm-effort-score` |
| `reusable-codex-run.yml` | `llm-data-quality` | string | Session data quality level. | `needs.codex.outputs.llm-data-quality` |
| `reusable-codex-run.yml` | `llm-analysis-text-length` | string (number-like) | Length of analysis text sent to LLM. | `needs.codex.outputs.llm-analysis-text-length` |
| `reusable-codex-run.yml` | `llm-quality-warnings` | string (JSON) | JSON array of quality warnings from the BS detector. | `needs.codex.outputs.llm-quality-warnings` |
| `reusable-claude-run.yml` | `final-message` | string (base64) | Full Claude output message, base64 encoded. | `needs.claude.outputs.final-message` |
| `reusable-claude-run.yml` | `final-message-summary` | string | First 500 characters of Claude output, safe for PR comments. | `needs.claude.outputs.final-message-summary` |
| `reusable-claude-run.yml` | `error-summary` | string | Failure summary message from Claude output or preflight errors. | `needs.claude.outputs.error-summary` |
| `reusable-claude-run.yml` | `exit-code` | string (number-like) | Claude CLI exit code. | `needs.claude.outputs.exit-code` |
| `reusable-claude-run.yml` | `changes-made` | string (boolean-like) | Whether Claude made file changes. | `needs.claude.outputs.changes-made` |
| `reusable-claude-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed. | `needs.claude.outputs.commit-sha` |
| `reusable-claude-run.yml` | `files-changed` | string (number-like) | Number of files changed by Claude. | `needs.claude.outputs.files-changed` |
| `reusable-claude-run.yml` | `agent-execution-started` | string (boolean-like) | Whether the Run Claude step started. | `needs.claude.outputs.agent-execution-started` |
| `reusable-claude-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.claude.outputs.capability-id` |
| `reusable-claude-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.claude.outputs.effect-fingerprint` |
| `reusable-claude-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.claude.outputs.evidence-artifact-ref` |
| `reusable-claude-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.claude.outputs.supervision-mode` |
| `reusable-claude-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.claude.outputs.capability-evidence-status` |
| `reusable-claude-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.claude.outputs.terminal-disposition` |
| `reusable-claude-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed. | `needs.claude.outputs.llm-analysis-run` |
| `reusable-claude-run.yml` | `llm-provider` | string | LLM provider used for analysis. | `needs.claude.outputs.llm-provider` |
| `reusable-claude-run.yml` | `llm-model` | string | Specific model used for analysis. | `needs.claude.outputs.llm-model` |
| `reusable-claude-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis. | `needs.claude.outputs.llm-confidence` |
| `reusable-claude-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions. | `needs.claude.outputs.llm-completed-tasks` |
| `reusable-claude-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected. | `needs.claude.outputs.llm-has-completions` |
| `reusable-claude-run.yml` | `error-category` | string | Error category if failure occurred. | `needs.claude.outputs.error-category` |
| `reusable-claude-run.yml` | `error-type` | string | Error type if failure occurred. | `needs.claude.outputs.error-type` |
| `reusable-claude-run.yml` | `error-recovery` | string | Suggested recovery action if failure occurred. | `needs.claude.outputs.error-recovery` |

Reusable workflows without `workflow_call` outputs:

| Workflow | Caller-facing output status |
| --- | --- |
| `reusable-10-ci-python.yml` | No `workflow_call` outputs; publishes coverage, metrics, logs, and summaries as artifacts/job output. |
| `reusable-11-ci-node.yml` | No `workflow_call` outputs; publishes coverage and JUnit artifacts when enabled. |
| `reusable-12-ci-docker.yml` | No `workflow_call` outputs; logs Docker smoke results. |
| `reusable-13-cross-repo-smoke.yml` | No `workflow_call` outputs; logs cross-repo smoke command output. |
| `reusable-18-autofix.yml` | No `workflow_call` outputs; publishes patch artifacts and summaries. |
| `reusable-70-orchestrator-main.yml` | No `workflow_call` outputs; consumes init outputs and reports status via summaries. |
| `reusable-agents-issue-bridge.yml` | No `workflow_call` outputs; creates bridge PR artifacts and logs. |
| `reusable-agents-pr-health.yml` | No `workflow_call` outputs; reports health through checks and summaries. |
| `reusable-agents-verifier.yml` | No `workflow_call` outputs; posts verifier reports and artifacts. |

### Using outputs in dependent jobs

The examples below show the two main output-consumption patterns: gating a downstream reusable workflow from orchestrator initialization, and passing a Markdown output into a reporting job.

Orchestrator chaining example:

```yaml
jobs:
  orchestrator-init:
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-init.yml@main

  orchestrator-main:
    needs: orchestrator-init
    if: needs.orchestrator-init.outputs.has_work == 'true' && needs.orchestrator-init.outputs.rate_limit_safe == 'true'
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-main.yml@main
    with:
      init_success: ${{ needs.orchestrator-init.result }}
      enable_keepalive: ${{ needs.orchestrator-init.outputs.enable_keepalive }}
      keepalive_pause_label: ${{ needs.orchestrator-init.outputs.keepalive_pause_label }}
      keepalive_round: ${{ needs.orchestrator-init.outputs.keepalive_round }}
      keepalive_pr: ${{ needs.orchestrator-init.outputs.keepalive_pr }}
      options_json: ${{ needs.orchestrator-init.outputs.options_json }}
      token_source: ${{ needs.orchestrator-init.outputs.token_source }}
```

Agent readiness example (posting the Markdown table):

```yaml
jobs:
  agents-readiness:
    uses: stranske/Workflows/.github/workflows/reusable-16-agents.yml@main
    with:
      enable_readiness: 'true'

  comment-readiness:
    needs: agents-readiness
    if: needs.agents-readiness.outputs.readiness_table != ''
    runs-on: ubuntu-latest
    steps:
      - name: Post readiness table
        uses: actions/github-script@v7
        with:
          script: |
            const table = `## Agent Readiness\n\n${{ toJSON(needs.agents-readiness.outputs.readiness_table) }}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: table,
            });
```


### Agent Workflows

| Workflow | Purpose | Required Secrets |
|----------|---------|------------------|
| `reusable-agents-issue-bridge.yml` | Convert issues to PRs via agents | `service_bot_pat`, `owner_pr_pat` |

### Example: Full CI

```yaml
name: CI

on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.12'
      lint: true
      typecheck: true
      coverage-min: '70'
    secrets:
      pypi-token: ${{ secrets.PYPI_TOKEN }}  # Optional, for publishing
```

---

## Template Workflows

Copy from `/templates/` and customize:

| Template | Use Case |
|----------|----------|
| `ci-basic.yml` | Simple projects: lint + test |
| `ci-full.yml` | Production projects: full pipeline with gate |
| `dependency-refresh.yml` | Keep `requirements.lock` updated |
| `cosmetic-repair.yml` | Auto-fix formatting issues |

> **Consuming a `packages/` monorepo dependency (e.g. `app-baseline-kit`)?**
> Exclude it from `requirements.lock` with `[tool.uv.pip] no-emit-package` so a
> frozen SHA in the lock cannot conflict with the unpinned `@main` URL when
> Workflows `main` advances. See
> [Monorepo Package Dependencies](ops/CONSUMER_REPO_MAINTENANCE.md#monorepo-package-dependencies-app-baseline-kit),
> and [Declaring the `app-baseline-kit` Dependency](guides/BASELINE_KIT_DEPENDENCY.md)
> for the catalog of accepted patterns and how to choose one.

### Customization Checklist

After copying a template:

- [ ] Replace `YOUR_PACKAGE_NAME` with your package
- [ ] Update test paths (`tests/`)
- [ ] Update source paths (`src/`)
- [ ] Set Python version(s)
- [ ] Configure coverage threshold
- [ ] Add required secrets

---

## Required Setup

### Repository Secrets

Set these in your repo's Settings → Secrets → Actions:

| Secret | When Needed | How to Create |
|--------|-------------|---------------|
| `GITHUB_TOKEN` | Always | Automatic |
| `SERVICE_BOT_PAT` | Agent workflows | Create PAT with `repo` scope |
| `OWNER_PR_PAT` | Agent PR creation and workflow-file source proposals | Create classic PAT with `repo` and `workflow` scopes |
| `PYPI_TOKEN` | Publishing packages | From pypi.org |

> **This table is a starting point, not the full set.** A first-party consumer
> actually carries ~15 secrets (App IDs and private keys for the Workflows,
> keepalive and bot-comment Apps; agent CLI credentials; provider API keys).
> `templates/consumer-repo/docs/SETUP_CHECKLIST.md` §3.2 is the authoritative list.
> Corrected 2026-08-21: onboarding `stranske/Orchestrator` against this table alone
> produced a repo with 4 of the 15 secrets and no indication anything was missing.

### Branch Protection

For the gate pattern to work:

1. Go to Settings → Branches → Add rule
2. Set branch pattern: `main`
3. Enable "Require status checks"
4. Add required checks: `CI Gate`, `Lint`, `Test`


### Workflow Permissions

**Critical for reusable workflows:** The repository must have write permissions enabled.

1. Go to Settings → Actions → General
2. Scroll to "Workflow permissions"
3. Select **"Read and write permissions"**
4. Check **"Allow GitHub Actions to create and approve pull requests"**
5. Click Save

Without these settings, workflows calling reusable workflows from this repo will fail
with `startup_failure` status and no useful error message.

**Via API (for automation):**
```bash
gh api repos/OWNER/REPO/actions/permissions/workflow -X PUT --input - << 'EOF'
{"default_workflow_permissions": "write", "can_approve_pull_request_reviews": true}
EOF
```

### Consumer Repo Setup: Required Scripts

The reusable `reusable-10-ci-python.yml` workflow runs two scripts from the
consumer repository. Add these files to your repo or CI will fail:

- `scripts/sync_test_dependencies.py` (validates test imports vs. dev deps)
- `tools/resolve_mypy_pin.py` (selects the Python version used by mypy)

You can copy the reference implementations from:

- `templates/integration-repo/scripts/sync_test_dependencies.py`
- `templates/integration-repo/tools/resolve_mypy_pin.py`

### Consumer Repo Setup: .gitignore Entries

**Critical for keepalive/codex workflows:** Add these entries to your `.gitignore`
to prevent merge conflicts when multiple PRs run concurrently:

```gitignore
# Codex working files (preserved via workflow artifacts, not git)
# CRITICAL: These must be gitignored to prevent merge conflicts when
# multiple PRs run keepalive simultaneously. Each run rebuilds these files.
# Generic names (legacy)
codex-prompt.md
codex-output.md
# PR-specific names (used by reusable-codex-run.yml to avoid conflicts)
codex-prompt-*.md
codex-output-*.md
verifier-context.md
```

**Why this matters:** When multiple PRs run keepalive concurrently, each workflow
generates these working files. The workflow uses PR-specific filenames (e.g.,
`codex-output-123.md`) and explicitly excludes them from commits, but the
`.gitignore` provides defense-in-depth. Historical data is preserved in:
- PR comments (completion summaries)
- Workflow artifacts (full outputs)
- Commit messages (change descriptions)

Post-merge verification loads a bounded evidence record from the selected PR.
It inspects only that PR's comments and workflow runs explicitly referenced by
the PR body, linked issue bodies, or those bounded comments. Comment count and
rendered characters, referenced runs, artifact count and archive size, text
entries, and rendered artifact characters all have finite limits. The context
reports each source as `present`, `absent`, or `unavailable`: a complete empty
lookup is `absent`, while API failure, unreadable content, or any limit that
prevents complete inspection is `unavailable`. An unavailable source can never
be used to claim that a required transcript is absent or to justify PASS for an
otherwise unverifiable required deliverable. Artifact archives are read without
extracting paths into the checkout, and only allowlisted text entry types are
included as untrusted evidence rather than instructions. Directory records are
harmless archive structure, but any non-directory payload entry excluded by the
allowlist makes the artifact evidence unavailable even if other text was read.
Evaluate/compare accept only a complete Git patch as code: a diff summary,
garbled `--diff-file`, malformed quoted path, or budget-truncated patch floors
the verdict at CONCERNS rather than treating zero parsed files as no change.
Binary-only descriptors (`Binary files ... differ` or `GIT binary patch`) are
omitted code coverage, not inspectable contents. Evidence-delivery requirements
such as "Include an artifact" remain required; mentioning an API/UI change
before a delivery instruction does not turn that instruction into product behavior.
Artifacts included in a product response or payload are not workflow evidence,
regardless of the actor's name; explicit PR delivery remains required.
The same rule applies to transcript/command-output fields in response contracts;
an additional required PR-comment delivery in the clause is preserved.
Declarative return/display/render/emit/expose behavior is identified without a
product-actor name list; explicit reviewer/author obligations and imperative
evidence requests remain requirements. Artifact/output/transcript pronouns can
refer to objects in the same acceptance item, including plural object groups,
in either active or passive delivery wording,
but never inherit objects from another checklist item. Optional or prohibited
delivery remains local to its clause, and artifact plus output delivery retains
both retrieval channels rather than downgrading the artifact to generic evidence.
Response-field operations include `provide`; an API response providing output
does not imply a review deliverable, while a separate PR-delivery clause and
explicit author obligation remain evidence requirements.
Product auxiliary wording is shared across response grouping and filtering,
artifact behavior and output predicates: `must`, `is required to`, `is needed
to`, and equivalent deontic forms do not change a product field into evidence.
An explicitly required workflow-run link is an evidence deliverable; only a
standalone workflow status/success criterion is exempt from evidence retrieval.
An unavailable required link prevents a coverage PASS.
Workflow-run antecedents also survive separate active/passive PR-link clauses;
qualified status forms such as passing on Linux or finishing successfully stay
exempt when they do not separately require link delivery.
Cross-repository full-diff recovery fetches and verifies both the recorded base
and PR head from the target repository before reconstructing the range.
Git's tab delimiter in `---`/`+++` metadata is not part of the changed pathname.
Diff summaries preserve literal ` b/` path components instead of choosing the
last header delimiter. Ambiguous rename/copy headers require authoritative
pre-hunk path metadata; unresolved or malformed paths fail closed.
Acceptance and evidence section scanners share fence-closing validation: a
marker with trailing non-space/tab content cannot expose literal headings.
Root fences cannot close at four spaces, while indented source snippets retain
their opening indentation so literal examples remain inert.

### Consumer Repo Setup: Coverage Soft Gate

Enable coverage tracking with automatic issue creation when coverage drops:

**1. Enable soft-gate in your Gate workflow:**

```yaml
jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      coverage-min: "80"           # Minimum threshold
      enable-soft-gate: true       # Enable trend tracking & hotspot reporting
      artifact-prefix: "gate-"     # Required for coverage guard
```

**2. Create a coverage baseline file (`config/coverage-baseline.json`):**

```json
{
  "line": 80.0,
  "warn_drop": 1.0,
  "recovery_days": 3,
  "updated": "2025-12-30",
  "notes": "Initial baseline - adjust based on project maturity"
}
```

**3. Add the coverage guard workflow (`.github/workflows/maint-coverage-guard.yml`):**

Copy from `templates/consumer-repo/.github/workflows/maint-coverage-guard.yml`

**What you get:**

| Feature | Description |
|---------|-------------|
| **Coverage Summary** | Table in workflow run summary showing current vs baseline |
| **Hotspot Report** | List of files with lowest coverage (candidates for new tests) |
| **Low Coverage Alert** | Files below 50% threshold highlighted separately |
| **Baseline Issue** | Auto-created/updated issue when coverage drops below baseline |
| **Trend Artifacts** | `coverage-trend.json` and `coverage-trend-history.ndjson` for analysis |

**Guard tolerance and recovery:** `warn_drop` is a percentage-point allowance below
the baseline (default `1.0` if omitted). A run creates or updates a breach issue only
when `current < baseline - warn_drop`; a smaller drop is an intentional no-op. An open
breach issue closes only after coverage reaches `baseline - warn_drop` for the
configured `recovery_days` consecutive samples (default `3`). The warning allowance
changes the recovery threshold, not the default confirmation window.

The guard restores repository-scoped recovery history, appends the current producer
run (replacing a repeated run identity), and retains at most 30 records. It saves a
new immutable cache after each guard run; a repository restore prefix carries the
records across different Gate producers. An incomplete recovery reports how many
of the required records meet the threshold. Dry runs do not persist history.

**Soft vs Hard Gate:**

- **Soft gate** (`enable-soft-gate: true`): Reports coverage but doesn't fail the build
- **Hard gate** (`coverage-min: "80"`): Fails build if coverage below threshold

Use both together for maximum visibility: soft gate shows trends while hard gate
enforces the minimum.

---

## Common Patterns

### Pattern 1: PR Gate

Use a gate job that branch protection requires:

```yaml
jobs:
  lint:
    # ...
  test:
    # ...
  
  gate:
    name: CI Gate
    needs: [lint, test]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Check results
        run: |
          if [[ "${{ needs.lint.result }}" != "success" ]] || \
             [[ "${{ needs.test.result }}" != "success" ]]; then
            exit 1
          fi
```

### Pattern 2: Matrix Testing

Test across Python versions:

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ['3.12', '3.13']
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
```

### Pattern 3: Conditional Jobs

Skip expensive jobs for draft PRs:

```yaml
jobs:
  full-test:
    if: github.event.pull_request.draft == false
    # ...
```

---

## Debouncing High-Frequency Workflows

Consumer repos can reduce redundant runs by adding workflow-level concurrency groups
with cancellation. Apply this to workflows that trigger on rapid push, label, or
comment activity.

Example patterns:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}
  cancel-in-progress: true
```

```yaml
concurrency:
  group: ${{ github.workflow }}-issue-${{ github.event.issue.number }}
  cancel-in-progress: true
```

Use `github.ref` for push workflows, PR numbers for pull_request workflows, and
issue numbers for issue_comment workflows. Avoid cancellation when a workflow
must run to completion (for example, long-running migrations).

---

## Troubleshooting

### "Workflow file issue" Error

**Cause:** YAML syntax error or invalid workflow structure.

**Fix:** Validate your workflow:
```bash
# In the Workflows repo, this runs actionlint as part of the fast checks.
./scripts/dev_check.sh

# Or, if you already have actionlint installed in your environment:
actionlint .github/workflows/your-workflow.yml
```

### "Resource not accessible" Error

**Cause:** Missing permissions or secrets.

**Fix:** Add permissions block:
```yaml
permissions:
  contents: read
  pull-requests: write
```

### Reusable Workflow Not Found

**Cause:** Wrong path or ref.

**Fix:** Use full path with `@ref`:
```yaml
uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
```

### Jobs Not Running

**Cause:** `if` condition evaluating to false.

**Fix:** Check concurrency groups and conditions. For `workflow_dispatch`, ensure fallbacks:
```yaml
concurrency:
  group: ci-${{ github.event.pull_request.number || github.run_id }}
```


### Startup Failure (No Error Message)

**Cause:** Repository workflow permissions set to "Read" instead of "Read and write".

**Symptoms:**
- Workflow shows `startup_failure` status
- No error message or logs available
- Same workflow works in other repositories
- Only affects workflows calling reusable workflows

**Fix:** Update repository workflow permissions:
1. Go to Settings → Actions → General
2. Set "Workflow permissions" to **"Read and write permissions"**
3. Enable **"Allow GitHub Actions to create and approve pull requests"**

**Capture the hidden startup error (file-parse / job-graph phase):**
```bash
python scripts/workflow_startup_failure_diagnostic.py --repo OWNER/REPO --run-id RUN_ID
```

This inspects check-runs for the same head SHA/run ID and prints the parser error
title/summary text that is not visible in `actions/runs/<id>/jobs`.

The same diagnostic also recognizes `action_required` runs with zero jobs.
When the run event is a public-fork `pull_request` and `head_repository.fork`
is true, classify it as a fork contributor approval hold (REST
`/actions/runs/{id}/approve` can recover it). Otherwise treat it as GitHub's
unproven-workflow protection: review the workflow file and use **Approve and
run** from an authenticated GitHub web session; the fork-PR REST approval
endpoint does not cover that class of hold. If the event is `pull_request` but
fork status cannot be determined, report an unspecified approval hold and
inspect `event` + `head_repository` before choosing remediation.

**Find every held workflow, not just one run:**
```bash
python scripts/workflow_startup_failure_diagnostic.py --sweep --repo OWNER/REPO
```

The sweep walks every active workflow, flags those whose recent runs are
dominated by zero-job `action_required`, and prints the blocking quantity
alongside the drainable one:

```
workflow liveness: 11 held / 0 clearable by API - web approval required; oldest 22d (...)
```

`11 held` on its own reads as a backlog to work through; `11 held, 0 clearable by
API` reads as a deadlock, which is what it is. The drainable count is measured
per run rather than assumed - fork-PR holds accept the REST approval endpoint and
unproven-workflow holds do not, so `POST .../approve` answers
`403 "This run is not from a fork pull request or queued by the Actions bot"`.

Onset is found by paginating back to the last run that executed, not from the
sample page: a workflow triggered hourly discards 20 runs in under a day, so a
single page reports a three-week outage as hours old.

The sweep reports and fails. It never approves a run - auto-clearing a hold
GitHub raised on suspicion of malice would make the protection a rubber stamp.
Add `--repos a/b,c/d` to cover consumer repositories, whose synced copies of
these workflows are held independently.


### Startup Failure (Caller Workflow Permissions)

**Cause:** Caller workflow has a top-level `permissions:` block when calling a reusable workflow.

**Symptoms:**
- Same as above: `startup_failure`, no logs, zero jobs started
- The reusable workflow also specifies permissions

**Fix:** Remove the `permissions:` block from the caller workflow:
```yaml
# WRONG - causes startup_failure
permissions:
  contents: read
  pull-requests: write

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main

# CORRECT - let the reusable workflow handle permissions
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
```

---

## Consumer Repo Setup (Full Automation)

The synced model-selection policy is documentation for consumer operators,
not a local MAINT-78 tool install. Run its `capture`, `screen`, `confirm`, and
snapshot commands from a matching `stranske/Workflows` checkout; the
`maint-78-model-evaluation-pilot.yml` workflow and snapshot helper remain
Workflows-owned. The synced `tools/langchain_client.py` preserves an outbound
`openai/` model ID while omitting unsupported temperature for prefixed GPT-5.6
and o-series reasoning models.

For repositories that want full CI + agent automation (Codex keepalive, autofix, etc.):

### Quick Setup

Prefer the managed consumer sync workflow for registered repos. For manual
bootstrap, copy the current default entry points from `templates/consumer-repo/`
and keep the root agent guidance files aligned with the same template source:

```bash
# Current default workflow surface
mkdir -p .github/workflows
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/ci.yml -o .github/workflows/ci.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/autofix-versions.env -o .github/workflows/autofix-versions.env
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-issue-intake.yml -o .github/workflows/agents-issue-intake.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml -o .github/workflows/agents-80-pr-event-hub.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml -o .github/workflows/agents-81-gate-followups.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-verifier.yml -o .github/workflows/agents-verifier.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/autofix.yml -o .github/workflows/autofix.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/pr-00-gate.yml -o .github/workflows/pr-00-gate.yml

# Root agent guidance and target-environment contract synced through .github/sync-manifest.yml
mkdir -p docs
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/AGENTS.md -o AGENTS.md
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/CLAUDE.md -o CLAUDE.md
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/docs/TARGET_WORK_ENVIRONMENT.md -o docs/TARGET_WORK_ENVIRONMENT.md

# These examples track the live Workflows source via /main/, which is the
# supported pin. For a one-off reproducible bootstrap you may replace /main/
# with a commit SHA in each URL, but @main is the supported reference for
# ongoing use (there is no floating version tag).
```

### Workflow Summary

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `ci.yml` | Python CI (lint, format, tests, typecheck) | push, PR |
| `agents-issue-intake.yml` | Assigns Codex/Copilot to issues | issue labeled `agent:codex` |
| `agents-80-pr-event-hub.yml` | Handles PR event routing, keepalive metadata, bot comments, and verification follow-ups | PR events and comments |
| `agents-81-gate-followups.yml` | Coordinates Gate follow-ups, keepalive/autofix recovery, and generated-delivery wakeups | Gate completion and follow-up events |
| `agents-verifier.yml` | Runs label-driven post-merge verification | manual dispatch, `verify:*` labels |
| `autofix.yml` | Auto-fixes lint/format issues | PR sync, `autofix` label |
| `pr-00-gate.yml` | Required PR gate and summary status | PR |
| `cross-repo-smoke.yml` | Optional cross-repo integration smoke (host + pinned dependency checkout) | push, PR, manual (opt-in via `CROSS_REPO_SMOKE_*` vars) |
| `autofix-versions.env` | Pins tool versions | N/A |
| `AGENTS.md` / `CLAUDE.md` / `docs/TARGET_WORK_ENVIRONMENT.md` | Repo-local agent guidance and delivery constraints synced from Workflows | N/A |

### Consolidated Workflow Migration (Notice Period)

To reduce duplicate PR context fetches, consumer repos should use the consolidated
event hubs. Legacy workflow files may still exist during migrations or for
backward compatibility, but new manual setup should prefer the current defaults.

| Legacy Workflow | Replacement |
|-----------------|-------------|
| `agents-pr-meta.yml` | `agents-80-pr-event-hub.yml` |
| `agents-bot-comment-handler.yml` | `agents-80-pr-event-hub.yml` |
| `agents-verify-to-issue-v2.yml` | `agents-80-pr-event-hub.yml` |
| `agents-keepalive-loop.yml` | `agents-81-gate-followups.yml` |
| `agents-autofix-loop.yml` | `agents-81-gate-followups.yml` |

### Required Secrets

| Secret | Purpose | Required For |
|--------|---------|--------------|
| `SERVICE_BOT_PAT` | Bot account for comments/labels (stranske-automation-bot); fallback credential for cross-repository label sync | agents, autofix, Maint 69 label sync |
| `ACTIONS_BOT_PAT` | Workflow dispatch triggers | event-hub/follow-up automation (`agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`); legacy orchestrator/pr-meta only when intentionally retained |
| `OWNER_PR_PAT` | Create PRs on behalf of user; required owner-scoped credential for generated-delivery mutations | issue-intake, Maint 69 label sync, Maint 71 sync reconciliation |
| `CROSS_REPO_TOKEN` | Read access to a dependency repository for cross-repo smoke | `cross-repo-smoke.yml` when `CROSS_REPO_SMOKE_ENABLED=true` |

### Cross-Repo Smoke (opt-in)

The synced `cross-repo-smoke.yml` caller is safe to ship to every consumer repo.
It remains a no-op until you set repository variables and the `CROSS_REPO_TOKEN`
secret. When enabled, it delegates to
`stranske/Workflows/.github/workflows/reusable-13-cross-repo-smoke.yml@main`.

Required repository variables when enabling:

| Variable | Purpose |
|----------|---------|
| `CROSS_REPO_SMOKE_ENABLED` | Set to `true` to run the workflow |
| `CROSS_REPO_SMOKE_DEPENDENCY_REPO` | Dependency slug (`owner/repo`) |
| `CROSS_REPO_SMOKE_RUN_COMMAND` | Shell command executed from the host workspace root |

Optional repository variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CROSS_REPO_SMOKE_DEPENDENCY_REF` | `main` | Branch, tag, or SHA for the dependency checkout |
| `CROSS_REPO_SMOKE_SETUP_NODE` | `false` | Set to `true` to run `actions/setup-node` before installs |
| `CROSS_REPO_SMOKE_NODE_VERSION` | `20` | Node.js version when setup is enabled |
| `CROSS_REPO_SMOKE_HOST_INSTALL_COMMAND` | *(empty)* | Host install command (workspace root) |
| `CROSS_REPO_SMOKE_DEPENDENCY_INSTALL_COMMAND` | *(empty)* | Dependency install command (dependency checkout path) |

Example caller wiring (already present in the synced template):

```yaml
jobs:
  cross-repo-smoke:
    if: >-
      vars.CROSS_REPO_SMOKE_ENABLED == 'true' &&
      vars.CROSS_REPO_SMOKE_DEPENDENCY_REPO != '' &&
      vars.CROSS_REPO_SMOKE_RUN_COMMAND != '' &&
      (github.event_name != 'pull_request' || github.event.pull_request.head.repo.fork == false)
    uses: stranske/Workflows/.github/workflows/reusable-13-cross-repo-smoke.yml@main
    with:
      dependency_repo: ${{ vars.CROSS_REPO_SMOKE_DEPENDENCY_REPO }}
      dependency_ref: ${{ vars.CROSS_REPO_SMOKE_DEPENDENCY_REF || 'main' }}
      setup_node: ${{ vars.CROSS_REPO_SMOKE_SETUP_NODE == 'true' }}
      node_version: ${{ vars.CROSS_REPO_SMOKE_NODE_VERSION || '20' }}
      host_install_command: ${{ vars.CROSS_REPO_SMOKE_HOST_INSTALL_COMMAND || '' }}
      dependency_install_command: ${{ vars.CROSS_REPO_SMOKE_DEPENDENCY_INSTALL_COMMAND || '' }}
      run_command: ${{ vars.CROSS_REPO_SMOKE_RUN_COMMAND }}
    secrets:
      CROSS_REPO_TOKEN: ${{ secrets.CROSS_REPO_TOKEN }}
```

The reusable workflow exports `DEPENDENCY_PATH` (basename of `dependency_repo`)
to the smoke command environment so scripts can reference the sibling checkout.

### Dual Checkout Architecture

Consumer repo workflows use the **dual checkout pattern**:

1. **Consumer repo** is checked out for your code
2. **Workflows repo** is checked out (sparse) for scripts

This means:
- ✅ Consumer repos still provide CI helper scripts in `scripts/` and `tools/`
- ✅ Automation scripts under `.github/scripts/` stay **up-to-date** from Workflows
- ✅ **No sync required** when Workflows scripts change
- ✅ Only **thin caller workflows** (~50-100 lines each) in your repo

### Drift Guardrails

Workflows runs a daily **Health 68 Consumer Sync Drift Check** to compare the
consumer repos against the templates/manifest. This guard excludes files marked
with `sync_mode: create_only`. The integration repo is validated separately via
Health 67.

### What Each Workflow Does

#### `agents-80-pr-event-hub.yml` (Critical for PR Events)

This is the current PR-event hub for Codex keepalive metadata, bot comments,
and verification follow-ups. When Codex completes a round of work, it posts a
comment with a keepalive marker. This workflow:

1. Detects the keepalive marker in PR comments
2. Validates the comment is from an authorized user
3. Dispatches the follow-up path that can continue work
4. Updates PR body with status sections

Without this workflow, Codex PRs will stall after the first round.

#### `agents-81-gate-followups.yml`

This is the current Gate follow-up hub. It coordinates keepalive continuation,
autofix recovery, and post-Gate actions after `pr-00-gate.yml` completes. A Gate
completion on a stable consumer-sync or dev-tool-sync branch also dispatches the
matching central Maint 71 lane; it never merges the generated PR locally.

#### `autofix.yml`

When a PR has lint/format issues:

1. Autofix runs Black and Ruff with `--fix`
2. Commits fixes directly to the PR branch
3. Labels PR with `autofix:applied`
4. Posts a summary comment

This eliminates manual formatting work and ensures consistent style.

##### Dynamic Target Detection

Autofix automatically detects Python directories by finding all `.py` files in the repository. Standard non-source directories are excluded by default:

- `.git`, `.venv`, `venv`, `.env`, `env`
- `__pycache__`, `node_modules`
- `build`, `dist`, `.eggs`, `*.egg-info`
- `.tox`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `htmlcov`, `.coverage`

##### Custom Exclusions (`.autofix-exclude`)

To exclude additional directories from autofix (e.g., generated code, vendor packages, legacy modules), create a `.autofix-exclude` file in your repository root:

```
# .autofix-exclude
# Comments start with #

# Exclude generated migrations
migrations/

# Exclude vendored code
vendor/
third_party/

# Exclude legacy modules being deprecated
legacy_api/
```

Each line specifies a directory to exclude. This file is optional - if not present, only standard exclusions apply.

---

## Getting Help

- **Documentation:** See `docs/ci/WORKFLOWS.md` for detailed workflow descriptions
- **Issues:** Open an issue in stranske/Workflows for bugs or feature requests
- **Templates:** Check `/templates/` for copy-paste solutions
- **Consumer templates:** See `/templates/consumer-repo/` for full automation setup

---

## CI Failure Routing

The keepalive system intelligently routes CI failures to the appropriate fix mechanism:

### Decision Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     Gate Workflow Result                         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Gate Passed?   │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │ Yes                           │ No
              ▼                               ▼
    ┌─────────────────┐  ┌─────────────────┐
    │  Normal Work    │  │ Classify Failure│
    │  (run action)   │  └─────────────────┘
    │                 │           │
    │  Prompt:        │     ┌─────┴─────┐
    │  keepalive_     │     │           │
    │  next_task.md   │     ▼           ▼
    └─────────────────┘  ┌───────┐  ┌──────────────┐
                         │ Lint/ │  │ Tests/Mypy/  │
                         │Format │  │ Unknown      │
                         └───┬───┘  └──────┬───────┘
                             │             │
                             ▼             ▼
                     ┌────────────┐  ┌─────────────────┐
                     │  Autofix   │  │   Fix Mode      │
                     │  Workflow  │  │  (fix action)   │
                     │            │  │                 │
                     │  Black +   │  │  Prompt:        │
                     │  Ruff      │  │  fix_ci_        │
                     └────────────┘  │  failures.md    │
                                     └─────────────────┘
```

### How It Works

1. **Gate Evaluation**: When the keepalive loop evaluates, it checks the gate workflow status

2. **Failure Classification**: If the gate failed, the system inspects which jobs failed:
   - **Test failures**: Jobs with names containing `test`, `pytest`, `unittest`
   - **Mypy failures**: Jobs with names containing `mypy`, `type`, `typecheck`
   - **Lint failures**: Jobs with names containing `lint`, `ruff`, `black`, `format`

3. **Routing Decision**:
   - **Lint/Format failures** → Route to **Autofix** (Black + Ruff can fix these automatically)
   - **Test/Mypy failures** → Route to **Codex with fix_ci_failures.md prompt** (requires code changes)
   - **Unknown failures** → Route to **Codex with fix_ci_failures.md prompt** (needs investigation)

### Prompt Files

| Prompt | Purpose | When Used |
|--------|---------|-----------|
| `keepalive_next_task.md` | Normal task work | Gate passed, tasks remaining |
| `fix_ci_failures.md` | Focus on fixing CI | Test/mypy failures detected |

### Output Variables

The `evaluate` job outputs these new fields:

| Output | Description | Values |
|--------|-------------|--------|
| `prompt_mode` | Which prompt mode to use | `normal`, `fix_ci` |
| `prompt_file` | Full path to prompt file | Path to `.md` file |
| `reason` | Why this action was chosen | `fix-test`, `fix-mypy`, `fix-unknown`, etc. |

### Action Types

| Action | Description | Triggers |
|--------|-------------|----------|
| `run` | Normal Codex run | Gate passed, tasks remaining |
| `fix` | CI fix mode | Test/mypy failure detected |
| `wait` | Wait for gate | Gate pending or lint failure (autofix handles) |
| `stop` | Stop iteration | Tasks complete or max iterations |
| `skip` | Skip entirely | Keepalive disabled |

### Example Scenarios

**Scenario 1: Tests Failing**
```
Gate Status: failure
Failed Jobs: [test (3.12), test (3.12)]
Classification: test failure
Action: fix
Reason: fix-test
Prompt: fix_ci_failures.md
```

**Scenario 2: Mypy Errors**
```
Gate Status: failure
Failed Jobs: [mypy]
Classification: mypy failure
Action: fix
Reason: fix-mypy
Prompt: fix_ci_failures.md
```

**Scenario 3: Black Formatting**
```
Gate Status: failure
Failed Jobs: [lint (black)]
Classification: lint failure
Action: wait
Reason: gate-not-success
→ Autofix workflow handles this separately
```

**Scenario 4: All Passing**
```
Gate Status: success
Action: run
Reason: ready
Prompt: keepalive_next_task.md
```

### Consumer Setup

No additional configuration needed. The CI failure routing is built into the keepalive system and works automatically when you have:

1. `agents-keepalive-loop.yml` workflow
2. `pr-00-gate.yml` workflow (for gate status)
3. `fix_ci_failures.md` prompt (in `.github/codex/prompts/`)

Ensure `fix_ci_failures.md` exists in `.github/codex/prompts/` for fix mode to work properly.

### Python CI default migration

Omitting both reusable Python runtime inputs selects Python 3.13 and 3.14 in
parallel. An explicit `python-version` remains a single-runtime override, including
3.12; a nonempty `python-versions` array still takes precedence. The primary artifact
runtime defaults to shared `CI_PYTHON_VERSION` when selected, otherwise the first
selected runtime. Gate requests coverage on 3.14 only through
`coverage-python-version`; both runtimes retain identical test selection. `pytest-workers` accepts `auto`
(the backward-compatible reusable default) or a positive integer; the first-party
Gate and new Gate template request `4`.

This changes CI defaults, not the package minimum (>=3.12). Existing create-only
consumer Gates keep their authored runtime overrides and require separate migration
review. The universal lock remains compatible with the package minimum; its compile
baseline alone is not a reason to remove 3.12 support.

```

### templates/consumer-repo/.github/workflows/maint-coverage-guard.yml @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
name: Maint Coverage Guard

'on':
  schedule:
    - cron: '45 6 * * *'
  workflow_dispatch:

permissions:
  contents: read
  actions: read
  issues: write

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # Rate limit gate: skip non-critical coverage checks when API quota is low
  # This ensures keepalive and core workflows get priority (threshold: 2000)
  rate-limit-check:
    name: Rate limit gate
    runs-on: ubuntu-latest
    outputs:
      proceed: ${{ steps.check.outputs.proceed || 'true' }}
      remaining: ${{ steps.check.outputs.remaining || '' }}
    steps:
      # Mint GitHub App token early to use for API calls (avoids rate limits)
      - name: Mint GitHub App Token
        id: app_token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3
        continue-on-error: true
        with:
          client-id: ${{ secrets.WORKFLOWS_APP_ID || '0' }}
          private-key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY || 'dummy' }}

      - name: Checkout retry helpers
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          token: ${{ steps.app_token.outputs.token || github.token }}
          sparse-checkout: |
            .github/actions/setup-api-client
            .github/scripts/error_classifier.js
            .github/scripts/github-api-with-retry.js
            .github/scripts/token_load_balancer.js
          sparse-checkout-cone-mode: false

      - name: Setup API client
        uses: ./.github/actions/setup-api-client
        with:
          # named inputs, not the whole secrets context (see #3185)
          github_token: ${{ github.token }}
          service_bot_pat: ${{ secrets.SERVICE_BOT_PAT }}
          actions_bot_pat: ${{ secrets.ACTIONS_BOT_PAT }}
          owner_pr_pat: ${{ secrets.OWNER_PR_PAT }}
          agents_automation_pat: ${{ secrets.AGENTS_AUTOMATION_PAT }}
          workflows_app_id: ${{ secrets.WORKFLOWS_APP_ID }}
          workflows_app_private_key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}
          keepalive_app_id: ${{ secrets.KEEPALIVE_APP_ID }}
          keepalive_app_private_key: ${{ secrets.KEEPALIVE_APP_PRIVATE_KEY }}
          gh_app_id: ${{ secrets.GH_APP_ID }}
          gh_app_private_key: ${{ secrets.GH_APP_PRIVATE_KEY }}
          app_1_id: ${{ secrets.APP_1_ID }}
          app_1_private_key: ${{ secrets.APP_1_PRIVATE_KEY }}
          app_2_id: ${{ secrets.APP_2_ID }}
          app_2_private_key: ${{ secrets.APP_2_PRIVATE_KEY }}



      - name: Check API quota
        id: check
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3 # v9
        env:
          # Higher threshold than orchestrator (1000) so keepalive runs first
          RATE_LIMIT_THRESHOLD: '2000'
        with:
          script: |
            // # best-effort: this ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative.
            const threshold = parseInt(process.env.RATE_LIMIT_THRESHOLD || '2000', 10);
            const fs = require('fs');
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { withRetry } = retryHelpers;
            try {
              const { data } = await withRetry(() => github.rest.rateLimit.get());
              const remaining = data?.resources?.core?.remaining || 0;
              const limit = data?.resources?.core?.limit || 5000;
              const proceed = remaining >= threshold;

              core.setOutput('proceed', proceed ? 'true' : 'false');
              core.setOutput('remaining', String(remaining));

              if (!proceed) {
                const reset = data?.resources?.core?.reset || 0;
                const resetTime = new Date(reset * 1000).toISOString();
                const notice = `Deferring coverage guard: API quota low (${remaining}/${limit}).`;
                core.notice(`${notice} Resets at ${resetTime}`);
                const quotaMessage = [
                  'API quota too low for non-critical health checks',
                  `(${remaining}/${limit} remaining).`,
                ].join(' ');
                await core.summary
                  .addHeading('Coverage Guard Deferred', 3)
                  .addRaw(quotaMessage)
                  .addEOL()
                  .addRaw(`Threshold: ${threshold}. Resets at: ${resetTime}`)
                  .write();
              }
            } catch (error) {
              core.warning(`Rate limit check failed: ${error.message}. Proceeding anyway.`);
              core.setOutput('proceed', 'true');
            }

  guard:
    name: coverage baseline monitor
    needs: rate-limit-check
    if: >-
      ${{ needs.rate-limit-check.outputs.proceed == 'true' }}
    runs-on: ubuntu-latest
    steps:
      # Mint GitHub App token early to use for API calls (avoids rate limits)
      - name: Mint GitHub App Token
        id: app_token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3
        continue-on-error: true
        with:
          client-id: ${{ secrets.WORKFLOWS_APP_ID || '0' }}
          private-key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY || 'dummy' }}
          owner: ${{ github.repository_owner }}

      - name: Checkout repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Locate latest Gate workflow run
        id: discover
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3 # v9
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const { owner, repo } = context.repo;
            const fs = require('fs');
            // WHICH WORKFLOW CARRIES THIS REPO'S COVERAGE IS A PER-REPO FACT, AND IT WAS HARDCODED.
            //
            // Two repos are invisible to this guard for the same reason, and neither is
            // misconfigured. stranske/Counter_Risk deliberately measures coverage on ci.yml -- its
            // Gate carries an explicit "PR Gate is optimized for fast feedback. Full coverage
            // enforcement runs on main" rationale. stranske/Orchestrator publishes its only honest
            // figure (80.3% combined, against the 34.11% its Gate reports for pytest alone) from a
            // job in ci.yml, because 79 of its 102 modules are exercised by --selftest subprocesses
            // that pytest-cov cannot see. A guard that can only ever look at pr-00-gate.yml reports
            // "no coverage" for both, which is indistinguishable from a repo that has none.
            //
            // Read from config/coverage-baseline.json, which is the right home: it is already the
            // per-repo coverage config and is explicitly EXCLUDED from template sync ("Each repo
            // maintains its own coverage baseline"), so a repo can answer this without diverging
            // from the synced workflow.
            //
            // The default is exactly the previous behaviour, so no repo changes unless it opts in,
            // and an unreadable or malformed config falls back to it rather than failing: a guard
            // that died on its own config would be worse than one that looks in one place.
            const DEFAULT_WORKFLOWS = ['.github/workflows/pr-00-gate.yml'];
            const configuredWorkflowIds = (declared) =>
              Array.isArray(declared)
                ? declared
                    .filter((workflow) => typeof workflow === 'string')
                    .map((workflow) => workflow.trim())
                    .filter(Boolean)
                : [];
            const errorMessage = (error) =>
              error instanceof Error ? error.message : String(error);
            let workflowIds = DEFAULT_WORKFLOWS;
            let workflowSource = 'default';
            try {
              const cfgRaw = fs.readFileSync('config/coverage-baseline.json', 'utf8');
              const cfg = JSON.parse(cfgRaw);
              const declared = configuredWorkflowIds(cfg.source_workflows);
              if (declared.length) {
                workflowIds = declared;
                workflowSource = 'config/coverage-baseline.json';
              }
            } catch (err) {
              core.info(
                `coverage-baseline.json not read for source_workflows (${errorMessage(err)}); ` +
                  'using the default workflow list'
              );
            }
            core.info(`Searching for coverage in: ${workflowIds.join(', ')} (from ${workflowSource})`);
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { paginateWithRetry, withRetry } = retryHelpers;

            // Every configured workflow is listed and the runs POOLED, rather than stopping at the
            // first that returns anything. A repo can legitimately publish coverage from more than
            // one workflow, and taking only the first would make the ORDER of a config list into a
            // silent filter.
            let runs = [];
            const searched = [];
            for (const wf of workflowIds) {
              try {
                const found = await paginateWithRetry(
                  github, github.rest.actions.listWorkflowRuns,
                  {
                    owner,
                    repo,
                    workflow_id: wf,
                    status: 'completed',
                    per_page: 50,
                  },
                );
                const successfulForWorkflow = found
                  .filter((run) => ['success', 'neutral'].includes(run.conclusion || ''))
                  .sort(
                    (a, b) =>
                      new Date(b.run_started_at || b.created_at || 0) -
                      new Date(a.run_started_at || a.created_at || 0),
                  )
                  .slice(0, 10);
                searched.push(
                  `${wf} (${found.length} run(s); ${successfulForWorkflow.length} successful probed)`,
                );
                runs = runs.concat(successfulForWorkflow);
              } catch (err) {
                // A workflow named in config that does not exist here is a CONFIG error worth
                // naming, not a reason to abandon the others.
                searched.push(`${wf} (UNAVAILABLE: ${errorMessage(err)})`);
              }
            }

            if (!runs.length) {
              core.warning(`No successful or neutral completed runs found in: ${searched.join('; ')}`);
              core.setOutput('run_id', '');
              core.setFailed(
                'Coverage verification requires at least one successful or neutral completed run ' +
                  `in a configured workflow. Searched: ${searched.join('; ')}. If this repo ` +
                  'publishes coverage elsewhere, add source_workflows to config/coverage-baseline.json.'
              );
              return;
            }

            const runsToProbe = runs.sort(
              (a, b) =>
                new Date(b.run_started_at || b.created_at || 0) -
                new Date(a.run_started_at || a.created_at || 0),
            );
            // THE PAYLOAD IS THE ONLY REQUIREMENT, AND IT HAS TWO NAMES IN THE WILD.
            // pr-00-gate.yml uploads it under the ARTIFACT name `gate-coverage.json` (the FILE
            // inside is gate-coverage.json; the step conflated the two), while this guard was
            // written against `gate-coverage`. A paired literal in two files that disagreed, so
            // the guard probed ten successful runs, found two of three artifacts every time, and
            // reported no usable run at all -- in every consumer repo, for as long as it existed.
            //
            // Accept BOTH here rather than renaming the producer: pr-00-gate.yml is distributed
            // create-only, so a producer rename reaches NEW repos only, while this file is
            // sync-managed and reaches all of them.
            //
            // AND IT HAS A THIRD SHAPE, WHICH IS THE ONE ALMOST EVERY REPO ACTUALLY USES. The
            // producer runs under a version matrix, so the artifact it publishes is suffixed:
            // `gate-coverage-3.12-1` and `gate-coverage-3.13-1`. Measured 2026-08-30 across the
            // lane fleet, EIGHT repos published a trend, a summary and both suffixed payloads --
            // everything this job needs -- and every one was skipped, because an exact-name list
            // can never match a name that carries a matrix suffix. The guard had failed in all 13
            // repos, continuously; two more names would not have fixed it, so the match is by
            // PREFIX with the non-payload artifacts excluded by name.
            //
            // Note what the exclusions are: `-trend`, `-trend-history`, `-summary` and `-delta`
            // all share the `gate-coverage` prefix, so a bare prefix match would have selected the
            // TREND as the payload and compared coverage against itself.
            const coveragePayloadNames = ['gate-coverage', 'gate-coverage.json'];
            const payloadPrefix = 'gate-coverage';
            const notAPayload = /^gate-coverage-(trend|summary|delta)/;
            const payloadCandidates = (names) => {
              const exact = coveragePayloadNames.filter((name) => names.has(name));
              const suffixed = [...names]
                .filter((name) => name.startsWith(payloadPrefix) && !notAPayload.test(name))
                .filter((name) => !coveragePayloadNames.includes(name))
                .sort();
              // Exact names first so a repo where this already worked is untouched; the suffixed
              // ones are SORTED rather than taken in listing order, because the API's order is not
              // stable and a coverage figure that depends on it would move for no reason.
              return [...exact, ...suffixed];
            };
            // The guard cannot evaluate a baseline from the payload alone: coverage_guard.py
            // deliberately treats a missing trend payload as a no-op.  Only select runs that
            // carry the trend artifact, otherwise this job can report success without checking
            // coverage or updating a breach issue.
            const trendArtifactName = 'gate-coverage-trend';
            const historyArtifactName = 'gate-coverage-trend-history';
            let candidate = null;
            let resolvedPayloadName = '';
            let resolvedTrendName = '';
            let resolvedHistoryName = '';
            const seenCoverageArtifacts = new Set();
            const seenPayloadArtifacts = new Set();
            for (const run of runsToProbe) {
              let artifacts = [];
              try {
                artifacts = await paginateWithRetry(
                  github,
                  github.rest.actions.listWorkflowRunArtifacts,
                  {
                    owner,
                    repo,
                    run_id: run.id,
                    per_page: 100,
                  },
                );
              } catch (error) {
                core.warning(
                  `Skipping Gate run ${run.id}; artifact lookup failed: ${error.message}`,
                );
                continue;
              }

              // Accumulated ACROSS runs so the failure message can distinguish "no coverage
              // artifacts anywhere" from "artifacts under names this job cannot use". Those are
              // opposite findings and only one of them means coverage is off.
              const availableCoverageArtifactNames = new Set(
                artifacts
                  .filter((artifact) => !artifact.expired)
                  .map((artifact) => artifact.name),
              );
              for (const name of availableCoverageArtifactNames) {
                if (name.startsWith(payloadPrefix)) seenCoverageArtifacts.add(name);
              }
              const candidateNames = payloadCandidates(availableCoverageArtifactNames);
              for (const name of candidateNames) seenPayloadArtifacts.add(name);
              const payloadName = candidateNames[0] || '';
              if (candidateNames.length > 1) {
                core.info(
                  `Gate run ${run.id} carries ${candidateNames.length} coverage payloads ` +
                    `(${candidateNames.join(', ')}); using ${payloadName}. They are the same ` +
                    'suite on different interpreters, so the choice is fixed rather than left ' +
                    'to listing order.',
                );
              }
              const hasTrend = availableCoverageArtifactNames.has(trendArtifactName);
              if (payloadName && hasTrend) {
                candidate = run;
                resolvedPayloadName = payloadName;
                resolvedTrendName = trendArtifactName;
                resolvedHistoryName = availableCoverageArtifactNames.has(historyArtifactName)
                  ? historyArtifactName
                  : '';
                break;
              }
              core.info(
                [
                  `Skipping Gate run ${run.id}; required coverage artifacts are incomplete.`,
                  payloadName
                    ? `Found payload ${payloadName} but no ${trendArtifactName}.`
                    : seenCoverageArtifacts.size
                      ? `No usable payload among ${[...seenCoverageArtifacts].sort().join(', ')}.`
                      : 'This run published no gate-coverage artifacts at all.',
                ].join(' '),
              );
            }

            if (!candidate) {
              // THREE FINDINGS, NOT ONE. "This repo does not measure coverage", "it measures it
              // and publishes it under a name I do not recognise" and "it publishes a payload but
              // no trend" have completely different fixes, and the single message this replaced
              // asserted the first in all three cases. It told eight repos that were measuring
              // coverage, and publishing it, to go and switch coverage on.
              core.warning(
                seenCoverageArtifacts.size === 0
                  ? [
                      'Unable to locate a recent successful Gate workflow run carrying any',
                      'gate-coverage artifact. Coverage is most likely not being measured here:',
                      'check that the reusable CI caller sets coverage: true and',
                      'enable-soft-gate: true.',
                    ].join(' ')
                  : seenPayloadArtifacts.size === 0
                    ? [
                        'Gate runs DID publish gate-coverage artifacts, but none matched a',
                        'supported payload shape.',
                        `Seen: ${[...seenCoverageArtifacts].sort().join(', ')}.`,
                        `A payload is any gate-coverage* artifact except ${'-trend'}/-summary/-delta.`,
                        'Coverage IS being measured in this repo, but the payload names are',
                        'unusable by this guard; align the producer name or matcher.',
                      ].join(' ')
                    : [
                        'Gate runs DID publish usable coverage payloads, but none had the required',
                        `${trendArtifactName} on the same run.`,
                        `Payloads seen: ${[...seenPayloadArtifacts].sort().join(', ')}.`,
                        'Coverage IS being measured in this repo; publish the missing trend',
                        'artifact rather than enabling coverage again.',
                      ].join(' '),
              );
              core.setOutput('run_id', '');
              const missingPairReason =
                seenCoverageArtifacts.size === 0
                  ? 'no gate-coverage artifacts were published'
                  : seenPayloadArtifacts.size === 0
                    ? 'published coverage artifact names did not match a supported payload shape'
                    : `coverage payloads were published without ${trendArtifactName}`;
              core.setFailed(`Coverage verification could not proceed: ${missingPairReason}.`);
              return;
            }

            core.setOutput('run_id', String(candidate.id || ''));
            core.setOutput('run_number', String(candidate.run_number || ''));
            // The downloader learns the names from the producer's actual artifact list instead of
            // repeating a literal. A name that is discovered cannot drift from the name that
            // exists, which is the whole defect this replaces.
            core.setOutput('coverage_artifact_name', resolvedPayloadName);
            core.setOutput('trend_artifact_name', resolvedTrendName);
            core.setOutput('history_artifact_name', resolvedHistoryName);
            core.setOutput('run_url', candidate.html_url || '');
            const url = candidate.html_url || 'no url';
            core.notice(`Using Gate workflow run ${candidate.id} (${url})`);

      - name: Download coverage trend artifact
        if: ${{ steps.discover.outputs.trend_artifact_name }}
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8
        with:
          name: ${{ steps.discover.outputs.trend_artifact_name }}
          run-id: ${{ steps.discover.outputs.run_id }}
          path: coverage_artifacts/trend
          github-token: ${{ secrets.GITHUB_TOKEN }}

      # Each immutable cache saves the accumulated history after this guard run.
      # Restore the newest repository history, independently of the producer run.
      - name: Restore coverage recovery history
        if: ${{ steps.discover.outputs.run_id }}
        id: coverage-trend-history-cache
        uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
        with:
          path: coverage_artifacts/history
          key: coverage-guard-history-v1-${{ github.repository }}-${{ github.run_id }}-${{ github.run_attempt }}
          restore-keys: |
            coverage-guard-history-v1-${{ github.repository }}-

      - name: Download coverage payload artifact
        if: ${{ steps.discover.outputs.coverage_artifact_name }}
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8
        with:
          name: ${{ steps.discover.outputs.coverage_artifact_name }}
          run-id: ${{ steps.discover.outputs.run_id }}
          path: coverage_artifacts/payload
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Run coverage guard
        if: ${{ steps.discover.outputs.run_id }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          COVERAGE_RUN_URL: ${{ steps.discover.outputs.run_url }}
          COVERAGE_RUN_NUMBER: ${{ steps.discover.outputs.run_number }}
        run: |
          # Try multiple possible artifact paths (workflow uses different naming)
          TREND_PATH=""
          COVERAGE_PATH=""
          HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"

          # Check for trend artifact
          for candidate in \
            "coverage_artifacts/trend/coverage-trend.json" \
            "coverage_artifacts/coverage-trend.json"; do
            if [ -f "$candidate" ]; then
              TREND_PATH="$candidate"
              break
            fi
          done

          # Check for trend history artifact
          for candidate in \
            "coverage_artifacts/history/coverage-trend-history.ndjson" \
            "coverage_artifacts/trend/coverage-trend-history.ndjson" \
            "coverage_artifacts/coverage-trend-history.ndjson"; do
            if [ -f "$candidate" ]; then
              HISTORY_PATH="$candidate"
              break
            fi
          done

          # Check for coverage json
          # THE ARTIFACT IS FOUND AND THE FILE INSIDE IT IS NOT. This list is the same shape of
          # defect as the artifact-NAME list one step earlier: seven hardcoded paths against a
          # producer that writes somewhere else. Verified 2026-08-30 by downloading
          # stranske/Counter_Risk's real `gate-coverage-3.12-1` -- it holds `index.ndjson` and
          # `runtimes/3.12/coverage.json`, extracting to
          # `coverage_artifacts/payload/runtimes/3.12/coverage.json`, one directory level from the
          # first candidate and matched by none of them. The list also hardcodes the Python
          # versions, so a matrix change breaks it silently and later.
          #
          # Literals first, so a repo where they already work is untouched and this change cannot
          # alter a working resolution. Then FIND the payload rather than guess where it is: a
          # file is the payload when it PARSES and carries `totals.percent_covered`, which is what
          # the guard actually reads. That test cannot drift from the producer's directory layout,
          # because it does not mention the layout.
          for candidate in \
            "coverage_artifacts/payload/coverage/runtimes/3.14/coverage.json" \
            "coverage_artifacts/payload/coverage/runtimes/3.13/coverage.json" \
            "coverage_artifacts/payload/artifacts/coverage/runtimes/3.14/coverage.json" \
            "coverage_artifacts/payload/artifacts/coverage/runtimes/3.13/coverage.json" \
            "coverage_artifacts/payload/gate-coverage.json" \
            "coverage_artifacts/payload/coverage.json" \
            "coverage_artifacts/coverage.json"; do
            if [ -f "$candidate" ]; then
              COVERAGE_PATH="$candidate"
              break
            fi
          done
          # `sort` so an artifact holding two runtimes resolves to the SAME file every run: they
          # are one suite on different interpreters, and a figure that moved with directory order
          # would be noise reported as a coverage change.
          if [ -z "$COVERAGE_PATH" ]; then
            while IFS= read -r found; do
              if python -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if isinstance(d,dict) and 'percent_covered' in (d.get('totals') or {}) else 1)" "$found" 2>/dev/null; then
                COVERAGE_PATH="$found"
                echo "::notice title=Coverage payload located by search::No known path matched; found ${found} by looking for a JSON carrying totals.percent_covered."
                break
              fi
            done < <(find coverage_artifacts -type f -name '*.json' 2>/dev/null | sort)
          fi

          # Build args
          ARGS=(
            --repo "${{ github.repository }}"
            --run-url "${{ steps.discover.outputs.run_url }}"
          )

          if [ -n "$TREND_PATH" ]; then
            ARGS+=(--trend-path "$TREND_PATH")
          fi

          if [ -n "$COVERAGE_PATH" ]; then
            ARGS+=(--coverage-path "$COVERAGE_PATH")
          fi

          if [ -n "$HISTORY_PATH" ]; then
            ARGS+=(--history-path "$HISTORY_PATH")
          fi

          if [ -f "config/coverage-baseline.json" ]; then
            ARGS+=(--baseline-path "config/coverage-baseline.json")
          fi

          if [ -z "$TREND_PATH" ] || [ -z "$COVERAGE_PATH" ]; then
            echo "Required coverage artifacts are missing after download."
            echo "TREND_PATH=${TREND_PATH:-<missing>}"
            echo "COVERAGE_PATH=${COVERAGE_PATH:-<missing>}"
            # WHAT WAS ACTUALLY THERE. Without this, the message says a file is missing and gives
            # no way to tell "the artifact was empty" from "the artifact was full and nothing in
            # it looked like a coverage report" -- and the second is what really happened.
            echo "--- files downloaded (the search covered every .json among these) ---"
            find coverage_artifacts -type f 2>/dev/null | head -50 || echo "(coverage_artifacts is absent or empty)"
            exit 1
          fi

          python tools/coverage_guard.py "${ARGS[@]}"

      - name: Save coverage recovery history
        if: ${{ always() && steps.discover.outputs.run_id && hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson') != '' }}
        uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6
        with:
          path: coverage_artifacts/history
          key: ${{ steps.coverage-trend-history-cache.outputs.cache-primary-key }}


  # A SKIPPED GUARD USED TO BE INDISTINGUISHABLE FROM A PASSING ONE. `guard` is gated on the
  # rate-limit job, so when quota is low the job is skipped and the WORKFLOW IS GREEN with nothing
  # checked. stranske/Workflows' three most recent runs all read `success` at the workflow level
  # and `coverage baseline monitor: skipped` at the job level -- which is how a monitor that has
  # never once executed came to look healthy for months. This job always runs and says which
  # happened, so the run's own summary distinguishes "checked, and it was fine" from "did not
  # check". It deliberately does NOT fail on a deferral: the quota gate is legitimate, and turning
  # a deferral into a red would train everyone to ignore the red.
  report:
    name: coverage guard outcome
    needs: [rate-limit-check, guard]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Record whether the guard actually evaluated
        env:
          PROCEED: ${{ needs.rate-limit-check.outputs.proceed }}
          GUARD_RESULT: ${{ needs.guard.result }}
        run: |
          if [ "${GUARD_RESULT}" = "skipped" ]; then
            if [ "${PROCEED}" = "true" ]; then
              REASON="the guard job was skipped for a reason other than API quota"
            else
              REASON="API quota was below the threshold, so the check was deferred"
            fi
            {
              echo "### Coverage guard: NOT EVALUATED"
              echo ""
              echo "Coverage was **not** checked on this run - ${REASON}."
              echo "A green run here does not mean coverage is healthy."
            } >> "$GITHUB_STEP_SUMMARY"
            echo "::notice title=Coverage guard not evaluated::${REASON}"
          else
            echo "### Coverage guard: evaluated (${GUARD_RESULT})" >> "$GITHUB_STEP_SUMMARY"
          fi

```

### tests/test_coverage_guard.py @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
import datetime as dt
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import coverage_guard


@pytest.fixture(autouse=True)
def isolate_guard_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default-path CLI calls must not share persisted samples between tests."""
    monkeypatch.chdir(tmp_path)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_baseline_applies_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "baseline.json"
    _write_json(
        config_path,
        {
            "line": 86.5,
            "warn_drop": 0.75,
            "recovery_days": "7",
        },
    )

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(86.5)
    assert baseline.warn_drop == pytest.approx(0.75)
    assert baseline.recovery_days == 7


def test_load_baseline_enforces_minimum_recovery_days(tmp_path: Path) -> None:
    config_path = tmp_path / "baseline.json"
    _write_json(
        config_path,
        {
            "line": 85.0,
            "warn_drop": 1.0,
            "recovery_days": 0,
        },
    )

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 3


def test_coverage_breach_requires_drop_beyond_warn_threshold() -> None:
    assert not coverage_guard.is_coverage_breach(84.0, 85.0, 1.0)
    assert coverage_guard.is_coverage_breach(83.99, 85.0, 1.0)


def test_compute_top_files_prioritises_missing_lines() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            },
            "src/b.py": {
                "summary": {
                    "percent_covered": 70.0,
                    "covered_lines": 7,
                    "missing_lines": 3,
                    "num_statements": 10,
                }
            },
            "src/c.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 10,
                    "missing_lines": 0,
                    "num_statements": 10,
                }
            },
        }
    }

    top = coverage_guard.compute_top_files(coverage, limit=2)

    assert [item.path for item in top] == ["src/a.py", "src/b.py"]
    assert all(item.missing > 0 for item in top)


def test_compute_top_files_falls_back_to_total_lines() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 40,
                    "missing_lines": 0,
                    "num_statements": 40,
                }
            },
            "src/b.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 10,
                    "missing_lines": 0,
                    "num_statements": 10,
                }
            },
        }
    }

    top = coverage_guard.compute_top_files(coverage, limit=2)

    assert [item.path for item in top] == ["src/a.py", "src/b.py"]


def test_build_update_comment_formats_metrics() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)
    files = [
        coverage_guard.FileCoverage(
            path="src/a.py",
            percent=60.0,
            covered=6,
            total=10,
            missing=4,
        ),
        coverage_guard.FileCoverage(
            path="src/b.py",
            percent=75.0,
            covered=15,
            total=20,
            missing=5,
        ),
    ]

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress=None,
        top_files=files,
    )

    assert "2024-12-31" in comment
    assert "Current coverage: 82.30%" in comment
    assert "Baseline coverage: 85.00%" in comment
    assert "Delta vs baseline: -2.70 pts" in comment
    assert "Top changed files" in comment
    assert "src/a.py" in comment


def test_build_update_comment_handles_missing_files() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=86.0, baseline=85.0, delta=1.0)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2025, 1, 1)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=False,
        date=today,
        run_url="",
        recovery_progress="1/3 days above baseline",
        top_files=[],
    )

    assert "2025-01-01" in comment
    assert "Status: At or above baseline" in comment
    assert "Top changed files unavailable" in comment


def test_build_recovered_comment_announces_closure() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=86.0, baseline=85.0, delta=1.0)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=4)
    today = dt.date(2025, 1, 4)

    message = coverage_guard.build_recovered_comment(snapshot, config, today)

    assert "Coverage recovered above baseline" in message
    assert "4 consecutive days" in message
    assert "Closing this issue" in message


def test_find_or_create_issue_updates_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            stdout = json.dumps([{"number": 123, "title": "[coverage] baseline breach"}])
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    assert any(call[0][:3] == ["gh", "issue", "list"] for call in calls)
    assert any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)
    assert not any(call[0][:3] == ["gh", "issue", "create"] for call in calls)


def test_find_or_create_issue_reopens_closed_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            stdout = json.dumps(
                [{"number": 123, "title": "[coverage] baseline breach", "state": "CLOSED"}]
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    assert any(call[0][:3] == ["gh", "issue", "reopen"] for call in calls)
    assert any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)


def test_find_or_create_issue_creates_new(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    assert any(call[0][:3] == ["gh", "issue", "list"] for call in calls)
    assert any(call[0][:3] == ["gh", "issue", "create"] for call in calls)
    create_call = next(call[0] for call in calls if call[0][:3] == ["gh", "issue", "create"])
    assert create_call.count("--label") == 2
    assert not any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)


def test_find_or_create_issue_retries_without_missing_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ["gh", "issue", "create"] and "--label" in args:
            raise subprocess.CalledProcessError(1, args, stderr="could not resolve label")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    create_calls = [call[0] for call in calls if call[0][:3] == ["gh", "issue", "create"]]
    assert len(create_calls) == 2
    assert "--label" in create_calls[0]
    assert "--label" not in create_calls[1]


def test_find_existing_issue_requires_exact_title(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        stdout = json.dumps(
            [
                {"number": 123, "title": "coverage baseline breach", "state": "OPEN"},
                {"number": 456, "title": "[coverage] baseline breach details", "state": "OPEN"},
            ]
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert coverage_guard._find_existing_issue("octo/repo", "[coverage] baseline breach") is None
    assert all(args[args.index("--limit") + 1] == "200" for args in calls)


def test_find_existing_issue_falls_back_to_title_only_when_label_search_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--label" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        stdout = json.dumps([{"number": 123, "title": "[coverage] baseline breach"}])
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    issue = coverage_guard._find_existing_issue(
        "octo/repo",
        "[coverage] baseline breach",
        labels=["coverage", "automated"],
    )

    assert issue == {"number": 123, "title": "[coverage] baseline breach"}
    assert any("--label" in args for args in calls)
    assert any("--label" not in args for args in calls)


def test_find_existing_issue_returns_none_after_label_and_title_search_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert (
        coverage_guard._find_existing_issue(
            "octo/repo",
            "[coverage] baseline breach",
            labels=["coverage", "automated"],
        )
        is None
    )
    assert any("--label" in args for args in calls)
    assert any("--label" not in args for args in calls)


def test_find_existing_issue_retries_title_only_when_label_search_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--label" in args:
            return SimpleNamespace(returncode=1, stdout="", stderr="could not resolve label")
        stdout = json.dumps([{"number": 123, "title": "[coverage] baseline breach"}])
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    issue = coverage_guard._find_existing_issue(
        "octo/repo",
        "[coverage] baseline breach",
        labels=["coverage"],
    )

    assert issue == {"number": 123, "title": "[coverage] baseline breach"}
    assert any("--label" in args for args in calls)
    assert any("--label" not in args for args in calls)


def test_main_invokes_issue_management_when_below_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    coverage_path = tmp_path / "coverage.json"
    _write_json(trend_path, {"current": 64.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 1})
    _write_json(
        coverage_path,
        {"files": {"src/app.py": {"summary": {"percent_covered": 64.0, "missing_lines": 3}}}},
    )

    calls = []

    def fake_issue(repo, title, body, labels):
        calls.append((repo, title, body, labels))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--coverage-path",
            str(coverage_path),
            "--baseline-path",
            str(baseline_path),
            "--run-url",
            "https://example/run",
        ]
    )

    assert exit_code == 0
    assert calls
    assert calls[0][0] == "octo/repo"
    assert calls[0][3] == ["coverage", "automated"]


def test_main_accepts_issue_label_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 64.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0})

    calls = []

    def fake_issue(repo, title, body, labels):
        calls.append((repo, title, body, labels))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--issue-label",
            "coverage",
            "--issue-label",
            "ci",
        ]
    )

    assert exit_code == 0
    assert calls[0][3] == ["coverage", "ci"]


def test_main_skips_issue_management_when_at_or_above_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 72.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 1})

    create_calls = []
    close_calls = []

    def fake_issue(*args, **kwargs):
        create_calls.append((args, kwargs))

    def fake_close(*args, **kwargs):
        close_calls.append((args, kwargs))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)
    monkeypatch.setattr(coverage_guard, "_close_existing_issue", fake_close)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert not create_calls
    assert close_calls


def test_main_leaves_issue_open_until_recovery_window_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        trend_path,
        {
            "current": 72.0,
            "baseline": 70.0,
            "history": [{"current": 68.0}, {"current": 72.0}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert not close_calls


def test_main_closes_existing_issue_after_within_allowance_recovery_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "coverage-trend-history.ndjson"
    _write_json(
        trend_path,
        {
            "current": 69.5,
            "baseline": 70.0,
            "history": [{"current": 69.5}, {"current": 69.5}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "warn_drop": 1.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    assert close_calls
    recovery_body = close_calls[0][0][2]
    assert "configured warning threshold" in recovery_body


def test_main_requires_baseline_samples_when_current_meets_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "coverage-trend-history.ndjson"
    _write_json(
        trend_path,
        {
            "current": 72.0,
            "baseline": 70.0,
            "history": [{"current": 69.5}, {"current": 72.0}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "warn_drop": 1.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    assert not close_calls


def test_main_preserves_default_recovery_window_within_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        trend_path,
        {
            "current": 69.5,
            "baseline": 70.0,
            "history": [{"current": 69.5}, {"current": 69.5}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "warn_drop": 1.0})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(tmp_path / "coverage-trend-history.ndjson"),
        ]
    )

    assert exit_code == 0
    assert not close_calls


def test_main_closes_existing_issue_when_baseline_recovery_window_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        trend_path,
        {
            "current": 72.0,
            "baseline": 70.0,
            "history": [{"current": 71.0}, {"current": 72.0}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(tmp_path / "coverage-trend-history.ndjson"),
        ]
    )

    assert exit_code == 0
    assert close_calls
    recovery_body = close_calls[0][0][2]
    assert "configured baseline" in recovery_body


def test_main_uses_embedded_history_when_history_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        trend_path,
        {
            "current": 72.0,
            "baseline": 70.0,
            "history": [{"current": 71.0}, {"current": 72.0}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert close_calls


def test_main_uses_history_file_for_recovery_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "coverage-trend-history.ndjson"
    _write_json(trend_path, {"current": 72.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0, "recovery_days": 2})
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"current": 71.0}),
                json.dumps({"current": 72.0}),
            ]
        ),
        encoding="utf-8",
    )

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    assert close_calls


def test_recovery_window_counts_same_coverage_from_distinct_runs() -> None:
    trend_data = {"current": 72.0, "run_id": "run-2"}
    history_records = [{"current": 72.0, "run_id": "run-1"}]

    assert coverage_guard._recovery_window_satisfied(
        trend_data,
        baseline=70.0,
        recovery_window=2,
        history_records=history_records,
    )


@pytest.mark.parametrize(
    "restored_run_ids",
    [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
    ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
)
def test_recovery_window_counts_records_accumulated_across_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
) -> None:
    """Restored runs accumulate while retries replace stale samples without inflating the window."""
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "history.ndjson"
    _write_json(trend_path, {"current": 90.0, "run_id": "3"})
    _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
    history_path.write_text(
        "\n".join(
            json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
            for run_id in restored_run_ids
        ),
        encoding="utf-8",
    )
    closed = []
    monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
    args = [
        "--repo",
        "octo/repo",
        "--trend-path",
        str(trend_path),
        "--baseline-path",
        str(baseline_path),
        "--history-path",
        str(history_path),
    ]
    assert coverage_guard.main(args) == 0
    assert len(closed) == 1
    assert [r["run_id"] for r in coverage_guard._load_ndjson(history_path)] == ["1", "2", "3"]
    assert coverage_guard._load_ndjson(history_path)[-1]["current"] == 90.0
    # Retrying the same Gate run cannot supply another recovery sample.
    assert coverage_guard.main(args) == 0
    assert len(coverage_guard._load_ndjson(history_path)) == 3
    history_path.unlink()
    closed.clear()
    assert coverage_guard.main(args) == 0
    assert not closed
    assert len(coverage_guard._load_ndjson(history_path)) == 1
    assert coverage_guard.main(args) == 0
    assert not closed
    assert len(coverage_guard._load_ndjson(history_path)) == 1


@pytest.mark.parametrize(
    ("restored_coverage", "recovered_records"),
    [((90.0,), 2), ((80.0,), 1), ((90.0, 90.0, 80.0), 2), ((), 1)],
    ids=["two-recovered", "one-below-baseline", "latest-window-only", "current-alone"],
)
def test_recovery_message_names_records_held_and_needed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restored_coverage: tuple[float, ...],
    recovered_records: int,
) -> None:
    """Progress names the qualifying records within the latest window and the required size."""
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "history.ndjson"
    _write_json(trend_path, {"current": 90.0, "run_id": str(len(restored_coverage) + 1)})
    _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
    history_path.write_text(
        "\n".join(
            json.dumps({"current": current, "run_id": str(n)})
            for n, current in enumerate(restored_coverage, start=1)
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        coverage_guard, "_close_existing_issue", lambda *a, **kw: pytest.fail("premature closure")
    )
    assert (
        coverage_guard.main(
            [
                "--repo",
                "octo/repo",
                "--trend-path",
                str(trend_path),
                "--baseline-path",
                str(baseline_path),
                "--history-path",
                str(history_path),
            ]
        )
        == 0
    )
    assert f"{recovered_records} of 3 records at or above the baseline" in capsys.readouterr().out


def test_recovery_history_retains_latest_thirty_unique_runs() -> None:
    history = [{"current": 90.0, "run_id": str(n)} for n in range(35)]
    history.insert(0, {"current": 80.0, "run_id": "34"})
    records = coverage_guard._accumulate_recovery_history(
        {"current": 91.0, "run_id": "34"}, history, ""
    )
    assert len(records) == 30
    assert [r["run_id"] for r in records] == [str(n) for n in range(5, 35)]
    assert records[-1]["current"] == 91.0


def test_recovery_window_accepts_aggregate_history_records() -> None:
    trend_data = {"current": 72.0, "run_id": "run-3"}
    history_records = [
        {"avg_coverage": 74.0, "run_id": "run-1"},
        {"worst_job_coverage": 71.0, "run_id": "run-2"},
    ]

    assert coverage_guard._recovery_window_satisfied(
        trend_data,
        baseline=70.0,
        recovery_window=3,
        history_records=history_records,
    )


def test_recovery_window_uses_worst_job_before_average() -> None:
    trend_data = {"current": 72.0, "run_id": "run-2"}
    history_records = [{"avg_coverage": 80.0, "worst_job_coverage": 69.0, "run_id": "run-1"}]

    assert not coverage_guard._recovery_window_satisfied(
        trend_data,
        baseline=70.0,
        recovery_window=2,
        history_records=history_records,
    )


def test_main_uses_trend_baseline_when_baseline_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    coverage_path = tmp_path / "coverage.json"
    _write_json(trend_path, {"current": 60.0, "baseline": 65.0})
    _write_json(
        coverage_path,
        {"files": {"src/app.py": {"summary": {"percent_covered": 60.0, "missing_lines": 4}}}},
    )

    calls = []

    def fake_issue(repo, title, body, labels):
        calls.append((repo, title, body, labels))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--coverage-path",
            str(coverage_path),
        ]
    )

    assert exit_code == 0
    assert calls


def test_main_skips_when_baseline_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "missing-baseline.json"
    _write_json(trend_path, {"current": 60.0})

    calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_find_or_create_issue",
        lambda *args, **kwargs: calls.append(args),
    )
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: calls.append(args),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert not calls


def test_main_accepts_legacy_coverage_baseline_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 72.0, "baseline": 65.0})
    _write_json(baseline_path, {"coverage": 75.0})

    calls = []

    def fake_issue(repo, title, body, labels):
        calls.append((repo, title, body, labels))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert calls
    assert "baseline: 75.00%" in calls[0][2]


def test_main_dry_run_prints_issue_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 60.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0})

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--run-url",
            "https://example/run",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Coverage Baseline Breach Report" in captured.out


def test_load_json_handles_missing_and_invalid(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    invalid = tmp_path / "invalid.json"
    non_dict = tmp_path / "list.json"
    invalid.write_text("{not-json}", encoding="utf-8")
    non_dict.write_text("[]", encoding="utf-8")

    assert coverage_guard._load_json(missing) == {}
    assert coverage_guard._load_json(invalid) == {}
    assert coverage_guard._load_json(non_dict) == {}


def test_numeric_coercion_rejects_non_finite_values() -> None:
    assert coverage_guard._to_float("nan", 12.0) == 12.0
    assert coverage_guard._to_float(float("inf"), 12.0) == 12.0
    assert coverage_guard._to_int("inf", 7) == 7
    assert coverage_guard._to_int(float("-inf"), 7) == 7


def test_get_hotspots_sorts_and_limits() -> None:
    coverage_data = {
        "files": {
            "src/high.py": {"summary": {"percent_covered": 90.0, "missing_lines": 1}},
            "src/low.py": {"summary": {"percent_covered": 10.0, "missing_lines": 9}},
            "src/mid.py": {"summary": {"percent_covered": 50.0, "missing_lines": 4}},
        }
    }

    hotspots = coverage_guard._get_hotspots(coverage_data, limit=2)

    assert [spot["file"] for spot in hotspots] == ["src/low.py", "src/mid.py"]
    assert hotspots[0]["missing_lines"] == 9


def test_get_hotspots_handles_unexpected_payloads() -> None:
    assert coverage_guard._get_hotspots({"files": []}) == []
    assert coverage_guard._get_hotspots({"files": {"bad.py": []}}) == []
    assert (
        coverage_guard._get_hotspots({"files": {"bad.py": {"summary": {"percent_covered": "nan"}}}})
        == []
    )


def test_main_skips_when_trend_payload_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_issue(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)
    monkeypatch.setattr(coverage_guard, "_close_existing_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--coverage-path",
            str(tmp_path / "coverage.json"),
        ]
    )

    assert exit_code == 0
    assert not calls


def test_format_issue_body_includes_hotspots() -> None:
    body = coverage_guard._format_issue_body(
        current=60.0,
        baseline=70.0,
        delta=-10.0,
        hotspots=[{"file": "src/app.py", "coverage": 60.0, "missing_lines": 4}],
        run_url="https://example/run",
    )

    assert "Coverage Baseline Breach Report" in body
    assert "| `src/app.py` | 60.0% | 4 |" in body
    assert "Gate Workflow Run" in body


def test_format_issue_body_handles_no_hotspots() -> None:
    body = coverage_guard._format_issue_body(
        current=72.0,
        baseline=70.0,
        delta=2.0,
        hotspots=[],
        run_url="https://example/run",
    )

    assert "| _(no files with low coverage)_ | - | - |" in body


def test_format_issue_body_handles_missing_run_url() -> None:
    body = coverage_guard._format_issue_body(
        current=60.0,
        baseline=70.0,
        delta=-10.0,
        hotspots=[],
        run_url="",
    )

    assert "Run URL unavailable." in body
    assert "Gate Workflow Run]()" not in body


def test_main_skips_when_current_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    _write_json(trend_path, {"current": "nan", "baseline": 70.0})

    calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_find_or_create_issue",
        lambda *args, **kwargs: calls.append(args),
    )
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: calls.append(args),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
        ]
    )

    assert exit_code == 0
    assert not calls


def test_close_existing_issue_skips_already_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_find_existing_issue",
        lambda repo, title, labels=None: {"number": 123, "state": "CLOSED"},
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    coverage_guard._close_existing_issue("octo/repo", "[coverage] baseline breach", "body")

    assert not calls


def test_find_existing_issue_retries_title_only_after_label_search_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--label" in args:
            return SimpleNamespace(returncode=1, stdout="", stderr="label unavailable")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"number": 5, "title": 'a "quoted" title', "state": "OPEN"}]),
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    assert coverage_guard._find_existing_issue("octo/repo", 'a "quoted" title', ["coverage"]) == {
        "number": 5,
        "title": 'a "quoted" title',
        "state": "OPEN",
    }
    assert len(calls) == 2


def test_find_existing_issue_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="not json", stderr=""),
    )

    with pytest.raises(RuntimeError, match="invalid JSON"):
        coverage_guard._find_existing_issue("octo/repo", "title")


@pytest.mark.parametrize("comment_fails", [False, True])
def test_close_existing_issue_posts_then_closes(
    monkeypatch: pytest.MonkeyPatch, comment_fails: bool
) -> None:
    calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_find_existing_issue",
        lambda *args, **kwargs: {"number": 7, "state": "OPEN"},
    )

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if comment_fails and "comment" in args:
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, args, stderr="comment rejected")
            return SimpleNamespace(returncode=1, stdout="", stderr="comment rejected")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    if comment_fails:
        with pytest.raises(subprocess.CalledProcessError, match="returned non-zero exit status 1"):
            coverage_guard._close_existing_issue("octo/repo", "title", "body", labels=["coverage"])
    else:
        coverage_guard._close_existing_issue("octo/repo", "title", "body", labels=["coverage"])

    expected = [["gh", "issue", "comment", "7", "--repo", "octo/repo", "--body", "body"]]
    if not comment_fails:
        expected.append(
            ["gh", "issue", "close", "7", "--repo", "octo/repo", "--reason", "completed"]
        )
    assert [args for args, _ in calls] == expected
    assert all(kwargs.get("check") is True for _, kwargs in calls)


# Tests for _load_ndjson


def test_load_ndjson_handles_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"
    assert coverage_guard._load_ndjson(missing) == []


def test_load_ndjson_handles_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.ndjson"
    empty.write_text("", encoding="utf-8")
    assert coverage_guard._load_ndjson(empty) == []


def test_load_ndjson_handles_whitespace_only(tmp_path: Path) -> None:
    whitespace = tmp_path / "whitespace.ndjson"
    whitespace.write_text("  \n  \n", encoding="utf-8")
    assert coverage_guard._load_ndjson(whitespace) == []


def test_load_ndjson_parses_valid_records(tmp_path: Path) -> None:
    ndjson_file = tmp_path / "valid.ndjson"
    ndjson_file.write_text(
        '{"a": 1}\n{"b": 2}\n{"c": 3}',
        encoding="utf-8",
    )
    result = coverage_guard._load_ndjson(ndjson_file)
    assert len(result) == 3
    assert result[0] == {"a": 1}
    assert result[1] == {"b": 2}
    assert result[2] == {"c": 3}


def test_load_ndjson_skips_invalid_lines(tmp_path: Path) -> None:
    ndjson_file = tmp_path / "mixed.ndjson"
    ndjson_file.write_text(
        '{"a": 1}\n{invalid}\n{"b": 2}',
        encoding="utf-8",
    )
    result = coverage_guard._load_ndjson(ndjson_file)
    assert len(result) == 2
    assert result[0] == {"a": 1}
    assert result[1] == {"b": 2}


def test_load_ndjson_skips_non_dict_records(tmp_path: Path) -> None:
    ndjson_file = tmp_path / "non_dict.ndjson"
    ndjson_file.write_text(
        '[1, 2]\n"string"\n{"a": 1}',
        encoding="utf-8",
    )
    result = coverage_guard._load_ndjson(ndjson_file)
    assert len(result) == 1
    assert result[0] == {"a": 1}


# Tests for _parse_finite_float


def test_parse_finite_float_handles_valid_integers() -> None:
    assert coverage_guard._parse_finite_float(42) == 42.0
    assert coverage_guard._parse_finite_float(0) == 0.0
    assert coverage_guard._parse_finite_float(-10) == -10.0


def test_parse_finite_float_handles_valid_floats() -> None:
    assert coverage_guard._parse_finite_float(3.14) == 3.14
    assert coverage_guard._parse_finite_float(-2.5) == -2.5
    assert coverage_guard._parse_finite_float(0.0) == 0.0


def test_parse_finite_float_handles_valid_strings() -> None:
    assert coverage_guard._parse_finite_float("42.5") == 42.5
    assert coverage_guard._parse_finite_float("3.14") == 3.14
    assert coverage_guard._parse_finite_float("-10") == -10.0
    assert coverage_guard._parse_finite_float("0") == 0.0


def test_parse_finite_float_rejects_boolean() -> None:
    assert coverage_guard._parse_finite_float(True) is None
    assert coverage_guard._parse_finite_float(False) is None


def test_parse_finite_float_rejects_non_numeric_strings() -> None:
    assert coverage_guard._parse_finite_float("not a number") is None
    assert coverage_guard._parse_finite_float("") is None
    assert coverage_guard._parse_finite_float("3.14.15") is None


def test_parse_finite_float_rejects_non_finite_values() -> None:
    assert coverage_guard._parse_finite_float(float("inf")) is None
    assert coverage_guard._parse_finite_float(float("-inf")) is None
    assert coverage_guard._parse_finite_float(float("nan")) is None
    assert coverage_guard._parse_finite_float("inf") is None
    assert coverage_guard._parse_finite_float("nan") is None


def test_parse_finite_float_rejects_none() -> None:
    assert coverage_guard._parse_finite_float(None) is None


def test_parse_finite_float_rejects_unsupported_types() -> None:
    assert coverage_guard._parse_finite_float([]) is None
    assert coverage_guard._parse_finite_float({}) is None
    assert coverage_guard._parse_finite_float(object()) is None


# Tests for _to_float


def test_to_float_handles_valid_integers() -> None:
    assert coverage_guard._to_float(42) == 42.0
    assert coverage_guard._to_float(0) == 0.0


def test_to_float_handles_valid_floats() -> None:
    assert coverage_guard._to_float(3.14) == 3.14
    assert coverage_guard._to_float(0.0) == 0.0


def test_to_float_handles_valid_strings() -> None:
    assert coverage_guard._to_float("42.5") == 42.5
    assert coverage_guard._to_float("3.14") == 3.14


def test_to_float_uses_default_for_none() -> None:
    assert coverage_guard._to_float(None, default=12.0) == 12.0


def test_to_float_uses_default_for_invalid() -> None:
    assert coverage_guard._to_float("not a number", default=12.0) == 12.0
    assert coverage_guard._to_float([], default=12.0) == 12.0
    assert coverage_guard._to_float({}, default=12.0) == 12.0


def test_to_float_uses_default_for_boolean() -> None:
    assert coverage_guard._to_float(True, default=12.0) == 12.0
    assert coverage_guard._to_float(False, default=12.0) == 12.0


def test_to_float_uses_default_for_non_finite() -> None:
    assert coverage_guard._to_float(float("inf"), default=12.0) == 12.0
    assert coverage_guard._to_float(float("nan"), default=12.0) == 12.0


def test_to_float_default_is_zero() -> None:
    assert coverage_guard._to_float("invalid") == 0.0
    assert coverage_guard._to_float(None) == 0.0


# Tests for _to_int


def test_to_int_handles_valid_integers() -> None:
    assert coverage_guard._to_int(42) == 42
    assert coverage_guard._to_int(0) == 0
    assert coverage_guard._to_int(-10) == -10


def test_to_int_handles_valid_floats() -> None:
    assert coverage_guard._to_int(3.14) == 3
    assert coverage_guard._to_int(3.99) == 3
    assert coverage_guard._to_int(-2.5) == -2
    assert coverage_guard._to_int(0.0) == 0


def test_to_int_handles_valid_strings() -> None:
    assert coverage_guard._to_int("42") == 42
    assert coverage_guard._to_int("3.14") == 3
    assert coverage_guard._to_int("3.99") == 3
    assert coverage_guard._to_int("-10") == -10


def test_to_int_uses_default_for_none() -> None:
    assert coverage_guard._to_int(None, default=7) == 7


def test_to_int_uses_default_for_invalid() -> None:
    assert coverage_guard._to_int("not a number", default=7) == 7
    assert coverage_guard._to_int([], default=7) == 7
    assert coverage_guard._to_int({}, default=7) == 7


def test_to_int_uses_default_for_boolean() -> None:
    assert coverage_guard._to_int(True, default=7) == 7
    assert coverage_guard._to_int(False, default=7) == 7


def test_to_int_uses_default_for_non_finite() -> None:
    assert coverage_guard._to_int(float("inf"), default=7) == 7
    assert coverage_guard._to_int(float("-inf"), default=7) == 7
    assert coverage_guard._to_int(float("nan"), default=7) == 7
    assert coverage_guard._to_int("inf", default=7) == 7
    assert coverage_guard._to_int("nan", default=7) == 7


def test_to_int_default_is_zero() -> None:
    assert coverage_guard._to_int("invalid") == 0
    assert coverage_guard._to_int(None) == 0


# Tests for load_baseline with defaults


def test_load_baseline_uses_all_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "empty.json"
    _write_json(config_path, {})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(80.0)
    assert baseline.warn_drop == pytest.approx(1.0)
    assert baseline.recovery_days == 3


def test_load_baseline_uses_coverage_key(tmp_path: Path) -> None:
    config_path = tmp_path / "coverage_key.json"
    _write_json(config_path, {"coverage": 85.0})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(85.0)


def test_load_baseline_uses_recovery_window_key(tmp_path: Path) -> None:
    config_path = tmp_path / "recovery_window.json"
    _write_json(config_path, {"line": 85.0, "recovery_window": 5})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 5


def test_load_baseline_uses_recovery_runs_key(tmp_path: Path) -> None:
    config_path = tmp_path / "recovery_runs.json"
    _write_json(config_path, {"line": 85.0, "recovery_runs": 4})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 4


def test_load_baseline_handles_string_values(tmp_path: Path) -> None:
    config_path = tmp_path / "string_values.json"
    _write_json(
        config_path,
        {
            "line": "85.5",
            "warn_drop": "0.5",
            "recovery_days": "5",
        },
    )

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(85.5)
    assert baseline.warn_drop == pytest.approx(0.5)
    assert baseline.recovery_days == 5


def test_load_baseline_handles_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.json"

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(80.0)
    assert baseline.warn_drop == pytest.approx(1.0)
    assert baseline.recovery_days == 3


def test_load_baseline_string_recovery_days(tmp_path: Path) -> None:
    config_path = tmp_path / "string_recovery.json"
    _write_json(config_path, {"line": 85.0, "recovery_days": "7"})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 7


# Tests for compute_top_files


def test_compute_top_files_returns_empty_for_invalid_files() -> None:
    assert coverage_guard.compute_top_files({"files": "not a dict"}) == []
    assert coverage_guard.compute_top_files({"files": []}) == []
    assert coverage_guard.compute_top_files({}) == []


def test_compute_top_files_returns_empty_for_zero_limit() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            },
        }
    }
    assert coverage_guard.compute_top_files(coverage, limit=0) == []
    assert coverage_guard.compute_top_files(coverage, limit=-1) == []


def test_compute_top_files_skips_invalid_file_entries() -> None:
    coverage = {
        "files": {
            "valid.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            },
            "invalid_path": {"bad": "data"},
            "invalid_summary": {"summary": "not a dict"},
            "missing_percent": {"summary": {"covered_lines": 5, "missing_lines": 5}},
            "none_percent": {"summary": {"percent_covered": None}},
        }
    }
    result = coverage_guard.compute_top_files(coverage)
    assert len(result) == 1
    assert result[0].path == "valid.py"


def test_compute_top_files_fallback_sorting_by_total_when_no_missing() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 5,
                    "missing_lines": 0,
                    "num_statements": 5,
                }
            },
            "src/b.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 10,
                    "missing_lines": 0,
                    "num_statements": 10,
                }
            },
            "src/c.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 8,
                    "missing_lines": 0,
                    "num_statements": 8,
                }
            },
        }
    }
    result = coverage_guard.compute_top_files(coverage, limit=3)
    assert [item.path for item in result] == ["src/b.py", "src/c.py", "src/a.py"]


def test_compute_top_files_uses_covered_plus_missing_when_total_missing() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                }
            },
        }
    }
    result = coverage_guard.compute_top_files(coverage)
    assert len(result) == 1
    assert result[0].total == 10


def test_compute_top_files_respects_limit() -> None:
    coverage = {
        "files": {
            f"file{i}.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            }
            for i in range(20)
        }
    }
    result = coverage_guard.compute_top_files(coverage, limit=5)
    assert len(result) == 5


# Tests for build_update_comment


def test_build_update_comment_with_recovery_progress_and_top_files() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)
    files = [
        coverage_guard.FileCoverage(
            path="src/a.py",
            percent=60.0,
            covered=6,
            total=10,
            missing=4,
        ),
    ]

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress="1/3 days above baseline",
        top_files=files,
    )

    assert "Recovery progress: 1/3 days above baseline" in comment
    assert "src/a.py" in comment
    assert "Below baseline" in comment


def test_build_update_comment_without_recovery_progress() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress=None,
        top_files=[],
    )

    assert "Recovery progress" not in comment
    assert "Top changed files unavailable" in comment


def test_build_update_comment_without_run_url() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="",
        recovery_progress=None,
        top_files=[],
    )

    assert "Run:" not in comment


def test_build_update_comment_above_baseline() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=86.0, baseline=85.0, delta=1.0)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2025, 1, 1)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=False,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress=None,
        top_files=[],
    )

    assert "Status: At or above baseline" in comment

```

### tests/workflows/test_maint_coverage_guard_artifacts.py @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
"""Regression checks for the source and bootstrap coverage-guard selectors."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/maint-coverage-guard.yml",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
    ],
)
def test_coverage_guard_selects_only_runs_with_payload_and_trend(workflow_path: str) -> None:
    workflow = Path(workflow_path).read_text(encoding="utf-8")

    assert (
        workflow.count("const hasTrend = availableCoverageArtifactNames.has(trendArtifactName);")
        == 1
    )
    assert workflow.count("if (payloadName && hasTrend)") == 1
    assert workflow.count("Coverage verification could not proceed: ${missingPairReason}.") == 1
    assert workflow.count("no gate-coverage artifacts were published") == 1
    assert workflow.count("published coverage artifact names did not match") == 1
    assert workflow.count("coverage payloads were published without ${trendArtifactName}") == 1
    assert '"coverage_artifacts/payload/gate-coverage.json"' in workflow


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/maint-coverage-guard.yml",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
    ],
)
def test_recovery_cache_survives_producer_runs_and_saves_after_guard(workflow_path: str) -> None:
    steps = yaml.safe_load(Path(workflow_path).read_text())["jobs"]["guard"]["steps"]
    restore = next(s for s in steps if s.get("id") == "coverage-trend-history-cache")
    guard = next(s for s in steps if s.get("name") == "Run coverage guard")
    save = next(s for s in steps if s.get("name") == "Save coverage recovery history")
    assert steps.index(restore) < steps.index(guard) < steps.index(save)
    assert restore["uses"].startswith("actions/cache/restore@")
    assert save["uses"].startswith("actions/cache/save@")
    assert restore["with"]["path"] == save["with"]["path"] == "coverage_artifacts/history"
    assert "github.repository" in restore["with"]["key"]
    assert "github.run_id" in restore["with"]["key"]
    assert "github.run_attempt" in restore["with"]["key"]
    assert "discover.outputs.run_id" not in restore["with"]["key"]
    prefix = restore["with"]["restore-keys"].strip()
    assert "github.repository" in prefix and "run_id" not in prefix
    assert restore["with"]["key"].startswith(prefix)
    assert 'HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"' in guard["run"]
    assert "cache-primary-key" in save["with"]["key"]
    assert "hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson')" in save["if"]

```

### tools/coverage_guard.py @ 40622701645e1c9c13ff28861ba606a3f78d2e4a
```
#!/usr/bin/env python3
"""Coverage guard script for maintaining baseline breach issues.

This script compares current coverage against a baseline and creates/updates
a tracking issue when coverage falls below the threshold.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TREND_PATH = Path("coverage-trend.json")
DEFAULT_COVERAGE_PATH = Path("coverage.json")
DEFAULT_BASELINE_PATH = Path("config/coverage-baseline.json")
DEFAULT_HISTORY_PATH = Path("coverage-trend-history.ndjson")
DEFAULT_BASELINE = 80.0
DEFAULT_WARN_DROP = 1.0
DEFAULT_RECOVERY_DAYS = 3


@dataclass(frozen=True)
class BaselineConfig:
    """Coverage baseline settings used by guard comments and issue policy."""

    baseline: float
    warn_drop: float
    recovery_days: int


@dataclass(frozen=True)
class CoverageSnapshot:
    """Current coverage state relative to the configured baseline."""

    current: float
    baseline: float
    delta: float


@dataclass(frozen=True)
class FileCoverage:
    """Coverage details for a file that needs attention."""

    path: str
    percent: float
    covered: int
    total: int
    missing: int


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON from a file, returning empty dict on error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    """Load newline-delimited JSON records from a file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _to_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float for numeric-ish values."""
    parsed = _parse_finite_float(value)
    return parsed if parsed is not None else default


def _parse_finite_float(value: Any) -> float | None:
    """Parse a finite float or return None for missing/invalid values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value)
        except (OverflowError, ValueError):
            return None
    else:
        return None
    return parsed if math.isfinite(parsed) else None


def _to_int(value: Any, default: int = 0) -> int:
    """Return an integer for numeric-ish values."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        return int(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
            if not math.isfinite(parsed):
                return default
            return int(parsed)
        except (OverflowError, ValueError):
            return default
    return default


def load_baseline(path: Path) -> BaselineConfig:
    """Load baseline configuration with conservative defaults."""
    payload = _load_json(path)
    baseline = _to_float(payload.get("line", payload.get("coverage")), DEFAULT_BASELINE)
    warn_drop = _to_float(payload.get("warn_drop"), DEFAULT_WARN_DROP)
    recovery_days = max(
        DEFAULT_RECOVERY_DAYS,
        _to_int(
            payload.get(
                "recovery_days",
                payload.get("recovery_window", payload.get("recovery_runs")),
            ),
            DEFAULT_RECOVERY_DAYS,
        ),
    )
    return BaselineConfig(
        baseline=baseline,
        warn_drop=warn_drop,
        recovery_days=recovery_days,
    )


def is_coverage_breach(current: float, baseline: float, warn_drop: float) -> bool:
    """Return whether coverage falls more than ``warn_drop`` points below baseline."""
    return current < baseline - warn_drop


def compute_top_files(coverage_data: dict[str, Any], limit: int = 15) -> list[FileCoverage]:
    """Return the most useful file-level coverage rows for issue comments."""
    files = coverage_data.get("files", {})
    if not isinstance(files, dict) or limit <= 0:
        return []

    rows: list[FileCoverage] = []
    for filepath, data in files.items():
        if not isinstance(filepath, str) or not isinstance(data, dict):
            continue
        summary = data.get("summary", {})
        if not isinstance(summary, dict):
            continue
        percent = _parse_finite_float(summary.get("percent_covered"))
        if percent is None:
            continue
        covered = _to_int(summary.get("covered_lines"))
        missing = _to_int(summary.get("missing_lines"))
        total = _to_int(summary.get("num_statements"), covered + missing)
        if total <= 0:
            total = covered + missing
        rows.append(
            FileCoverage(
                path=filepath,
                percent=percent,
                covered=covered,
                total=total,
                missing=missing,
            )
        )

    if any(row.missing > 0 for row in rows):
        rows = [row for row in rows if row.missing > 0]
        rows.sort(key=lambda row: (-row.missing, row.percent, row.path))
    else:
        rows.sort(key=lambda row: (-row.total, row.percent, row.path))
    return rows[:limit]


def build_update_comment(
    snapshot: CoverageSnapshot,
    config: BaselineConfig,
    *,
    below_baseline: bool,
    date: dt.date,
    run_url: str,
    recovery_progress: str | None,
    top_files: list[FileCoverage],
) -> str:
    """Build the durable coverage issue update comment."""
    status = "Below baseline" if below_baseline else "At or above baseline"
    lines = [
        "## Coverage guard update",
        "",
        f"Date: {date.isoformat()}",
        f"Status: {status}",
        f"Current coverage: {snapshot.current:.2f}%",
        f"Baseline coverage: {snapshot.baseline:.2f}%",
        f"Delta vs baseline: {snapshot.delta:+.2f} pts",
        f"Warning threshold: {config.warn_drop:.2f} pts",
        f"Recovery window: {config.recovery_days} days",
    ]
    if recovery_progress:
        lines.append(f"Recovery progress: {recovery_progress}")
    if run_url:
        lines.append(f"Run: {run_url}")

    lines.extend(["", "### Top changed files"])
    if top_files:
        lines.extend(
            [
                "",
                "| File | Coverage | Covered | Missing | Total |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in top_files:
            lines.append(
                f"| `{item.path}` | {item.percent:.2f}% | {item.covered} | "
                f"{item.missing} | {item.total} |"
            )
    else:
        lines.append("")
        lines.append("Top changed files unavailable.")
    return "\n".join(lines)


def build_recovered_comment(
    snapshot: CoverageSnapshot,
    config: BaselineConfig,
    date: dt.date,
) -> str:
    """Build the comment used when closing a recovered coverage issue."""
    return "\n".join(
        [
            "Coverage recovered above baseline.",
            "",
            f"Date: {date.isoformat()}",
            f"Current coverage: {snapshot.current:.2f}%",
            f"Baseline coverage: {snapshot.baseline:.2f}%",
            f"Delta vs baseline: {snapshot.delta:+.2f} pts",
            f"Recovered for {config.recovery_days} consecutive days.",
            "",
            "Closing this issue.",
        ]
    )


def _get_hotspots(coverage_data: dict[str, Any], limit: int = 15) -> list[dict[str, Any]]:
    """Extract files with lowest coverage from coverage.json."""
    files = coverage_data.get("files", {})
    if not isinstance(files, dict):
        return []
    hotspots = []

    for filepath, data in files.items():
        if not isinstance(data, dict):
            continue
        summary = data.get("summary", {})
        if not isinstance(summary, dict):
            continue
        percent = _parse_finite_float(summary.get("percent_covered"))
        if percent is None:
            continue
        missing = _to_int(summary.get("missing_lines"))
        hotspots.append(
            {
                "file": filepath,
                "coverage": percent,
                "missing_lines": missing,
            }
        )

    # Sort by coverage ascending (lowest first)
    hotspots.sort(key=lambda x: x["coverage"])
    return hotspots[:limit]


def _format_issue_body(
    current: float,
    baseline: float,
    delta: float,
    hotspots: list[dict[str, Any]],
    run_url: str,
) -> str:
    """Format the issue body with coverage summary and hotspots."""
    status_emoji = "✅" if current >= baseline else "❌"

    body = f"""## Coverage Baseline Breach Report

{status_emoji} **Current Coverage: {current:.2f}%** (baseline: {baseline:.2f}%, delta: {delta:+.2f}%)

### Summary

| Metric | Value |
|--------|-------|
| Current | {current:.2f}% |
| Baseline | {baseline:.2f}% |
| Delta | {delta:+.2f}% |
| Status | {"Pass ✅" if current >= baseline else "Below baseline ❌"} |

### Low Coverage Hotspots

These files have the lowest coverage and are candidates for additional tests:

| File | Coverage | Missing Lines |
|------|----------|---------------|
"""

    for spot in hotspots:
        body += f"| `{spot['file']}` | {spot['coverage']:.1f}% | {spot['missing_lines']} |\n"

    if not hotspots:
        body += "| _(no files with low coverage)_ | - | - |\n"

    source_section = (
        f"\n### Source\n\n[Gate Workflow Run]({run_url})\n"
        if run_url
        else "\n### Source\n\nRun URL unavailable.\n"
    )

    body += f"""

### Actions

- [ ] Review hotspot files and add tests for uncovered code
- [ ] Update baseline once coverage improves
{source_section}

---
_This issue is automatically updated by the coverage guard workflow._
"""
    return body


def _format_recovery_body(
    current: float,
    baseline: float,
    recovery_threshold: float,
    delta: float,
    run_url: str,
) -> str:
    """Format a concise recovery comment for closing a breach issue."""
    source_line = f"\n\n[Gate Workflow Run]({run_url})" if run_url else ""
    if current >= baseline:
        headline = "Coverage has recovered to or above the configured baseline."
    else:
        headline = "Coverage has recovered to the configured warning threshold."
    return f"""{headline}

| Metric | Value |
|--------|-------|
| Current | {current:.2f}% |
| Baseline | {baseline:.2f}% |
| Recovery threshold | {recovery_threshold:.2f}% |
| Delta | {delta:+.2f}% |

Closing the coverage baseline breach issue.{source_line}
"""


def _normalize_labels(labels: list[str] | None) -> list[str]:
    """Return non-empty labels with stable order and duplicates removed."""
    normalized = []
    seen = set()
    for label in labels or []:
        value = label.strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _find_existing_issue(
    repo: str,
    title: str,
    labels: list[str] | None = None,
) -> dict[str, Any] | None:
    """Find an existing issue by title using gh CLI."""
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    search_query = f'"{escaped_title}" in:title'
    normalized_labels = _normalize_labels(labels)
    label_args = []
    for label in normalized_labels:
        label_args.extend(["--label", label])
    for state in ("open", "all"):
        search_result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                state,
                "--search",
                search_query,
                *label_args,
                "--json",
                "number,title,state",
                "--limit",
                "200",
            ],
            capture_output=True,
            text=True,
        )

        if search_result.returncode != 0:
            error_message = search_result.stderr.strip() or "unknown gh error"
            if label_args:
                print(
                    "Failed to search for labeled existing issues; retrying title-only search: "
                    f"{error_message}",
                    file=sys.stderr,
                )
                return _find_existing_issue(repo, title, labels=[])
            print(f"Failed to search for existing issues: {error_message}", file=sys.stderr)
            raise RuntimeError("gh issue list failed")

        try:
            existing_issues = (
                json.loads(search_result.stdout) if search_result.stdout.strip() else []
            )
        except json.JSONDecodeError as exc:
            print("Failed to parse gh issue list output as JSON.", file=sys.stderr)
            if search_result.stderr.strip():
                print(search_result.stderr.strip(), file=sys.stderr)
            raise RuntimeError("gh issue list returned invalid JSON") from exc

        for issue in existing_issues:
            if issue.get("title") == title:
                return issue

    if label_args:
        print(
            "No exact labeled coverage issue match found; retrying title-only search",
            file=sys.stderr,
        )
        return _find_existing_issue(repo, title, labels=[])

    return None


def _find_or_create_issue(repo: str, title: str, body: str, labels: list[str]) -> None:
    """Find existing issue or create a new one using gh CLI."""
    labels = _normalize_labels(labels)
    existing_issue = _find_existing_issue(repo, title, labels=labels)

    if existing_issue:
        issue_number = existing_issue["number"]
        if str(existing_issue.get("state", "")).upper() == "CLOSED":
            subprocess.run(
                ["gh", "issue", "reopen", str(issue_number), "--repo", repo],
                check=True,
            )
        subprocess.run(
            ["gh", "issue", "edit", str(issue_number), "--repo", repo, "--body", body],
            check=True,
        )
        print(f"Updated issue #{issue_number}")
    else:
        # Create new issue
        label_args = []
        for label in labels:
            label_args.extend(["--label", label])

        create_command = [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            title,
            "--body",
            body,
            *label_args,
        ]
        try:
            subprocess.run(create_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            if not label_args:
                raise
            details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            print(
                f"Failed to create coverage issue with labels; retrying without labels: {details}",
                file=sys.stderr,
            )
            subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--repo",
                    repo,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                check=True,
            )
        print(f"Created new issue: {title}")


def _close_existing_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> None:
    """Close the existing baseline breach issue after coverage recovers."""
    existing_issue = _find_existing_issue(repo, title, labels=labels)
    if not existing_issue:
        print("Coverage recovered; no existing breach issue found")
        return

    issue_number = existing_issue["number"]
    if str(existing_issue.get("state", "")).upper() == "CLOSED":
        print(f"Coverage recovered; issue #{issue_number} is already closed")
        return

    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body],
        check=True,
    )
    subprocess.run(
        [
            "gh",
            "issue",
            "close",
            str(issue_number),
            "--repo",
            repo,
            "--reason",
            "completed",
        ],
        check=True,
    )
    print(f"Closed recovered issue #{issue_number}")


def _coverage_value_for_recovery(record: dict[str, Any]) -> float | None:
    """Return the best available coverage value for recovery-window checks."""
    for key in (
        "current",
        "line",
        "lines",
        "worst_job_coverage",
        "avg_coverage",
        "coverage",
        "percent_covered",
    ):
        value = _parse_finite_float(record.get(key))
        if value is not None:
            return value
    return None


def _recovery_window_satisfied(
    trend_data: dict[str, Any],
    baseline: float,
    recovery_window: int,
    history_records: list[dict[str, Any]] | None = None,
) -> bool:
    """Return whether recent coverage samples satisfy the configured recovery window."""
    if recovery_window <= 1:
        return True
    history = history_records if history_records is not None else trend_data.get("history")
    if not isinstance(history, list):
        history = []
    records = [record for record in history if isinstance(record, dict)]
    latest_key = _coverage_record_key(records[-1]) if records else None
    trend_key = _coverage_record_key(trend_data)
    if latest_key != trend_key:
        records.append(trend_data)
    if len(records) < recovery_window:
        return False
    recent = records[-recovery_window:]
    for record in recent:
        current = _coverage_value_for_recovery(record)
        if current is None or current < baseline:
            return False
    return True


def _coverage_record_key(record: dict[str, Any]) -> tuple[str, str | float | None]:
    """Return a stable identity for a coverage sample."""
    for key in ("run_id", "run_url", "workflow_run_id", "head_sha", "sha", "timestamp", "date"):
        value = record.get(key)
        if value not in (None, ""):
            return (key, str(value))
    return ("coverage", _coverage_value_for_recovery(record))


def _accumulate_recovery_history(
    trend_data: dict[str, Any], history_records: list[dict[str, Any]] | None, run_url: str
) -> list[dict[str, Any]]:
    """Retain up to 30 samples, replacing repeated producer-run identities."""
    previous = history_records if history_records is not None else trend_data.get("history", [])
    sample = {key: value for key, value in trend_data.items() if key != "history"}
    if run_url:
        sample.setdefault("run_url", run_url)
    records: list[dict[str, Any]] = []
    for record in [*(previous if isinstance(previous, list) else []), sample]:
        if not isinstance(record, dict):
            continue
        key = _coverage_record_key(record)
        if key[0] != "coverage":
            records = [item for item in records if _coverage_record_key(item) != key]
        elif record is sample and records and _coverage_record_key(records[-1]) == key:
            records.pop()
        records.append(record)
    return records[-30:]


def main(args: list[str] | None = None) -> int:
    """Main entry point for coverage guard."""
    parser = argparse.ArgumentParser(description="Coverage guard - maintain baseline breach issues")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument(
        "--trend-path",
        type=Path,
        default=DEFAULT_TREND_PATH,
        help="Path to coverage-trend.json",
    )
    parser.add_argument(
        "--coverage-path",
        type=Path,
        default=DEFAULT_COVERAGE_PATH,
        help="Path to coverage.json",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="Path to coverage-baseline.json",
    )
    parser.add_argument(
        "--history-path",
        type=Path,
        default=DEFAULT_HISTORY_PATH,
        help="Path to coverage-trend-history.ndjson",
    )
    parser.add_argument("--run-url", default="", help="URL to the workflow run")
    parser.add_argument("--issue-title", default="[coverage] baseline breach", help="Issue title")
    parser.add_argument(
        "--issue-label",
        action="append",
        dest="issue_labels",
        default=None,
        help=(
            "Label to apply to coverage breach issues. Repeat for multiple labels; "
            "pass an empty value to disable default labels."
        ),
    )
    parser.add_argument(
        "--recovery-window",
        type=int,
        default=None,
        help="Number of consecutive recovered samples required before closing",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print issue body without creating")
    parsed = parser.parse_args(args)

    # Load trend data
    trend_data = {}
    if parsed.trend_path and parsed.trend_path.exists():
        trend_data = _load_json(parsed.trend_path)

    # Load coverage data for hotspots
    coverage_data = {}
    if parsed.coverage_path and parsed.coverage_path.exists():
        coverage_data = _load_json(parsed.coverage_path)

    # Load baseline
    baseline_data = {}
    if parsed.baseline_path and parsed.baseline_path.exists():
        baseline_data = _load_json(parsed.baseline_path)

    history_records = None
    if parsed.history_path and parsed.history_path.exists():
        history_records = _load_ndjson(parsed.history_path)

    if not trend_data:
        print("No coverage trend payload found; skipping coverage guard update")
        return 0

    # Extract values
    current = _parse_finite_float(trend_data.get("current"))
    if current is None:
        print("Coverage trend payload has no finite current value; skipping coverage guard update")
        return 0
    baseline = _parse_finite_float(baseline_data.get("line", baseline_data.get("coverage")))
    if baseline is None:
        baseline = _parse_finite_float(trend_data.get("baseline"))
    if baseline is None:
        print(
            "Coverage trend payload has no explicit finite baseline; "
            "skipping coverage guard issue update"
        )
        return 0
    delta = current - baseline
    baseline_config = load_baseline(parsed.baseline_path)
    warn_drop = baseline_config.warn_drop
    recovery_threshold = baseline - warn_drop
    configured_recovery_window = max(
        1,
        _to_int(
            (
                parsed.recovery_window
                if parsed.recovery_window is not None
                else baseline_data.get(
                    "recovery_window",
                    baseline_data.get("recovery_runs", baseline_data.get("recovery_days")),
                )
            ),
            baseline_config.recovery_days,
        ),
    )
    issue_labels = (
        _normalize_labels(parsed.issue_labels)
        if parsed.issue_labels is not None
        else ["coverage", "automated"]
    )

    # Get hotspots
    hotspots = _get_hotspots(coverage_data)

    # Format issue body
    body = _format_issue_body(current, baseline, delta, hotspots, parsed.run_url)

    if parsed.dry_run:
        print("=" * 60)
        print(f"Issue Title: {parsed.issue_title}")
        print("=" * 60)
        print(body)
        return 0

    history_records = _accumulate_recovery_history(trend_data, history_records, parsed.run_url)
    parsed.history_path.parent.mkdir(parents=True, exist_ok=True)
    parsed.history_path.write_text(
        "".join(json.dumps(record) + "\n" for record in history_records), encoding="utf-8"
    )

    # Create or update issue
    if is_coverage_breach(current, baseline, warn_drop):
        try:
            _find_or_create_issue(
                repo=parsed.repo,
                title=parsed.issue_title,
                body=body,
                labels=issue_labels,
            )
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Failed to create or update coverage issue: {exc}", file=sys.stderr)
            return 1
    else:
        if current < baseline:
            print(
                f"Coverage {current:.2f}% has not fallen more than {warn_drop:.2f} points "
                f"below baseline {baseline:.2f}% - evaluating recovery-window closure"
            )
        else:
            print(f"Coverage {current:.2f}% meets baseline {baseline:.2f}% - no open issue needed")
        recovery_check_threshold = baseline if current >= baseline else recovery_threshold
        if not _recovery_window_satisfied(
            history_records[-1],
            recovery_check_threshold,
            configured_recovery_window,
            history_records,
        ):
            recovered_records = sum(
                (value := _coverage_value_for_recovery(record)) is not None
                and value >= recovery_check_threshold
                for record in history_records[-configured_recovery_window:]
            )
            threshold_name = "baseline" if current >= baseline else "warning threshold"
            print(
                f"Coverage recovered, {recovered_records} of {configured_recovery_window} "
                f"records at or above the {threshold_name}; "
                "configured recovery window is not satisfied; "
                "leaving any breach issue open"
            )
            return 0
        try:
            _close_existing_issue(
                parsed.repo,
                parsed.issue_title,
                _format_recovery_body(
                    current,
                    baseline,
                    recovery_threshold,
                    delta,
                    parsed.run_url,
                ),
                labels=issue_labels,
            )
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Failed to close recovered coverage issue: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

```


## Current reviewer acceptance verification evidence
The files below are exact copied receipt/output bytes. Historical absolute paths inside command receipts are provenance, not external capture dependencies; complete receipt/output files are inlined here and retained under local relative evidence paths. No expected PR Verify verdict or independent gold is supplied. Kernel sandbox denied network connections and confined writes to the private verification fixture; the executed tests already patch issue-closing effects.

### evidence/EVIDENCE_INDEX.json (SHA256 1f4965caf9109a6f199f62a4b74a15302655d498d5c13f41afc78877478ba0c1)
```
{
  "schema": "current-review-evidence-index/v1",
  "meaning": "New current reviewer verification; original source packet, original Task6 gold and historical author claims remain unchanged. Independent re-review is required before using an enriched pre-observation packet.",
  "source_packet": "/tmp/real-verify-representative-packets-20261027/linked-issue-cases/workflows-4265",
  "second_source_packet": "/tmp/real-verify-representative-packets-20261027/replacement-linked-issue-case/workflows-3850",
  "original_source_head": "40622701645e1c9c13ff28861ba606a3f78d2e4a",
  "outcomes": {
    "original_two_named_tests": "9 passed; exit0",
    "removed_current_append": "5 assertion failures; exit1",
    "restored_two_named_tests": "9 passed; exit0"
  },
  "restoration_matches_original": true,
  "setup_attempt_receipts": [
    "/tmp/real-verify-4265-current-review-verification-20261027/receipt.json",
    "/tmp/real-verify-4265-current-review-verification-20261027-kernel-retry/receipt.json",
    "/tmp/real-verify-4265-current-review-verification-20261027-confined/receipt.json"
  ],
  "files": {
    "sandbox-and-runtime-probe.stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "original.pytest.log": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "restored-two-named-tests.stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "original.junit.xml": "5183216f09c82d17b07277cdc8cab1e3a87d57acd602618704d931d7ecec254b",
    "sandbox-and-runtime-probe.stdout": "6f5a0def7d78406abf2c3bd92dc46cbbf32af268915767b81577e40288e683c4",
    "restored.junit.xml": "23f9bd8422fddc12a2f179b61b0f0bbf5147408813b1b0f97445a2601a6e9d06",
    "restored-two-named-tests.stdout": "38025b23df21b23d371cb04835992ad56739231045e0683deb6a80c6d699b19d",
    "sandbox.sb": "26a916d002f05105670fb4a67a2e348c65c2368aa03bc9de1dfd9a7d6bf39984",
    "broken.pytest.log": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "original-two-named-tests.stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "mutation.patch": "9b2e105bf5cc72819537980bea8c86364896bff444d9a43fb43eded649e5d886",
    "removed-current-append.stdout": "1527f3e7fa617449ba3d04e924d1d273b1cc4b021d85e387a037d8766005fdd7",
    "removed-current-append.stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "restored.pytest.log": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "original-two-named-tests.stdout": "38025b23df21b23d371cb04835992ad56739231045e0683deb6a80c6d699b19d",
    "broken.junit.xml": "afe073343962cdb4538ede7c53b0913ea2bf3743c8449cbd1a8f39ea178015b6",
    "receipt.json": "87e45c38296887a04681519b4d42bf207835bbed0187a2a62cdb1bb7894d3a07"
  }
}

```

### evidence/broken.junit.xml (SHA256 afe073343962cdb4538ede7c53b0913ea2bf3743c8449cbd1a8f39ea178015b6)
```
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="5" skipped="0" tests="5" time="0.198" timestamp="2026-10-27T13:42:27.387747-05:00" hostname="server.trs.private"><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[two-runs]" time="0.002"><failure message="assert 0 == 1&#10; +  where 0 = len([])">tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re0')
monkeypatch = &lt;_pytest.monkeypatch.MonkeyPatch object at 0x1045176b0&gt;
restored_run_ids = ('1', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -&gt; None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
&gt;       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError</failure></testcase><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-oldest]" time="0.002"><failure message="assert 0 == 1&#10; +  where 0 = len([])">tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re1')
monkeypatch = &lt;_pytest.monkeypatch.MonkeyPatch object at 0x104515970&gt;
restored_run_ids = ('3', '1', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -&gt; None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
&gt;       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError</failure></testcase><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-middle]" time="0.002"><failure message="assert 0 == 1&#10; +  where 0 = len([])">tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re2')
monkeypatch = &lt;_pytest.monkeypatch.MonkeyPatch object at 0x1045150a0&gt;
restored_run_ids = ('1', '3', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -&gt; None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
&gt;       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError</failure></testcase><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-latest]" time="0.002"><failure message="assert 0 == 1&#10; +  where 0 = len([])">tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re3')
monkeypatch = &lt;_pytest.monkeypatch.MonkeyPatch object at 0x104504b00&gt;
restored_run_ids = ('1', '2', '3')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -&gt; None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
&gt;       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError</failure></testcase><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[duplicate-restored-run]" time="0.002"><failure message="assert 0 == 1&#10; +  where 0 = len([])">tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re4')
monkeypatch = &lt;_pytest.monkeypatch.MonkeyPatch object at 0x104505430&gt;
restored_run_ids = ('1', '1', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -&gt; None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
&gt;       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError</failure></testcase></testsuite></testsuites>
```

### evidence/broken.pytest.log (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/current-review-runner.py (SHA256 08c42b32ed5188d6071d40a749a26ec6fe310067f3dab32214b96a80ed4d1ef1)
```
from pathlib import Path
import subprocess,json,hashlib,datetime,sys,difflib
ROOT=Path('/tmp/real-verify-4265-current-review-verification-20261027-final')
ROOT.mkdir(exist_ok=False)
SNAP=ROOT/'snapshot';SNAP.mkdir()
TMP=ROOT/'fixtures';TMP.mkdir()
HOME=ROOT/'empty-home';HOME.mkdir()
SRC=Path('/Users/teacher/Library/CloudStorage/Dropbox/Learning/Code/Workflows')
HEAD='40622701645e1c9c13ff28861ba606a3f78d2e4a'
PYTHON='/opt/anaconda3/bin/python3'
sha=lambda b:hashlib.sha256(b).hexdigest()
files=['tools/coverage_guard.py','tests/test_coverage_guard.py']
blobs={}
for name in files:
    data=subprocess.check_output(['git','-C',str(SRC),'show',HEAD+':'+name])
    path=SNAP/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    blobs[name]={'sha256':sha(data),'git_blob':subprocess.check_output(['git','-C',str(SRC),'rev-parse',HEAD+':'+name]).decode().strip()}
(ROOT/'sandbox.sb').write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath "'+str(ROOT.resolve())+'"))\n(deny file-read* (subpath "/Users/teacher"))\n')
env={'PATH':'/usr/bin:/bin','HOME':str(HOME),'TMPDIR':str(TMP),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','LANG':'en_US.UTF-8'}
receipt={'schema':'current-review-original-acceptance-procedure/v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repository':'stranske/Workflows','pr':4265,'issue':4254,'original_pr_head':HEAD,'meaning':'Current reviewer execution of existing exact-head acceptance tests and deliberate break/revert; not evidence of what the PR author historically ran.','source_files':blobs,'environment':env,'kernel_sandbox_profile':(ROOT/'sandbox.sb').read_text(),'runs':[],'provider_calls':0}
def run(name,argv):
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result=subprocess.run(argv,cwd=SNAP,env=env,capture_output=True,timeout=90)
    (ROOT/(name+'.stdout')).write_bytes(result.stdout)
    (ROOT/(name+'.stderr')).write_bytes(result.stderr)
    row={'name':name,'argv':argv,'cwd':str(SNAP),'started_utc':started,'exit_code':result.returncode,'stdout_sha256':sha(result.stdout),'stderr_sha256':sha(result.stderr)}
    receipt['runs'].append(row)
    (ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    return result
prefix=['/usr/bin/sandbox-exec','-f',str(ROOT/'sandbox.sb'),PYTHON,'-I','-B']
probe=run('sandbox-and-runtime-probe',prefix+['-c','import sys,platform,socket,json; print(json.dumps({"executable":sys.executable,"version":sys.version,"platform":platform.platform()}));\ntry: socket.socket().connect(("127.0.0.1", 9))\nexcept PermissionError as e: print("KERNEL_NETWORK_DENIED",type(e).__name__)\nelse: raise SystemExit("network sandbox unexpectedly permitted loopback connection")'])
if probe.returncode:
    receipt['blocked']='Kernel network-denial/runtime probe failed; no pytest or mutation execution.'
    (ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    raise SystemExit(0)
names=['test_recovery_window_counts_records_accumulated_across_runs','test_recovery_message_names_records_held_and_needed']
def pytest_cmd(label,selected):
    args=['--log-file',str(ROOT/(label+'.pytest.log')),'--junitxml',str(ROOT/(label+'.junit.xml')),'-q','-o','addopts=','-c','/dev/null','--rootdir',str(SNAP),'--confcutdir',str(SNAP),'--basetemp',str(TMP/label),'-p','no:cacheprovider']+[str(SNAP/'tests/test_coverage_guard.py')+'::'+n for n in selected]
    code='import sys;sys.path.insert(0,'+repr(str(SNAP))+');import pytest;raise SystemExit(pytest.main('+repr(args)+'))'
    return prefix+['-c',code]
baseline=run('original-two-named-tests',pytest_cmd('original',names))
if baseline.returncode:
    receipt['blocked']='Original selected tests did not pass; deliberate break not attempted.'
else:
    module=SNAP/'tools/coverage_guard.py';original=module.read_bytes()
    old=b'for record in [*(previous if isinstance(previous, list) else []), sample]:'
    new=b'for record in [*(previous if isinstance(previous, list) else [])]:'
    if original.count(old)!=1:raise RuntimeError('Mutation anchor not unique')
    broken=original.replace(old,new)
    (ROOT/'mutation.patch').write_text(''.join(difflib.unified_diff(original.decode().splitlines(True),broken.decode().splitlines(True),fromfile='original/tools/coverage_guard.py',tofile='broken/tools/coverage_guard.py')))
    receipt['mutation']={'operation':'Remove only the current sample from existing accumulation iteration; retain all prior-history processing and test source unchanged.','before_sha256':sha(original),'broken_sha256':sha(broken),'patch_sha256':sha((ROOT/'mutation.patch').read_bytes())}
    try:
        module.write_bytes(broken)
        run('removed-current-append',pytest_cmd('broken',[names[0]]))
    finally:
        module.write_bytes(original)
        receipt['restored_sha256']=sha(module.read_bytes())
    run('restored-two-named-tests',pytest_cmd('restored',names))
receipt['final_source_files']={name:sha((SNAP/name).read_bytes()) for name in files}
receipt['interpreter_file_sha256']=sha(Path(PYTHON).resolve().read_bytes())
(ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(str(ROOT/'receipt.json'))

```

### evidence/mutation.patch (SHA256 9b2e105bf5cc72819537980bea8c86364896bff444d9a43fb43eded649e5d886)
```
--- original/tools/coverage_guard.py
+++ broken/tools/coverage_guard.py
@@ -618,7 +618,7 @@
     if run_url:
         sample.setdefault("run_url", run_url)
     records: list[dict[str, Any]] = []
-    for record in [*(previous if isinstance(previous, list) else []), sample]:
+    for record in [*(previous if isinstance(previous, list) else [])]:
         if not isinstance(record, dict):
             continue
         key = _coverage_record_key(record)

```

### evidence/original-two-named-tests.stderr (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/original-two-named-tests.stdout (SHA256 38025b23df21b23d371cb04835992ad56739231045e0683deb6a80c6d699b19d)
```
.........                                                                [100%]
9 passed in 0.12s

```

### evidence/original.junit.xml (SHA256 5183216f09c82d17b07277cdc8cab1e3a87d57acd602618704d931d7ecec254b)
```
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="9" time="0.124" timestamp="2026-10-27T13:42:27.121335-05:00" hostname="server.trs.private"><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[two-runs]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-oldest]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-middle]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-latest]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[duplicate-restored-run]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[two-recovered]" time="0.001" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[one-below-baseline]" time="0.002" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[latest-window-only]" time="0.001" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[current-alone]" time="0.001" /></testsuite></testsuites>
```

### evidence/original.pytest.log (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/receipt.json (SHA256 87e45c38296887a04681519b4d42bf207835bbed0187a2a62cdb1bb7894d3a07)
```
{
  "schema": "current-review-original-acceptance-procedure/v1",
  "created_utc": "2026-10-27T18:42:26.937157+00:00",
  "repository": "stranske/Workflows",
  "pr": 4265,
  "issue": 4254,
  "original_pr_head": "40622701645e1c9c13ff28861ba606a3f78d2e4a",
  "meaning": "Current reviewer execution of existing exact-head acceptance tests and deliberate break/revert; not evidence of what the PR author historically ran.",
  "source_files": {
    "tools/coverage_guard.py": {
      "sha256": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
      "git_blob": "6ce725e48749884d2ef81094a69e3b466b594a32"
    },
    "tests/test_coverage_guard.py": {
      "sha256": "778b90641854081857bfdf9123a6cc28ddf5f5517f5a8da418e5d8f5f3549648",
      "git_blob": "ff6bfeb12e7bb19bd120d14b2d44b6079b68ffd6"
    }
  },
  "environment": {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp/real-verify-4265-current-review-verification-20261027-final/empty-home",
    "TMPDIR": "/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "LANG": "en_US.UTF-8"
  },
  "kernel_sandbox_profile": "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath \"/private/tmp/real-verify-4265-current-review-verification-20261027-final\"))\n(deny file-read* (subpath \"/Users/teacher\"))\n",
  "runs": [
    {
      "name": "sandbox-and-runtime-probe",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-final/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys,platform,socket,json; print(json.dumps({\"executable\":sys.executable,\"version\":sys.version,\"platform\":platform.platform()}));\ntry: socket.socket().connect((\"127.0.0.1\", 9))\nexcept PermissionError as e: print(\"KERNEL_NETWORK_DENIED\",type(e).__name__)\nelse: raise SystemExit(\"network sandbox unexpectedly permitted loopback connection\")"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot",
      "started_utc": "2026-10-27T18:42:26.937395+00:00",
      "exit_code": 0,
      "stdout_sha256": "6f5a0def7d78406abf2c3bd92dc46cbbf32af268915767b81577e40288e683c4",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "name": "original-two-named-tests",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-final/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys;sys.path.insert(0,'/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot');import pytest;raise SystemExit(pytest.main(['--log-file', '/tmp/real-verify-4265-current-review-verification-20261027-final/original.pytest.log', '--junitxml', '/tmp/real-verify-4265-current-review-verification-20261027-final/original.junit.xml', '-q', '-o', 'addopts=', '-c', '/dev/null', '--rootdir', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot', '--confcutdir', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot', '--basetemp', '/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/original', '-p', 'no:cacheprovider', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_message_names_records_held_and_needed']))"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot",
      "started_utc": "2026-10-27T18:42:26.985429+00:00",
      "exit_code": 0,
      "stdout_sha256": "38025b23df21b23d371cb04835992ad56739231045e0683deb6a80c6d699b19d",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "name": "removed-current-append",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-final/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys;sys.path.insert(0,'/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot');import pytest;raise SystemExit(pytest.main(['--log-file', '/tmp/real-verify-4265-current-review-verification-20261027-final/broken.pytest.log', '--junitxml', '/tmp/real-verify-4265-current-review-verification-20261027-final/broken.junit.xml', '-q', '-o', 'addopts=', '-c', '/dev/null', '--rootdir', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot', '--confcutdir', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot', '--basetemp', '/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken', '-p', 'no:cacheprovider', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs']))"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot",
      "started_utc": "2026-10-27T18:42:27.266911+00:00",
      "exit_code": 1,
      "stdout_sha256": "1527f3e7fa617449ba3d04e924d1d273b1cc4b021d85e387a037d8766005fdd7",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "name": "restored-two-named-tests",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-final/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys;sys.path.insert(0,'/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot');import pytest;raise SystemExit(pytest.main(['--log-file', '/tmp/real-verify-4265-current-review-verification-20261027-final/restored.pytest.log', '--junitxml', '/tmp/real-verify-4265-current-review-verification-20261027-final/restored.junit.xml', '-q', '-o', 'addopts=', '-c', '/dev/null', '--rootdir', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot', '--confcutdir', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot', '--basetemp', '/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/restored', '-p', 'no:cacheprovider', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs', '/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_message_names_records_held_and_needed']))"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot",
      "started_utc": "2026-10-27T18:42:27.609898+00:00",
      "exit_code": 0,
      "stdout_sha256": "38025b23df21b23d371cb04835992ad56739231045e0683deb6a80c6d699b19d",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ],
  "provider_calls": 0,
  "mutation": {
    "operation": "Remove only the current sample from existing accumulation iteration; retain all prior-history processing and test source unchanged.",
    "before_sha256": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
    "broken_sha256": "28eda2170b1e03dcb11bcae8f6511b2cc09a7c0ea1c765427f7ddfda8c6a6a02",
    "patch_sha256": "9b2e105bf5cc72819537980bea8c86364896bff444d9a43fb43eded649e5d886"
  },
  "restored_sha256": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
  "final_source_files": {
    "tools/coverage_guard.py": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
    "tests/test_coverage_guard.py": "778b90641854081857bfdf9123a6cc28ddf5f5517f5a8da418e5d8f5f3549648"
  },
  "interpreter_file_sha256": "d01b09973b5bd3ff617e7849ce9c0bdb8991256f495ce190720ccc976cdaaee7"
}

```

### evidence/removed-current-append.stderr (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/removed-current-append.stdout (SHA256 1527f3e7fa617449ba3d04e924d1d273b1cc4b021d85e387a037d8766005fdd7)
```
FFFFF                                                                    [100%]
=================================== FAILURES ===================================
____ test_recovery_window_counts_records_accumulated_across_runs[two-runs] _____

tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1045176b0>
restored_run_ids = ('1', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -> None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
>       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError
----------------------------- Captured stdout call -----------------------------
Coverage 90.00% meets baseline 85.00% - no open issue needed
Coverage recovered, 2 of 3 records at or above the baseline; configured recovery window is not satisfied; leaving any breach issue open
__ test_recovery_window_counts_records_accumulated_across_runs[retry-oldest] ___

tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re1')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x104515970>
restored_run_ids = ('3', '1', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -> None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
>       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError
----------------------------- Captured stdout call -----------------------------
Coverage 90.00% meets baseline 85.00% - no open issue needed
Coverage recovered, 2 of 3 records at or above the baseline; configured recovery window is not satisfied; leaving any breach issue open
__ test_recovery_window_counts_records_accumulated_across_runs[retry-middle] ___

tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re2')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1045150a0>
restored_run_ids = ('1', '3', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -> None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
>       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError
----------------------------- Captured stdout call -----------------------------
Coverage 90.00% meets baseline 85.00% - no open issue needed
Coverage recovered, 2 of 3 records at or above the baseline; configured recovery window is not satisfied; leaving any breach issue open
__ test_recovery_window_counts_records_accumulated_across_runs[retry-latest] ___

tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re3')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x104504b00>
restored_run_ids = ('1', '2', '3')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -> None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
>       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError
----------------------------- Captured stdout call -----------------------------
Coverage 90.00% meets baseline 85.00% - no open issue needed
Coverage recovered, 2 of 3 records at or above the baseline; configured recovery window is not satisfied; leaving any breach issue open
_ test_recovery_window_counts_records_accumulated_across_runs[duplicate-restored-run] _

tmp_path = PosixPath('/private/tmp/real-verify-4265-current-review-verification-20261027-final/fixtures/broken/test_recovery_window_counts_re4')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x104505430>
restored_run_ids = ('1', '1', '2')

    @pytest.mark.parametrize(
        "restored_run_ids",
        [("1", "2"), ("3", "1", "2"), ("1", "3", "2"), ("1", "2", "3"), ("1", "1", "2")],
        ids=["two-runs", "retry-oldest", "retry-middle", "retry-latest", "duplicate-restored-run"],
    )
    def test_recovery_window_counts_records_accumulated_across_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restored_run_ids: tuple[str, ...]
    ) -> None:
        """Restored runs accumulate while retries replace stale samples without inflating the window."""
        trend_path = tmp_path / "trend.json"
        baseline_path = tmp_path / "baseline.json"
        history_path = tmp_path / "history.ndjson"
        _write_json(trend_path, {"current": 90.0, "run_id": "3"})
        _write_json(baseline_path, {"line": 85.0, "recovery_days": 3})
        history_path.write_text(
            "\n".join(
                json.dumps({"current": 80.0 if run_id == "3" else 90.0, "run_id": run_id})
                for run_id in restored_run_ids
            ),
            encoding="utf-8",
        )
        closed = []
        monkeypatch.setattr(coverage_guard, "_close_existing_issue", lambda *a, **kw: closed.append(a))
        args = [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
        assert coverage_guard.main(args) == 0
>       assert len(closed) == 1
E       assert 0 == 1
E        +  where 0 = len([])

/tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py:821: AssertionError
----------------------------- Captured stdout call -----------------------------
Coverage 90.00% meets baseline 85.00% - no open issue needed
Coverage recovered, 2 of 3 records at or above the baseline; configured recovery window is not satisfied; leaving any breach issue open
=========================== short test summary info ============================
FAILED ../../../../tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs[two-runs]
FAILED ../../../../tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs[retry-oldest]
FAILED ../../../../tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs[retry-middle]
FAILED ../../../../tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs[retry-latest]
FAILED ../../../../tmp/real-verify-4265-current-review-verification-20261027-final/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs[duplicate-restored-run]
5 failed in 0.20s

```

### evidence/restored-two-named-tests.stderr (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/restored-two-named-tests.stdout (SHA256 38025b23df21b23d371cb04835992ad56739231045e0683deb6a80c6d699b19d)
```
.........                                                                [100%]
9 passed in 0.12s

```

### evidence/restored.junit.xml (SHA256 23f9bd8422fddc12a2f179b61b0f0bbf5147408813b1b0f97445a2601a6e9d06)
```
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="9" time="0.124" timestamp="2026-10-27T13:42:27.730442-05:00" hostname="server.trs.private"><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[two-runs]" time="0.004" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-oldest]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-middle]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[retry-latest]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_window_counts_records_accumulated_across_runs[duplicate-restored-run]" time="0.003" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[two-recovered]" time="0.001" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[one-below-baseline]" time="0.001" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[latest-window-only]" time="0.001" /><testcase classname="tests.test_coverage_guard" name="test_recovery_message_names_records_held_and_needed[current-alone]" time="0.001" /></testsuite></testsuites>
```

### evidence/restored.pytest.log (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/sandbox-and-runtime-probe.stderr (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
```

```

### evidence/sandbox-and-runtime-probe.stdout (SHA256 6f5a0def7d78406abf2c3bd92dc46cbbf32af268915767b81577e40288e683c4)
```
{"executable": "/opt/anaconda3/bin/python3", "version": "3.12.2 | packaged by conda-forge | (main, Feb 16 2024, 20:54:21) [Clang 16.0.6 ]", "platform": "macOS-26.6.2-arm64-64bit"}
KERNEL_NETWORK_DENIED PermissionError

```

### evidence/sandbox.sb (SHA256 26a916d002f05105670fb4a67a2e348c65c2368aa03bc9de1dfd9a7d6bf39984)
```
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "/private/tmp/real-verify-4265-current-review-verification-20261027-final"))
(deny file-read* (subpath "/Users/teacher"))

```

### evidence/setup-attempt-1-receipt.json (SHA256 3ce5c1bc1780d2c9404e6d27965580838ac9c42f6ff8e7c69ad8821ae41f368e)
```
{
  "schema": "current-review-original-acceptance-procedure/v1",
  "created_utc": "2026-10-27T18:41:34.841910+00:00",
  "repository": "stranske/Workflows",
  "pr": 4265,
  "issue": 4254,
  "original_pr_head": "40622701645e1c9c13ff28861ba606a3f78d2e4a",
  "meaning": "Current reviewer execution of existing exact-head acceptance tests and deliberate break/revert; not evidence of what the PR author historically ran.",
  "source_files": {
    "tools/coverage_guard.py": {
      "sha256": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
      "git_blob": "6ce725e48749884d2ef81094a69e3b466b594a32"
    },
    "tests/test_coverage_guard.py": {
      "sha256": "778b90641854081857bfdf9123a6cc28ddf5f5517f5a8da418e5d8f5f3549648",
      "git_blob": "ff6bfeb12e7bb19bd120d14b2d44b6079b68ffd6"
    }
  },
  "environment": {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp/real-verify-4265-current-review-verification-20261027/empty-home",
    "TMPDIR": "/tmp/real-verify-4265-current-review-verification-20261027/fixtures",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "LANG": "en_US.UTF-8"
  },
  "kernel_sandbox_profile": "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath \"/private/tmp/real-verify-4265-current-review-verification-20261027\"))\n(deny file-read* (subpath \"/Users/teacher\"))\n",
  "runs": [
    {
      "name": "sandbox-and-runtime-probe",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys,platform,socket,json; print(json.dumps({\"executable\":sys.executable,\"version\":sys.version,\"platform\":platform.platform()}));\ntry: socket.socket()\nexcept PermissionError as e: print(\"KERNEL_NETWORK_DENIED\",type(e).__name__)\nelse: raise SystemExit(\"network sandbox unexpectedly permitted socket\")"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027/snapshot",
      "started_utc": "2026-10-27T18:41:34.842059+00:00",
      "exit_code": 71,
      "stdout_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "stderr_sha256": "d34a4e4359a4dc36526cf5b363da32f7b7594a3a09eea17cbdfd6425b052d93e"
    }
  ],
  "provider_calls": 0,
  "blocked": "Kernel network-denial/runtime probe failed; no pytest or mutation execution."
}

```

### evidence/setup-attempt-2-receipt.json (SHA256 49794234f70f15289824bf3cb7816afdb92b4bbc4db43a4c001e984fde220bb7)
```
{
  "schema": "current-review-original-acceptance-procedure/v1",
  "created_utc": "2026-10-27T18:41:56.881631+00:00",
  "repository": "stranske/Workflows",
  "pr": 4265,
  "issue": 4254,
  "original_pr_head": "40622701645e1c9c13ff28861ba606a3f78d2e4a",
  "meaning": "Current reviewer execution of existing exact-head acceptance tests and deliberate break/revert; not evidence of what the PR author historically ran.",
  "source_files": {
    "tools/coverage_guard.py": {
      "sha256": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
      "git_blob": "6ce725e48749884d2ef81094a69e3b466b594a32"
    },
    "tests/test_coverage_guard.py": {
      "sha256": "778b90641854081857bfdf9123a6cc28ddf5f5517f5a8da418e5d8f5f3549648",
      "git_blob": "ff6bfeb12e7bb19bd120d14b2d44b6079b68ffd6"
    }
  },
  "environment": {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp/real-verify-4265-current-review-verification-20261027-kernel-retry/empty-home",
    "TMPDIR": "/tmp/real-verify-4265-current-review-verification-20261027-kernel-retry/fixtures",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "LANG": "en_US.UTF-8"
  },
  "kernel_sandbox_profile": "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath \"/private/tmp/real-verify-4265-current-review-verification-20261027-kernel-retry\"))\n(deny file-read* (subpath \"/Users/teacher\"))\n",
  "runs": [
    {
      "name": "sandbox-and-runtime-probe",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-kernel-retry/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys,platform,socket,json; print(json.dumps({\"executable\":sys.executable,\"version\":sys.version,\"platform\":platform.platform()}));\ntry: socket.socket()\nexcept PermissionError as e: print(\"KERNEL_NETWORK_DENIED\",type(e).__name__)\nelse: raise SystemExit(\"network sandbox unexpectedly permitted socket\")"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-kernel-retry/snapshot",
      "started_utc": "2026-10-27T18:41:56.881881+00:00",
      "exit_code": 1,
      "stdout_sha256": "467530857dbc019858a9f537daa856594ccbd37f757963d5604f2234cc04e0e1",
      "stderr_sha256": "cd0642c381e518d5dd715a375317b8e4703b3f2c694e44e0d57138a02e3b5e0b"
    }
  ],
  "provider_calls": 0,
  "blocked": "Kernel network-denial/runtime probe failed; no pytest or mutation execution."
}

```

### evidence/setup-attempt-3-receipt.json (SHA256 7472dbee6b3c7e6c6be6745a0f7f52e2dbbcce11530cfb69bcd3f51413c9fdbf)
```
{
  "schema": "current-review-original-acceptance-procedure/v1",
  "created_utc": "2026-10-27T18:42:14.925499+00:00",
  "repository": "stranske/Workflows",
  "pr": 4265,
  "issue": 4254,
  "original_pr_head": "40622701645e1c9c13ff28861ba606a3f78d2e4a",
  "meaning": "Current reviewer execution of existing exact-head acceptance tests and deliberate break/revert; not evidence of what the PR author historically ran.",
  "source_files": {
    "tools/coverage_guard.py": {
      "sha256": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
      "git_blob": "6ce725e48749884d2ef81094a69e3b466b594a32"
    },
    "tests/test_coverage_guard.py": {
      "sha256": "778b90641854081857bfdf9123a6cc28ddf5f5517f5a8da418e5d8f5f3549648",
      "git_blob": "ff6bfeb12e7bb19bd120d14b2d44b6079b68ffd6"
    }
  },
  "environment": {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp/real-verify-4265-current-review-verification-20261027-confined/empty-home",
    "TMPDIR": "/tmp/real-verify-4265-current-review-verification-20261027-confined/fixtures",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "LANG": "en_US.UTF-8"
  },
  "kernel_sandbox_profile": "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath \"/private/tmp/real-verify-4265-current-review-verification-20261027-confined\"))\n(deny file-read* (subpath \"/Users/teacher\"))\n",
  "runs": [
    {
      "name": "sandbox-and-runtime-probe",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-confined/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys,platform,socket,json; print(json.dumps({\"executable\":sys.executable,\"version\":sys.version,\"platform\":platform.platform()}));\ntry: socket.socket().connect((\"127.0.0.1\", 9))\nexcept PermissionError as e: print(\"KERNEL_NETWORK_DENIED\",type(e).__name__)\nelse: raise SystemExit(\"network sandbox unexpectedly permitted loopback connection\")"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot",
      "started_utc": "2026-10-27T18:42:14.925763+00:00",
      "exit_code": 0,
      "stdout_sha256": "6f5a0def7d78406abf2c3bd92dc46cbbf32af268915767b81577e40288e683c4",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "name": "original-two-named-tests",
      "argv": [
        "/usr/bin/sandbox-exec",
        "-f",
        "/tmp/real-verify-4265-current-review-verification-20261027-confined/sandbox.sb",
        "/opt/anaconda3/bin/python3",
        "-I",
        "-B",
        "-c",
        "import sys;sys.path.insert(0,'/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot');import pytest;raise SystemExit(pytest.main(['-q', '-o', 'addopts=', '-c', '/dev/null', '--rootdir', '/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot', '--confcutdir', '/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot', '--basetemp', '/tmp/real-verify-4265-current-review-verification-20261027-confined/fixtures/original', '-p', 'no:cacheprovider', '/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot/tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs', '/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot/tests/test_coverage_guard.py::test_recovery_message_names_records_held_and_needed']))"
      ],
      "cwd": "/tmp/real-verify-4265-current-review-verification-20261027-confined/snapshot",
      "started_utc": "2026-10-27T18:42:14.976500+00:00",
      "exit_code": 3,
      "stdout_sha256": "0f2a05e965976a66a49797d28056474abcde3a29222e940d4b214bed82b320da",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ],
  "provider_calls": 0,
  "blocked": "Original selected tests did not pass; deliberate break not attempted.",
  "final_source_files": {
    "tools/coverage_guard.py": "fd4b88605d88267a90ada88803754b4b171ba1a916ab4c5379009a74c304ba1d",
    "tests/test_coverage_guard.py": "778b90641854081857bfdf9123a6cc28ddf5f5517f5a8da418e5d8f5f3549648"
  },
  "interpreter_file_sha256": "d01b09973b5bd3ff617e7849ce9c0bdb8991256f495ce190720ccc976cdaaee7"
}

```
