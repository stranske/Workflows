# PR Finalization Skill

You are helping finalize a PR through merge, verification, and follow-ups.

## Inputs
- **pr_number**: PR number (detect from current branch if not provided)
- **verify_mode**: `compare` (thorough, dual-LLM) or `evaluate` (quick, single-LLM)
- **max_iterations**: Maximum bot review + CI fix cycles (default: 3)
- **skip_verification**: Skip verification step (for non-issue PRs or doc-only changes)

## Phase 1: Address Bot Reviews (Parallel with CI)

**Timeline**: 5-10 minutes per iteration, reset on each push

1. **Poll for bot comments every 30 seconds** until 2 minutes of silence or max time
   ```bash
   # Poll issue-level comments
   gh pr view $PR_NUMBER --json comments | \
     jq --arg last_check "$LAST_CHECK" '.comments[] |
       select(.author.login | test("bot|reviewer")) |
       select(.createdAt > $last_check) |
       {id, body, createdAt}'

   # Poll inline review comments (PR review threads)
   gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/comments | \
     jq --arg last_check "$LAST_CHECK" '.[] |
       select(.user.login | test("bot|copilot|reviewer")) |
       select(.created_at > $last_check) |
       {id, body, path, line, created_at}'
   ```

2. **For each new bot comment**:
   - Read the comment body, file path, line number
   - Use LLM to evaluate: "Is this a valid issue? Should we fix it?"
   - Decision criteria:
     - **Fix if**: Clear bug, standards violation, security issue, or quality improvement
     - **Skip if**: False positive, out of scope, or contested convention

3. **If fix warranted**:
   - Read the file context (±20 lines from comment location)
   - Make the fix
   - Push update with commit message: `fix: address bot review - <brief summary>`
   - Get review thread node IDs (not comment IDs):
     ```bash
     # List unresolved review threads
     gh api graphql -f query='
       query($pr: Int!, $owner: String!, $repo: String!) {
         repository(owner: $owner, name: $repo) {
           pullRequest(number: $pr) {
             reviewThreads(first: 50) {
               nodes { id isResolved comments(first: 1) {
                 nodes { body path line }
               }}
             }
           }
         }
       }' -F owner="{owner}" -F repo="{repo}" -F pr="$PR_NUMBER"
     ```
   - Resolve the matching thread:
     ```bash
     gh api graphql -f query="
       mutation {
         resolveReviewThread(input: {threadId: \"$THREAD_ID\"}) {
           thread { isResolved }
         }
       }"
     ```
   - Add reply: "Fixed in <commit_sha>. <explanation of what changed>"
   - **Reset iteration timer** - start Phase 1 again

4. **Parallel execution**: Run CI monitoring (Phase 2) concurrently

## Phase 2: Fix Failing CI (Parallel with Bot Reviews)

**Timeline**: 5-10 minutes per iteration, reset on each push

1. **Poll for CI status every 20 seconds**:
   ```bash
   gh pr checks $PR_NUMBER --json name,state,conclusion,detailsUrl
   ```

2. **On first failure**:
   - Identify failing check(s)
   - Fetch logs:
     ```bash
     # Get workflow run ID
     RUN_ID=$(gh pr view $PR_NUMBER --json statusCheckRollup --jq \
       '.statusCheckRollup[] | select(.name=="Gate") | .workflowRun.databaseId')

     # Get failed job logs
     gh run view $RUN_ID --log-failed | tail -100
     ```

3. **Diagnose and fix**:
   - Read error messages
   - Identify root cause (lint, type error, test failure, etc.)
   - Make fixes
   - Push update: `fix: resolve CI failure - <check name>`
   - **Reset iteration timer** - start Phase 2 again

4. **Continue until**: All checks pass or max_iterations reached

## Phase 3: Wait for Clean State

**Before proceeding to merge, ensure**:
- No bot comments in last 2 minutes
- All CI checks passing (green)
- No unresolved review threads (critical)
- Current iteration count < max_iterations

**If max_iterations exceeded**:
- Comment on PR: "⚠️ PR finalization paused after $max_iterations iterations.
  Remaining issues require manual review."
- Exit with summary of remaining work

## Phase 4: Merge PR

1. **Verify merge readiness**:
   ```bash
   gh pr view $PR_NUMBER --json mergeable,mergeStateStatus
   ```
   - Check: mergeable=true, mergeStateStatus=clean

2. **Generate merge commit message**:
   ```bash
   # Get PR title, body, and linked issues
   gh pr view $PR_NUMBER --json title,body,closingIssuesReferences

   # Format:
   # <pr_title>
   #
   # <pr_body>
   #
   # Closes #<issue_number> (for each linked issue, if any)
   ```

3. **Squash merge**:
   ```bash
   gh pr merge $PR_NUMBER --squash --auto \
     --subject "<pr_title>" \
     --body "<formatted_body>"
   ```

4. **Wait for merge to complete** (poll every 5 seconds for up to 30 seconds):
   ```bash
   gh pr view $PR_NUMBER --json state,merged,mergedAt
   ```

## Phase 5: Apply Verification (if applicable)

**Skip this phase if**:
- `skip_verification` is true
- PR was not created from an issue
- PR is doc-only or trivial
- Repository doesn't have agents-verifier.yml workflow

