'use strict';

async function run({ github, context, core }) {
  const defaultOwner = context.repo.owner;
  const fs = require('fs');
  const path = require('path');
  // Sibling-relative paths: this module lives under .github/scripts/, so
  // require('./.github/scripts/...') would resolve to a nested non-existent path.
  const retryHelperPath = path.join(__dirname, 'github-api-with-retry.js');
  const {
    buildMarkdownSummary,
    buildMergeReport,
    candidateEvidenceAllowsMutation,
    classifyGeneratedPr,
    classifySyncPrChecks,
    collectDeletableSyncBranches,
    evaluatePostPushReviewWindow,
    generatedDeliveryLane,
    isBlockingSyncSystemFailure,
    normalizeSyncHash,
    parseBooleanInput,
    requiresStrictGateBranchUpdate,
    requiredContextsFromRulesets,
    isTrustedGeneratedDeliveryPr,
    selectLatestMergedCandidatePr,
    selectMergeEligibleSyncPr,
    selectSyncPrGatingChecks,
    syncBranchForHash,
    validateCanaryEvidence,
  } = require('./sync_pr_merge_contract.js');
  const {
    assertRuntimeAcMergeAllowed,
  } = require('./runtime_ac_merge_guard.js');
  // Support repository_dispatch (no inputs) with sensible defaults
  const inputRepos =
    process.env.REPOS_INPUT ||
    (context.payload.client_payload && context.payload.client_payload.repos) ||
    'all';
  const autoMerge = parseBooleanInput(
    process.env.AUTO_MERGE_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.auto_merge),
    true,
  );
  const evidenceOnly = parseBooleanInput(process.env.EVIDENCE_ONLY_INPUT, false);
  const candidateEvidenceAuthorized = parseBooleanInput(
    process.env.CANDIDATE_EVIDENCE_AUTHORIZED,
    process.env.CANDIDATE_EVIDENCE_RESULT === 'success'
      && process.env.CANDIDATE_ARTIFACT_RESULT === 'success',
  );
  const dryRun = evidenceOnly || parseBooleanInput(
    process.env.DRY_RUN_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.dry_run),
    false,
  );
  const cleanupBranches = parseBooleanInput(
    process.env.CLEANUP_BRANCHES_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.cleanup_branches),
    true,
  );
  const retryHelpers = fs.existsSync(retryHelperPath)
    ? require(retryHelperPath)
    : {
        // Call sites pass (client) => client.rest...; match that contract.
        withRetry: (fn) => fn(github),
        paginateWithRetry: (githubInstance, method, params) =>
          githubInstance.paginate(method, params),
      };
  const { createTokenAwareRetry } = retryHelpers;
  const { withRetry } = createTokenAwareRetry
    ? await createTokenAwareRetry({
        github,
        core,
        env: process.env,
        task: 'maint-71-merge-sync-prs',
        capabilities: [
          'pull-requests:read',
          'pull-requests:write',
          'checks:read',
          'contents:write',
        ],
      })
    : { github, withRetry: (fn) => fn(github) };
  async function getRequiredContexts({ owner, repo, branch }) {
    try {
      const { data: protection } = await withRetry((client) =>
        client.rest.repos.getBranchProtection({
          owner,
          repo,
          branch,
        }),
      );
      const requiredStatusChecks = protection?.required_status_checks || {};
      const requiredContexts = new Set();
      for (const contextName of requiredStatusChecks.contexts || []) {
        const normalized = String(contextName || '').trim();
        if (normalized) {
          requiredContexts.add(normalized);
        }
      }
      for (const check of requiredStatusChecks.checks || []) {
        const normalized = String(check?.context || '').trim();
        if (normalized) {
          requiredContexts.add(normalized);
        }
      }
      if (requiredContexts.size > 0) {
        return { contexts: requiredContexts, source: 'branch-protection' };
      }
      console.log(
        `Legacy branch protection for ${owner}/${repo}@${branch} has no ` +
          'required checks; checking active repository and organization rulesets',
      );
    } catch (error) {
      const status = error?.status || error?.response?.status;
      if (status === 403 || status === 404) {
        console.log(
          `Branch protection unavailable for ${owner}/${repo}@${branch} ` +
            `(${status}); checking active repository and organization rulesets`,
        );
      } else {
        throw error;
      }
    }

    const { data: rulesetList } = await withRetry((client) =>
      client.rest.repos.getRepoRulesets({
        owner,
        repo,
        includes_parents: true,
      }),
    );
    const rulesets = [];
    for (const ruleset of rulesetList || []) {
      if (Array.isArray(ruleset?.rules) && ruleset?.conditions) {
        rulesets.push(ruleset);
        continue;
      }
      const { data: rulesetDetail } = await withRetry((client) =>
        client.rest.repos.getRepoRuleset({
          owner,
          repo,
          ruleset_id: ruleset.id,
        }),
      );
      rulesets.push(rulesetDetail);
    }
    const requiredContexts = requiredContextsFromRulesets(rulesets, branch);
    console.log(
      requiredContexts.size > 0
        ? `Ruleset required checks: ${[...requiredContexts].join(', ')}`
        : `No active ruleset requires status checks for ${owner}/${repo}@${branch}`,
    );
    return { contexts: requiredContexts, source: 'rulesets' };
  }
  
  // Parse repos from previous step
  const registeredRepos = String(process.env.REGISTERED_REPOS_INPUT || '')
    .split(',')
    .map(r => r.trim())
    .filter(Boolean);
  
  const requestedSyncHash = normalizeSyncHash(
    process.env.ACTIVE_SYNC_HASH_INPUT ||
      process.env.SYNC_HASH_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.active_sync_hash) ||
      (context.payload.client_payload && context.payload.client_payload.sync_hash) ||
    '',
  );
  const trustedSyncActors = String(process.env.TRUSTED_SYNC_ACTORS || '')
    .split(',')
    .map((actor) => actor.trim())
    .filter(Boolean);

  let expectedCanaryRepos = [];
  if (requestedSyncHash === 'candidate') {
    const canaryConfigPath = process.env.CONSUMER_SYNC_CANARIES_PATH ||
      'config/consumer_sync_canaries.json';
    const canaryConfig = JSON.parse(
      fs.readFileSync(canaryConfigPath, 'utf8'),
    );
    expectedCanaryRepos = (canaryConfig.canaries || [])
      .map((entry) => String(entry?.repo || '').trim())
      .filter(Boolean);
  }

  // Candidate reconciliation is a registry-owned operation. Processing the
  // complete consumer registry here lets unrelated non-canary delivery PRs
  // create target_missing failures and can make promotion evidence unusable.
  // Always derive this target set from the canonical canary registry.
  const targetRepos = requestedSyncHash === 'candidate'
    ? expectedCanaryRepos
    : inputRepos === 'all'
      ? registeredRepos
      : inputRepos.split(',').map(r => r.trim());
  
  console.log(`Registered consumer repos: ${registeredRepos.join(', ')}`);
  console.log(`Processing repos: ${targetRepos.join(', ')}`);
  console.log(`Auto-merge: ${autoMerge}, Dry run: ${dryRun}`);
  console.log(`Evidence only: ${evidenceOnly}`);
  console.log(`Candidate evidence authorized: ${candidateEvidenceAuthorized}`);
  console.log(`Cleanup stale sync branches: ${cleanupBranches}\n`);
  if (requestedSyncHash) {
    console.log(`Target sync hash: ${requestedSyncHash}`);
  }
  
  const results = [];
  const canaryEvidence = [];
  
  function syncMetadata(pr) {
    const match = String(pr.body || '').match(
      /<!-- workflows-consumer-sync:v1 ([\s\S]*?) -->/,
    );
    if (!match) return null;
    try {
      return JSON.parse(match[1]);
    } catch (_) {
      return null;
    }
  }
  
  async function activeReviewThreadCount(owner, repo, number) {
    try {
      const data = await github.graphql(
        `query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              reviewThreads(first: 100) {
                pageInfo { hasNextPage }
                nodes { isResolved isOutdated }
              }
            }
          }
        }`,
        { owner, repo, number },
      );
      const reviewThreads = data.repository.pullRequest.reviewThreads;
      if (reviewThreads.pageInfo.hasNextPage) {
        core.warning(
          `Review-thread pagination exceeded the safe evidence window for ${owner}/${repo}#${number}`,
        );
        return -1;
      }
      return reviewThreads.nodes.filter(
        (thread) => !thread.isResolved && !thread.isOutdated,
      ).length;
    } catch (error) {
      core.warning(`Unable to read active review threads for ${owner}/${repo}#${number}: ${error}`);
      return -1;
    }
  }

  async function confirmExactHeadReviewClear({ owner, repo, pr, expectMerged }) {
    const { data: freshPr } = await withRetry((client) => client.rest.pulls.get({
      owner,
      repo,
      pull_number: pr.number,
    }));
    if (freshPr?.head?.sha !== pr.head.sha) {
      return {
        ok: false,
        reason: 'head_changed',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.head?.sha || '',
      };
    }
    if (expectMerged && !freshPr?.merged_at) {
      return {
        ok: false,
        reason: 'merged_state_changed',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.head?.sha || '',
      };
    }
    if (!expectMerged && freshPr?.state !== 'open') {
      return {
        ok: false,
        reason: 'pr_state_changed',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.head?.sha || '',
      };
    }
    const reviewWindow = evaluatePostPushReviewWindow(
      freshPr,
      new Date().toISOString(),
    );
    if (!reviewWindow.ready) {
      return {
        ok: false,
        reason: 'review_window_pending',
        activeReviewThreads: -1,
        freshHeadSha: freshPr.head.sha,
        reviewWindow,
      };
    }
    const activeReviewThreads = await activeReviewThreadCount(owner, repo, pr.number);
    if (activeReviewThreads !== 0) {
      return {
        ok: false,
        reason: 'review_blocked',
        activeReviewThreads,
        freshHeadSha: freshPr.head.sha,
      };
    }
    return {
      ok: true,
      reason: 'exact_head_review_clear',
      activeReviewThreads,
      freshHeadSha: freshPr.head.sha,
      freshPr,
    };
  }
  
  for (const repoEntry of targetRepos) {
    const [entryOwner, entryRepo] = repoEntry.includes('/')
      ? repoEntry.split('/')
      : [defaultOwner, repoEntry];
    const owner = entryOwner || defaultOwner;
    const repo = entryRepo;
  
    console.log(`\n=== ${owner}/${repo} ===`);
  
    try {
      // Find open sync PRs (paginate — first page alone can miss open sync heads).
      const prs = await withRetry((client) =>
        client.paginate(client.rest.pulls.list, {
          owner,
          repo,
          state: 'open',
          per_page: 100,
        }),
      );
  
      const syncPRs = prs.filter((pr) => isTrustedGeneratedDeliveryPr(pr, trustedSyncActors));
      let closedPRs = [];
      if (cleanupBranches || requestedSyncHash === 'candidate') {
        closedPRs = await withRetry((client) => client.paginate(client.rest.pulls.list, {
          owner,
          repo,
          state: 'closed',
          per_page: 100,
        }));
      }
  
      if (cleanupBranches) {
        try {
          const branches = await withRetry((client) => client.paginate(
            client.rest.repos.listBranches,
            { owner, repo, per_page: 100 },
          ));
          const branchesToDelete = collectDeletableSyncBranches({
            branches,
            // Pass every open PR so an open sync head beyond the filtered set is never deleted.
            openPullRequests: prs,
            closedPullRequests: closedPRs,
          });
  
          if (branchesToDelete.length > 0) {
            console.log(
              `Found ${branchesToDelete.length} closed sync PR branch(es) to clean up`,
            );
          }
  
          for (const branch of branchesToDelete) {
            if (dryRun) {
              console.log(`[DRY RUN] Would delete ${branch}`);
              results.push({
                owner,
                repo,
                branch,
                status: 'branch_deleted',
                dry_run: true,
              });
              continue;
            }
  
            try {
              await withRetry((client) => client.rest.git.deleteRef({
                owner,
                repo,
                ref: `heads/${branch}`,
              }));
              console.log(`✓ Deleted leftover branch ${branch}`);
              results.push({ owner, repo, branch, status: 'branch_deleted' });
            } catch (branchErr) {
              console.log(
                `⚠ Could not delete leftover branch ${branch}: ${branchErr.message}`,
              );
              results.push({
                owner,
                repo,
                branch,
                status: 'branch_delete_failed',
                error: branchErr.message,
              });
            }
          }
        } catch (cleanupErr) {
          console.log(`⚠ Sync branch cleanup failed: ${cleanupErr.message}`);
          results.push({
            owner,
            repo,
            status: 'branch_delete_failed',
            error: cleanupErr.message,
          });
        }
      }

      let candidatePRs = syncPRs;
      let recoveredMergedCandidate = false;
      const hasOpenCandidate = syncPRs.some(
        (pr) => pr?.head?.ref === syncBranchForHash('candidate'),
      );
      if (!hasOpenCandidate && requestedSyncHash === 'candidate') {
        const mergedCandidate = selectLatestMergedCandidatePr(closedPRs, trustedSyncActors);
        if (mergedCandidate) {
          candidatePRs = [mergedCandidate];
          recoveredMergedCandidate = true;
          console.log(
            `Recovering canary evidence from merged PR #${mergedCandidate.number} ` +
              `(${mergedCandidate.head.sha})`,
          );
        }
      }

      if (candidatePRs.length === 0) {
        console.log('No sync PRs found');
        results.push({ owner, repo, status: 'no_prs' });
        continue;
      }
  
      let selection = selectMergeEligibleSyncPr(candidatePRs, {
        syncHash: requestedSyncHash,
        now: new Date().toISOString(),
        repository: `${owner}/${repo}`,
      });
      if (selection.missingExpected) {
        console.log(
          `Expected sync PR branch ${selection.expectedBranch} was not found; leaving ` +
            `${candidatePRs.length} sync PRs untouched`,
        );
        results.push({
          owner,
          repo,
          status: 'target_missing',
          expected_branch: selection.expectedBranch,
          open_sync_prs: candidatePRs.map((item) => ({
            number: item.number,
            branch: item.head.ref,
            url: item.html_url,
          })),
        });
        continue;
      }
  
      const { data: selectedHeadCommit } = await withRetry((client) =>
        client.rest.git.getCommit({
          owner,
          repo,
          commit_sha: selection.active.head.sha,
        }),
      );
      selection = selectMergeEligibleSyncPr(candidatePRs, {
        syncHash: requestedSyncHash,
        now: new Date().toISOString(),
        repository: `${owner}/${repo}`,
        desiredTreeHash: selectedHeadCommit?.tree?.sha || '',
      });
  
      // If multiple sync PRs exist, close older ones as stale
      if (selection.stale.length > 0) {
        console.log(
          `Found ${candidatePRs.length} sync PRs - closing ` +
            `${selection.stale.length} stale PRs`,
        );
  
        for (const stalePR of selection.stale) {
          console.log(`\nClosing stale PR #${stalePR.number}: ${stalePR.title}`);
          console.log(`Branch: ${stalePR.head.ref}, Created: ${stalePR.created_at}`);
  
          if (!dryRun) {
            try {
              // Close PR
              await withRetry((client) => client.rest.pulls.update({
                owner,
                repo,
                pull_number: stalePR.number,
                state: 'closed'
              }));
              console.log('✓ Closed');
  
              // Delete branch
              try {
                await withRetry((client) => client.rest.git.deleteRef({
                  owner,
                  repo,
                  ref: `heads/${stalePR.head.ref}`
                }));
                console.log('✓ Branch deleted');
              } catch (delErr) {
                console.log(`⚠ Branch delete failed: ${delErr.message}`);
              }
              results.push({
                owner,
                repo,
                pr: stalePR.number,
                branch: stalePR.head.ref,
                status: 'stale_closed',
              });
            } catch (staleErr) {
              console.log(`✗ Stale close failed: ${staleErr.message}`);
              results.push({
                owner,
                repo,
                pr: stalePR.number,
                branch: stalePR.head.ref,
                status: 'stale_close_failed',
                error: staleErr.message,
              });
            }
          } else {
            console.log('[DRY RUN] Would close and delete branch');
            results.push({
              owner,
              repo,
              pr: stalePR.number,
              branch: stalePR.head.ref,
              status: 'stale_closed',
              dry_run: true,
            });
          }
        }
      }
  
      if (!selection.eligibility?.eligible) {
        const reason = selection.eligibility?.reason || 'missing_delivery_record';
        console.log(`Delivery contract blocks merge: ${reason}`);
        const deliveryDisposition = reason === 'lease_expired'
          ? 'expired'
          : selection.deliveryRecord
            ? 'superseded'
            : 'owner-decision';
        const deliveryContext = {
          owner,
          repo,
          pr: selection.active.number,
          branch: selection.active.head.ref,
          head_sha: selection.active.head.sha,
          delivery_generation: selection.deliveryRecord?.generation || '',
          delivery_lane: generatedDeliveryLane(selection.active.head.ref),
          delivery_disposition: deliveryDisposition,
          delivery_reason: reason,
          blocker_owner: deliveryDisposition === 'owner-decision' ? 'source' : 'maint-71',
          next_command: deliveryDisposition === 'expired'
            ? 'close-expired-delivery'
            : deliveryDisposition === 'superseded'
              ? 'close-or-refresh-delivery'
              : 'attach-or-infer-delivery-record',
        };
        if (deliveryDisposition === 'expired' || deliveryDisposition === 'superseded') {
          if (!dryRun) {
            await withRetry((client) => client.rest.issues.createComment({
              owner,
              repo,
              issue_number: selection.active.number,
              body: [
                'Closing this generated delivery as no longer current.',
                `delivery_reason: ${reason}`,
                `delivery_disposition: ${deliveryDisposition}`,
                `next_command: ${deliveryContext.next_command}`,
              ].join('\n'),
            }));
            await withRetry((client) => client.rest.pulls.update({
              owner,
              repo,
              pull_number: selection.active.number,
              state: 'closed',
            }));
          }
          results.push({ ...deliveryContext, status: 'stale_closed', dry_run: dryRun });
          continue;
        }
        results.push({
          ...deliveryContext,
          status: 'delivery_contract_blocked',
          delivery_reason: reason,
        });
        continue;
      }
  
      // Process the selected active PR
      let pr = selection.active;
      try {
        const { data: fullPr } = await withRetry((client) => client.rest.pulls.get({
          owner,
          repo,
          pull_number: pr.number,
        }));
        const changedSinceSelection = !fullPr
          || fullPr.number !== pr.number
          || fullPr.head?.ref !== pr.head?.ref
          || fullPr.head?.sha !== pr.head?.sha
          || fullPr.base?.ref !== pr.base?.ref
          || fullPr.user?.login !== pr.user?.login
          || fullPr.body !== pr.body
          || !isTrustedGeneratedDeliveryPr(fullPr, trustedSyncActors);
        if (changedSinceSelection) {
          throw new Error('refreshed PR no longer matches the trusted delivery selection');
        }
        pr = fullPr;
      } catch (error) {
        const message = String(error?.message || error);
        console.log(`Unable to refresh generated PR #${pr.number}: ${message}`);
        results.push({
          owner,
          repo,
          pr: pr.number,
          branch: pr.head.ref,
          head_sha: pr.head.sha,
          status: 'pr_refresh_failed',
          error: `PR refresh before branch update: ${message}`,
        });
        continue;
      }
      const metadata = syncMetadata(pr);
      console.log(`\nProcessing active PR #${pr.number}: ${pr.title}`);
      console.log(`Branch: ${pr.head.ref}`);
      console.log(`Created: ${pr.created_at}`);

      if (!candidateEvidenceAllowsMutation({
        branch: pr.head.ref,
        evidenceOnly,
        authorized: candidateEvidenceAuthorized,
      })) {
        console.log('Candidate merge blocked: pre-merge evidence was not persisted successfully');
        results.push({
          owner,
          repo,
          pr: pr.number,
          branch: pr.head.ref,
          head_sha: pr.head.sha,
          delivery_generation: selection.deliveryRecord?.generation || '',
          delivery_lane: generatedDeliveryLane(pr.head.ref),
          delivery_disposition: 'awaiting-canary-evidence',
          blocker_owner: 'maint-71',
          next_command: 'rerun-active-sync-hash-candidate',
          status: 'candidate_evidence_required',
        });
        continue;
      }

      const reviewWindow = evaluatePostPushReviewWindow(pr, new Date().toISOString());
      if (!reviewWindow.ready) {
        console.log(`Post-push review window remains open until ${reviewWindow.eligible_at || 'unknown'}`);
        results.push({
          owner,
          repo,
          pr: pr.number,
          branch: pr.head.ref,
          head_sha: pr.head.sha,
          delivery_generation: selection.deliveryRecord?.generation || '',
          delivery_lane: generatedDeliveryLane(pr.head.ref),
          delivery_disposition: 'awaiting-review-window',
          blocker_owner: 'maint-71',
          next_command: reviewWindow.eligible_at
            ? `rerun-after:${reviewWindow.eligible_at}`
            : 'rerun-after-review-window',
          status: 'review_window_pending',
          review_window_eligible_at: reviewWindow.eligible_at || '',
        });
        continue;
      }
  
      // Combined legacy statuses + every check-run page (paginate returns a flat array).
      const { data: combinedStatus } = await withRetry((client) =>
        client.rest.repos.getCombinedStatusForRef({
          owner,
          repo,
          ref: pr.head.sha,
        }),
      );
      const paginatedCheckRuns = await withRetry((client) =>
        client.paginate(client.rest.checks.listForRef, {
          owner,
          repo,
          ref: pr.head.sha,
          per_page: 100,
        }),
      );
      const statusAsChecks = (combinedStatus.statuses || []).map((status) => {
        const state = String(status.state || '').toLowerCase();
        return {
          name: status.context,
          status: state === 'pending' ? 'in_progress' : 'completed',
          conclusion:
            state === 'success'
              ? 'success'
              : state === 'pending'
                ? null
                : 'failure',
        };
      });
      const checkNames = new Set(
        paginatedCheckRuns.map((check) => String(check?.name || '').trim()).filter(Boolean),
      );
      const allChecks = [
        ...paginatedCheckRuns,
        ...statusAsChecks.filter((status) => !checkNames.has(String(status.name || '').trim())),
      ];
      const requiredCheckPolicy = await getRequiredContexts({
        owner,
        repo,
        branch: pr.base.ref,
      });
      const requiredContexts = requiredCheckPolicy.contexts;
      let classification = requiredContexts.size > 0
        ? classifySyncPrChecks({ checkRuns: allChecks, requiredContexts })
        : { status: 'ready', failed: [], pending: [] };
      // Fail closed: a required context absent from both checks and statuses is not "ready".
      if (requiredContexts.size > 0 && classification.status === 'ready') {
        const seenNames = new Set(
          allChecks.map((check) => String(check?.name || '').trim()).filter(Boolean),
        );
        const missingRequired = [...requiredContexts].filter((ctx) => !seenNames.has(ctx));
        if (missingRequired.length > 0) {
          classification = {
            status: 'checks_pending',
            failed: [],
            pending: missingRequired.map((name) => ({ name, status: 'queued' })),
          };
        }
      }
      const gatingChecks = requiredContexts.size > 0
        ? selectSyncPrGatingChecks({ checkRuns: allChecks, requiredContexts })
        : [];
      const checkGateMode = requiredCheckPolicy.source;
      const failedChecks = classification.failed;
      const pendingChecks = classification.pending;
      const activeReviewThreads = await activeReviewThreadCount(
        owner,
        repo,
        pr.number,
      );
      const deliveryState = classifyGeneratedPr({
        pr,
        checkState: classification,
        activeReviewThreadCount: activeReviewThreads,
        now: new Date().toISOString(),
      });
      const deliveryContext = {
        owner,
        repo,
        pr: pr.number,
        branch: pr.head.ref,
        head_sha: pr.head.sha,
        delivery_generation: selection.deliveryRecord?.generation || '',
        delivery_lane: generatedDeliveryLane(pr.head.ref),
        delivery_disposition: deliveryState.disposition,
        blocker_owner: deliveryState.blocker_owner,
        next_command: deliveryState.next_command,
      };
  
      console.log(
        `Checks (${checkGateMode}): ${gatingChecks.length} gating, ` +
          `${failedChecks.length} failed, ${pendingChecks.length} pending`,
      );
  
      if (deliveryState.disposition === 'review-blocked') {
        console.log(`Active review threads block merge: ${activeReviewThreads}`);
        results.push({
          ...deliveryContext,
          status: 'review_blocked',
          active_review_thread_count: activeReviewThreads,
        });
        continue;
      }
  
      if (classification.status === 'checks_failed') {
        console.log('Failed checks:');
        failedChecks.forEach(c => console.log(`  - ${c.name}: ${c.conclusion}`));
        results.push({
          ...deliveryContext,
          status: 'checks_failed',
          failed_checks: failedChecks.map((check) => ({
            name: check.name,
            conclusion: check.conclusion,
            status: check.status,
          })),
        });
        continue;
      }
  
      if (classification.status === 'checks_pending') {
        console.log('Waiting for checks to complete');
        results.push({
          ...deliveryContext,
          status: 'checks_pending',
          pending_checks: pendingChecks.map((check) => ({
            name: check.name,
            conclusion: check.conclusion,
            status: check.status,
          })),
        });
        continue;
      }
  
      // All checks passed. For an actual merge, run the runtime AC guard before
      // the final exact-head/thread query so no intervening network action sits
      // between the hard review gate and the merge call.
      const willMerge = autoMerge && !dryRun && !recoveredMergedCandidate;
      // Strict required-status-check rules evaluate the merge result. If the
      // head is behind main, every merge strategy creates a new result without
      // the head's Gate context. Update the generated branch and wait for its
      // fresh Gate and mandatory review window instead of attempting a merge.
      if (requiresStrictGateBranchUpdate({ pr, requiredContexts, willMerge })) {
        try {
          await withRetry((client) => client.rest.pulls.updateBranch({
            owner,
            repo,
            pull_number: pr.number,
            expected_head_sha: pr.head.sha,
          }));
          console.log(`Requested branch update for behind PR #${pr.number}; awaiting fresh Gate`);
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-review-window',
            blocker_owner: 'maint-71',
            next_command: 'rerun-after-updated-branch-gate',
            status: 'review_window_pending',
            branch_update_started: true,
          });
        } catch (error) {
          const message = String(error?.message || error);
          console.log(`Unable to update behind PR #${pr.number}: ${message}`);
          results.push({ ...deliveryContext, status: 'branch_update_failed', error: message });
        }
        continue;
      }
      if (willMerge) {
        try {
          await assertRuntimeAcMergeAllowed({
            github,
            core,
            owner,
            repo,
            prNumber: pr.number,
            withRetry,
            source: 'maint-71-merge-sync-prs',
          });
        } catch (guardError) {
          const message = String(guardError?.message || guardError);
          console.log(`Runtime AC merge guard blocked PR #${pr.number}: ${message}`);
          results.push({
            ...deliveryContext,
            status: 'merge_blocked_runtime_ac',
            error: message,
          });
          continue;
        }
      }

      const finalGate = await confirmExactHeadReviewClear({
        owner,
        repo,
        pr,
        expectMerged: recoveredMergedCandidate,
      });
      if (!finalGate.ok) {
        console.log(`Final exact-head review gate blocked delivery: ${finalGate.reason}`);
        if (finalGate.reason === 'review_window_pending') {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-review-window',
            blocker_owner: 'maint-71',
            next_command: finalGate.reviewWindow?.eligible_at
              ? `rerun-after:${finalGate.reviewWindow.eligible_at}`
              : 'rerun-after-review-window',
            status: 'review_window_pending',
            review_window_eligible_at: finalGate.reviewWindow?.eligible_at || '',
          });
        } else if (finalGate.reason === 'review_blocked') {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'review-blocked',
            blocker_owner: 'closer',
            next_command: finalGate.activeReviewThreads < 0
              ? 'retry-review-thread-query'
              : 'resolve-active-review-threads',
            status: 'review_blocked',
            active_review_thread_count: finalGate.activeReviewThreads,
          });
        } else {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-exact-head',
            blocker_owner: 'maint-71',
            next_command: 'rerun-exact-head-gate',
            status: 'head_changed',
            observed_head_sha: finalGate.freshHeadSha || '',
            gate_reason: finalGate.reason,
          });
        }
        continue;
      }

      if (metadata?.sync_phase === 'canary' && metadata?.plan_id) {
        canaryEvidence.push({
          repo: `${owner}/${repo}`,
          plan_id: metadata.plan_id,
          pr: pr.number,
          head_sha: pr.head.sha,
          evidence_source: recoveredMergedCandidate
            ? 'merged-candidate-recovery'
            : 'open-candidate',
          required_check_state: 'success',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
      }

      if (recoveredMergedCandidate) {
        console.log('✓ Recovered green, review-clear evidence from the merged candidate PR');
        results.push({
          ...deliveryContext,
          status: 'evidence_recovered',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }

      if (!autoMerge) {
        console.log('✓ Ready to merge (auto-merge disabled)');
        results.push({
          ...deliveryContext,
          status: 'ready',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }
  
      if (dryRun) {
        console.log('✓ Would merge (dry run)');
        results.push({
          ...deliveryContext,
          status: 'dry_run_merge',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }
  
      // Merge the PR. The final exact-head and live-thread query above is the
      // immediately preceding network gate for this exact head.
  
      try {
        const mergeMethods = ['merge', 'squash', 'rebase'];
        let merged = false;
        let lastError = null;
  
        for (const merge_method of mergeMethods) {
          try {
            await withRetry((client) => client.rest.pulls.merge({
              owner,
              repo,
              pull_number: pr.number,
              merge_method,
              commit_title: pr.title,
              commit_message:
                `Automated merge of sync PR\n\n` +
                `Sync hash: ${requestedSyncHash || metadata?.sync_hash || 'unknown'}\n` +
                `Delivery generation: ${selection.deliveryRecord?.generation || 'unknown'}`
            }));
            console.log(`✓ Merged successfully (method=${merge_method})`);
            merged = true;
            break;
          } catch (e) {
            lastError = e;
            const message = String(e?.message || 'unknown error');
            console.log(`⚠ Merge attempt failed (method=${merge_method}): ${message}`);
            if (!message.toLowerCase().includes('repository rule violations')) {
              break;
            }
          }
        }
  
        if (!merged) {
          throw lastError || new Error('Merge failed');
        }
  
        // Delete the branch
        try {
          await withRetry((client) => client.rest.git.deleteRef({
            owner,
            repo,
            ref: `heads/${pr.head.ref}`
          }));
          console.log('✓ Branch deleted');
          results.push({
            ...deliveryContext,
            status: 'branch_deleted',
          });
        } catch (e) {
          console.log(`⚠ Could not delete branch: ${e.message}`);
          results.push({
            ...deliveryContext,
            status: 'branch_delete_failed',
            error: e.message,
          });
        }
  
        results.push({
          ...deliveryContext,
          status: 'merged',
        });
      } catch (e) {
        console.log(`✗ Merge failed: ${e.message}`);
        results.push({
          ...deliveryContext,
          status: 'merge_failed',
          error: e.message,
        });
      }
    } catch (e) {
      console.log(`✗ Error processing ${repo}: ${e.message}`);
      results.push({ owner, repo, status: 'error', error: e.message });
    }
  }
  
  // Summary
  console.log('\n=== Summary ===');
  console.log(JSON.stringify(results, null, 2));
  const report = buildMergeReport({
    results,
    registeredRepos,
    targetRepos,
    autoMerge,
    dryRun,
    syncHash: requestedSyncHash,
    run: {
      repository: `${context.repo.owner}/${context.repo.repo}`,
      run_id: context.runId,
      run_number: context.runNumber,
      workflow: context.workflow,
      ref: context.ref,
      sha: context.sha,
    },
  });
  const reportPath = process.env.SYNC_PR_MERGE_REPORT_JSON || 'artifacts/sync-pr-merge-report.json';
  const canaryEvidencePath = 'artifacts/sync-canary-evidence.json';
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.mkdirSync(path.dirname(canaryEvidencePath), { recursive: true });
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  fs.writeFileSync(
    canaryEvidencePath,
    `${JSON.stringify({
      schema: 'workflows.consumer-sync-canary-evidence/v1',
      version: 1,
      results: canaryEvidence,
    }, null, 2)}\n`,
    'utf8',
  );
  const evidenceValidation = requestedSyncHash === 'candidate'
    ? validateCanaryEvidence(canaryEvidence, expectedCanaryRepos)
    : { ok: true, errors: [], plan_id: '' };
  if (evidenceOnly && !evidenceValidation.ok) {
    core.setFailed(
      `Canary evidence is incomplete or unsafe: ${evidenceValidation.errors.join(', ')}`,
    );
  }
  await core.summary.addRaw(buildMarkdownSummary(report)).write();
  if (!dryRun && !evidenceOnly && report.handoff_records.length > 0) {
    // Fleet-wide refresh: a targeted Maint 71 repos filter must not cause
    // Maint 82 to stale unscanned repos. Dispatch is best-effort so a
    // permissions/transient failure does not fail the reconciler run.
    try {
      await withRetry((client) => client.rest.repos.createDispatchEvent({
        owner: context.repo.owner,
        repo: context.repo.repo,
        event_type: 'sync-dependabot-campaign',
        client_payload: {
          repos: registeredRepos.join(','),
          delivery_handoff_records: report.handoff_records,
        },
      }));
    } catch (dispatchError) {
      core.notice(
        `Maint 71 handoff dispatch failed (non-blocking): ${dispatchError.message}`,
      );
    }
  }
  
  const merged = report.summary.merged;
  const stale = report.summary.stale_closed;
  const branchesDeleted = report.summary.branch_deleted;
  // A consumer's own red CI (checks_failed) is outside this workflow's control,
  // so it must NOT fail the fleet janitor run — otherwise one red consumer turns
  // every scheduled flush red and forces re-runs. Only genuine sync-system action
  // failures (merge/cleanup/missing-target) are blocking; consumer CI health is
  // surfaced via the merge report and Health 68 instead.
  const blockingFailures = results.filter((r) => isBlockingSyncSystemFailure(r.status));
  const branchDeleteFailures = results.filter((r) => r.status === 'branch_delete_failed');
  if (branchDeleteFailures.length > 0) {
    core.notice(
      `${branchDeleteFailures.length} sync branch(es) could not be deleted; ` +
        'the next scheduled run retries the cleanup.',
    );
  }
  const checksFailed = results.filter((r) => r.status === 'checks_failed');
  if (checksFailed.length > 0) {
    core.notice(
      `${checksFailed.length} consumer sync PR(s) have failing checks (consumer CI); ` +
        `left open, not treated as a janitor failure.`,
    );
  }
  const failed = dryRun ? 0 : blockingFailures.length;
  const pending = report.summary.checks_pending;
  const ready = report.summary.ready;
  
  console.log(`\nMerged: ${merged}`);
  console.log(`Stale closed: ${stale}`);
  console.log(`Leftover branches deleted: ${branchesDeleted}`);
  console.log(`Failed: ${failed}`);
  console.log(`Pending: ${pending}`);
  console.log(`Ready (not auto-merged): ${ready}`);
  if (dryRun && blockingFailures.length > 0) {
    core.notice(
      `Dry run observed ${blockingFailures.length} blocking result(s); ` +
        'report-only mode remains successful.',
    );
  }
  
  if (failed > 0) {
    const blockingStatuses = [...new Set(blockingFailures.map((result) => result.status))];
    core.setFailed(
      `${failed} blocking sync-system failure(s): ${blockingStatuses.join(', ')}`,
    );
  }
}

module.exports = { run };
