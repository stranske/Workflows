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
    classifyGeneratedPr,
    classifySyncPrChecks,
    collectDeletableSyncBranches,
    generatedDeliveryLane,
    normalizeSyncHash,
    parseBooleanInput,
    isTrustedGeneratedDeliveryPr,
    selectMergeEligibleSyncPr,
    selectSyncPrGatingChecks,
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
  const dryRun = parseBooleanInput(
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
  const fallbackCheckDenylist = [
    'Detect keepalive',
    'pr_meta',
    'resolve_pr',
    'Cleanup',
    '${' + '{ matrix.',
    'matrix.python-version',
  ];
  
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
      if (requiredContexts.size === 0) {
        console.log(
          `Branch protection for ${owner}/${repo}@${branch} has no required ` +
            'status checks; using denylist fallback',
        );
      }
      return requiredContexts;
    } catch (error) {
      const status = error?.status || error?.response?.status;
      if (status === 403 || status === 404) {
        console.log(
          `Branch protection unavailable for ${owner}/${repo}@${branch} ` +
            `(${status}); using denylist fallback`,
        );
        return new Set();
      }
      throw error;
    }
  }
  
  // Parse repos from previous step
  const registeredRepos = String(process.env.REGISTERED_REPOS_INPUT || '')
    .split(',')
    .map(r => r.trim())
    .filter(Boolean);
  
  // Determine which repos to process
  const targetRepos = inputRepos === 'all'
    ? registeredRepos
    : inputRepos.split(',').map(r => r.trim());
  const requestedSyncHash = normalizeSyncHash(
    process.env.SYNC_HASH_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.sync_hash) ||
    '',
  );
  const trustedSyncActors = String(process.env.TRUSTED_SYNC_ACTORS || '')
    .split(',')
    .map((actor) => actor.trim())
    .filter(Boolean);
  
  console.log(`Registered consumer repos: ${registeredRepos.join(', ')}`);
  console.log(`Processing repos: ${targetRepos.join(', ')}`);
  console.log(`Auto-merge: ${autoMerge}, Dry run: ${dryRun}`);
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
  
      if (cleanupBranches) {
        try {
          const [branches, closedPRs] = await Promise.all([
            withRetry((client) => client.paginate(client.rest.repos.listBranches, {
              owner,
              repo,
              per_page: 100,
            })),
            withRetry((client) => client.paginate(client.rest.pulls.list, {
              owner,
              repo,
              state: 'closed',
              per_page: 100,
            })),
          ]);
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
  
      if (syncPRs.length === 0) {
        console.log('No sync PRs found');
        results.push({ owner, repo, status: 'no_prs' });
        continue;
      }
  
      let selection = selectMergeEligibleSyncPr(syncPRs, {
        syncHash: requestedSyncHash,
        now: new Date().toISOString(),
        repository: `${owner}/${repo}`,
      });
      if (selection.missingExpected) {
        console.log(
          `Expected sync PR branch ${selection.expectedBranch} was not found; leaving ` +
            `${syncPRs.length} sync PRs untouched`,
        );
        results.push({
          owner,
          repo,
          status: 'target_missing',
          expected_branch: selection.expectedBranch,
          open_sync_prs: syncPRs.map((item) => ({
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
      selection = selectMergeEligibleSyncPr(syncPRs, {
        syncHash: requestedSyncHash,
        now: new Date().toISOString(),
        repository: `${owner}/${repo}`,
        desiredTreeHash: selectedHeadCommit?.tree?.sha || '',
      });
  
      // If multiple sync PRs exist, close older ones as stale
      if (selection.stale.length > 0) {
        console.log(
          `Found ${syncPRs.length} sync PRs - closing ` +
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
      const pr = selection.active;
      const metadata = syncMetadata(pr);
      console.log(`\nProcessing active PR #${pr.number}: ${pr.title}`);
      console.log(`Branch: ${pr.head.ref}`);
      console.log(`Created: ${pr.created_at}`);
  
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
      const requiredContexts = await getRequiredContexts({
        owner,
        repo,
        branch: pr.base.ref,
      });
      let classification = classifySyncPrChecks({
        checkRuns: allChecks,
        requiredContexts,
        fallbackDenylist: fallbackCheckDenylist,
      });
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
      const gatingChecks = selectSyncPrGatingChecks({
        checkRuns: allChecks,
        requiredContexts,
        fallbackDenylist: fallbackCheckDenylist,
      });
      const checkGateMode =
        requiredContexts.size > 0 ? 'required-contexts' : 'denylist-fallback';
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
  
      if (metadata?.sync_phase === 'canary' && metadata?.plan_id) {
        canaryEvidence.push({
          repo: `${owner}/${repo}`,
          plan_id: metadata.plan_id,
          pr: pr.number,
          required_check_state:
            classification.status === 'ready' ? 'success' : classification.status,
          active_review_thread_count: activeReviewThreads,
        });
      }
  
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
  
      // All checks passed
      if (!autoMerge) {
        console.log('✓ Ready to merge (auto-merge disabled)');
        results.push({
          ...deliveryContext,
          status: 'ready',
        });
        continue;
      }
  
      if (dryRun) {
        console.log('✓ Would merge (dry run)');
        results.push({
          ...deliveryContext,
          status: 'dry_run_merge',
        });
        continue;
      }
  
      // Merge the PR
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
  await core.summary.addRaw(buildMarkdownSummary(report)).write();
  if (!dryRun && report.handoff_records.length > 0) {
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
  const blockingFailures = results.filter(
    (r) =>
      r.status === 'merge_failed' ||
      r.status === 'stale_close_failed' ||
      r.status === 'target_missing',
  );
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
    core.setFailed(
      `${failed} blocking sync-system failure(s): merge_failed, stale_close_failed, or target_missing`,
    );
  }
}

module.exports = { run };
