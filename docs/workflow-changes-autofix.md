# Autofix Workflow Comment Suppression

This note documents the YAML changes required to **suppress autofix PR comments** when
there are no diagnostics to report. The composite action `.github/actions/build-pr-comment`
already emits `should-post` based on `scripts/build_autofix_pr_comment.py` metadata; the
workflow must wire that output into the `if:` guards on comment-posting steps.

## YAML changes (reusable-18-autofix.yml)

### 1) Capture `should-post` from the build step

```yaml
      - name: Build consolidated PR comment
        id: build_comment
        if: steps.guard.outputs.skip != 'true'
        env:
          AUTOFIX_MODE: ${{ steps.fix_results.outputs.mode }}
          AUTOFIX_CLEAN_LABEL: ${{ inputs.clean_label }}
        uses: ./workflows-lib/.github/actions/build-pr-comment
        with:
          output: autofix_pr_comment.md
          pr-number: ${{ inputs.pr_number }}
          scripts-path: workflows-lib/scripts
```

### 2) Gate all comment-posting steps on `should-post`

```yaml
      - name: Upsert consolidated PR comment
        if: steps.guard.outputs.skip != 'true' && steps.build_comment.outputs.should-post == 'true'
        uses: actions/github-script@v8
        env:
          PR_NUMBER: ${{ inputs.pr_number }}
        with:
          script: |
            const fs = require('fs');
            const marker = '<!-- AUTOFIX REPORT -->';
            const body = fs.readFileSync('autofix_pr_comment.md', 'utf8');
            const prNumber = Number(process.env.PR_NUMBER || '0');
            if (!prNumber) {
              core.info('No pull request number available; skipping PR comment update.');
              return;
            }
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { withRetry, paginateWithRetry } = retryHelpers;
            try {
              const comments = await paginateWithRetry(github, github.rest.issues.listComments, { owner: context.repo.owner, repo: context.repo.repo, issue_number: prNumber, per_page: 100 });
              const existing = comments.find(c => c.body && c.body.includes(marker));
              if (existing) {
                await withRetry(() => github.rest.issues.updateComment({ owner: context.repo.owner, repo: context.repo.repo, comment_id: existing.id, body }));
                console.log('Updated existing autofix status comment.');
              } else {
                await withRetry(() => github.rest.issues.createComment({ owner: context.repo.owner, repo: context.repo.repo, issue_number: prNumber, body }));
                console.log('Created new autofix status comment.');
              }
            } catch (error) {
              const message = String(error?.message || error || '');
              if (message.toLowerCase().includes('rate limit')) {
                core.warning(`Rate limited while updating autofix comment; skipping. ${message}`);
                return;
              }
              throw error;
            }

      - name: Upsert clean-mode file summary comment
        if: steps.guard.outputs.skip != 'true' && steps.build_comment.outputs.should-post == 'true' && steps.clean_mode.outputs.enabled == 'true' && steps.fix_results.outputs.changed == 'true'
        uses: actions/github-script@v8
        env:
          PR_NUMBER: ${{ inputs.pr_number }}
          FILE_LIST: ${{ steps.fix_results.outputs.file_list }}
          CLEAN_LABEL: ${{ inputs.clean_label }}
        with:
          script: |
            const prNumber = Number(process.env.PR_NUMBER || context.payload.pull_request?.number || 0);
            if (!prNumber) {
              core.info('No pull request number available; skipping clean-mode summary comment.');
              return;
            }
            const fs = require('fs');
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { withRetry, paginateWithRetry } = retryHelpers;
            const marker = '<!-- autofix-clean-summary -->';
            const filesRaw = (process.env.FILE_LIST || '').split('\n').map((line) => line.trim()).filter(Boolean);
            if (!filesRaw.length) {
              core.info('No files recorded for clean summary; skipping comment.');
              return;
            }

      - name: Upsert safe sweep file summary comment
        if: steps.guard.outputs.skip != 'true' && steps.build_comment.outputs.should-post == 'true' && steps.clean_mode.outputs.enabled != 'true' && steps.fix_results.outputs.changed == 'true'
        uses: actions/github-script@v8
        env:
          PR_NUMBER: ${{ inputs.pr_number }}
          FILE_LIST: ${{ steps.fix_results.outputs.file_list }}
        with:
          script: |
            const prNumber = Number(process.env.PR_NUMBER || context.payload.pull_request?.number || 0);
            if (!prNumber) {
              core.info('No pull request number available; skipping safe sweep summary comment.');
              return;
            }
            const fs = require('fs');
            const retryHelperPath = './.github/scripts/github-api-with-retry.js';
            const retryHelpers = fs.existsSync(retryHelperPath)
              ? require(retryHelperPath)
              : {
                  withRetry: (fn) => fn(),
                  paginateWithRetry: (githubInstance, method, params) =>
                    githubInstance.paginate(method, params),
                };
            const { withRetry, paginateWithRetry } = retryHelpers;
            const marker = '<!-- autofix-sweep-summary -->';
            const filesRaw = (process.env.FILE_LIST || '').split('\n').map((line) => line.trim()).filter(Boolean);
            if (!filesRaw.length) {
              core.info('No files recorded for safe sweep summary; skipping comment.');
              return;
            }
```

Notes:
- `build-pr-comment` already writes `autofix_pr_comment.meta.json` and exposes `should-post` as an output.
- The added `if:` conditions prevent comment creation when there are no diagnostics to report.
