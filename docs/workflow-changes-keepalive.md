# Keepalive Workflow Suppression Guard

This note documents the YAML changes required to **suppress progress-review comments** when the
`review_result.json` payload is missing or empty. The guard uses
`.github/scripts/should-post-review.js`, which writes `should_post_review` to `$GITHUB_OUTPUT`.

## YAML change (insert after `Run progress review`)

```yaml
      - name: Decide whether to post progress review
        id: review_gate
        run: node .github/scripts/should-post-review.js review_result.json

      - name: Post review feedback to PR
        if: steps.review_gate.outputs.should_post_review == 'true'
        uses: actions/github-script@v8
        env:
          REVIEW_FEEDBACK: ${{ steps.review.outputs.feedback }}
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const prNumber = Number('${{ needs.evaluate.outputs.pr_number }}');
            const recommendation = '${{ steps.review.outputs.recommendation }}';
            const alignmentScore = '${{ steps.review.outputs.alignment_score }}';
            const rounds = '${{ needs.evaluate.outputs.rounds_without_task_completion }}';
            const feedback = process.env.REVIEW_FEEDBACK || '';
            const { createTokenAwareRetry } = require('./.github/scripts/github-api-with-retry.js');
            const { github: retryGithub, withRetry } = await createTokenAwareRetry({
              github,
              core,
              env: process.env,
              task: 'keepalive-loop',
              capabilities: ['issues:write'],
            });

            const emojiMap = {
              'CONTINUE': '✅',
              'REDIRECT': '⚠️',
              'STOP': '🛑'
            };
            const emoji = emojiMap[recommendation] || '❓';

            const body = [
              `## ${emoji} Progress Review (Round ${rounds})`,
              '',
              `**Recommendation:** ${recommendation}`,
              `**Alignment Score:** ${alignmentScore}/10`,
              '',
              '### Feedback',
              feedback || 'No specific feedback.',
              '',
              '---',
              `_This review was triggered because the agent has been working for ${rounds} ` +
                `rounds without completing any task checkboxes._`,
              '_The review evaluates whether recent work is advancing toward ' +
                'the acceptance criteria._',
            ].join('\n');

            await withRetry((client) =>
              client.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: prNumber,
                body,
              })
            );
```

Notes:
- The guard runs even if `review_result.json` is missing; the script returns `false` in that case.
- The `if:` check ensures the comment step is skipped when there is no actionable review.