1. **Check if PR came from an issue**:
   ```bash
   # Check PR body for "Closes #<issue_number>" or linked issues
   gh pr view $PR_NUMBER --json body,closingIssuesReferences
   ```

2. **Check if repository has verification workflow**:
   ```bash
   # Check if agents-verifier.yml exists
   if ! gh api repos/{owner}/{repo}/contents/.github/workflows/agents-verifier.yml \
        --jq '.name' 2>/dev/null; then
     echo "Repository doesn't have verification workflow, skipping"
     exit 0
   fi
   ```

3. **Apply verification label**:
   ```bash
   # Use verify_mode to determine label
   LABEL="verify:$verify_mode"  # verify:compare or verify:evaluate

   gh pr edit $PR_NUMBER --add-label "$LABEL"
   ```

4. **Wait for verification workflow** (max 10 minutes):
   ```bash
   # Record timestamp before applying label to filter runs
   LABEL_APPLIED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   HEAD_BRANCH=$(gh pr view $PR_NUMBER --json headRefName --jq '.headRefName')

   # Poll for workflow run triggered by label, scoped to this PR's branch
   while true; do
     STATUS=$(gh run list --workflow=agents-verifier.yml \
       --branch "$HEAD_BRANCH" \
       --json conclusion,status,createdAt | \
       jq -r --arg since "$LABEL_APPLIED_AT" \
         '[.[] | select(.createdAt >= $since)] | .[0] |
          (.conclusion // .status)')

     if [[ "$STATUS" == "success" ]]; then
       break
     elif [[ "$STATUS" == "failure" ]]; then
       echo "Verification workflow failed"
       break
     fi

     sleep 20
   done
   ```

5. **Read verification results**:
   ```bash
   # Get verification comment on PR
   gh pr view $PR_NUMBER --json comments --jq \
     '.comments[] | select(.author.login | contains("bot")) |
      select(.body | contains("Verification")) | .body'
   ```

## Phase 6: Handle Verification Feedback

**Parse verification verdict**: PASS, CONCERNS, or FAIL

### If PASS:
- Comment: "✅ Verification passed. PR finalization complete."
- Exit successfully

### If CONCERNS or FAIL:
1. **Analyze remaining work**:
   - Count incomplete tasks in verification report
   - Estimate complexity (simple fixes vs. substantial work)
   - Decision threshold:
     - **≤ 2 simple tasks**: Complete inline
     - **≥ 3 tasks OR complex work**: Create follow-up PR

2. **If completing inline**:
   - Parse task list from verification report
   - For each incomplete task:
     - Read relevant code
     - Make fixes
     - Check off task in original issue
   - Push updates
   - Re-run verification (apply label again)
   - Repeat Phase 5-6

3. **If creating follow-up PR**:
   ```bash
   # Check if repository has follow-up workflow
   if gh api repos/{owner}/{repo}/contents/.github/workflows/agents-verify-to-new-pr.yml \
        --jq '.name' 2>/dev/null; then
     gh pr edit $PR_NUMBER --add-label "verify:create-new-pr"
     # Wait for workflow to run (max 5 minutes)
     # Get new issue number from PR comments
     echo "🔄 Follow-up work tracked in #<issue_number>"
   else
     # Manual follow-up needed
     echo "⚠️ Verification CONCERNS - repository doesn't have automated follow-up."
     echo "Please create follow-up issue manually with remaining tasks."
   fi
   ```
   - Exit successfully

## Timeouts and Limits

| Phase | Timeout per iteration | Max iterations | Total time |
|-------|----------------------|----------------|------------|
| Bot reviews | 10 minutes | 3 | ~30 min |
| CI fixes | 10 minutes | 3 | ~30 min |
| Merge wait | 30 seconds | N/A | 30 sec |
| Verification | 10 minutes | 2 | ~20 min |
| Follow-up inline | 15 minutes | 1 | 15 min |

**Max total runtime**: ~60 minutes with all iterations
**Typical runtime**: 10-20 minutes for clean PRs

## Error Handling

### If bot continues commenting after 3 iterations:
- Comment: "⚠️ Bot review cycle exceeded 3 iterations. Remaining comments
  require maintainer evaluation."
- List unresolved comments with links
- Exit

### If CI fails after 3 fix attempts:
- Comment: "❌ CI failures persist after 3 attempts. Manual intervention needed."
- Link to failing checks
- Exit

### If verification fails twice:
- Comment: "⚠️ Verification did not pass after 2 attempts. Creating follow-up PR."
- Force apply `verify:create-new-pr` label
- Exit

## Success Criteria

Exit with success when:
- PR merged ✅
- All CI checks passed ✅
- Bot comments addressed ✅
- Verification passed (if applicable) ✅
- Follow-up work tracked (if needed) ✅

## Output Summary

At completion, provide:
```markdown
## PR Finalization Summary

**PR**: #<number> - <title>
**Merged**: <timestamp>
**Iterations**: <bot_review_count> bot reviews, <ci_fix_count> CI fixes
**Verification**: <PASS|CONCERNS|FAIL> (<verify_mode> mode)
**Follow-up**: <none|issue #<number>>

### Work Completed
- Addressed <count> bot review comments
- Fixed <count> CI failures
- <verification outcome>
- <follow-up status>

Total time: <duration>
```
