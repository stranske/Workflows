# Canary promotion validation evidence

The first task's evidence builder now rejects non-string `plan_id` values before
API calls, matching Maint 68's actual jq parser. Four regression cases failed on
the prior implementation: number, boolean, array, and object plan IDs. All four
pass with the fix, and the parser regression independently rejects those values.

## Deliberate-break proof

Temporarily removed only `plan_id: row.plan_id,` from
`buildCanaryPromotionEvidence` in `.github/scripts/maint71_merge_sync_prs.js`.
Ran:

```bash
node --test --test-isolation=none \
  --test-name-pattern='all canaries merged dispatch correct plan-bound evidence' \
  tests/scripts/test_maint71_promote_dispatch.js
```

Result: exit **1**, one executed test failed. The assertion names
`missing_key:plan_id` for each configured canary. Full output:
[missing-plan-id-red.txt](missing-plan-id-red.txt).

Restored the source byte-for-byte, then ran:

```bash
node --test --test-isolation=none tests/scripts/test_maint71_promote_dispatch.js
```

Result: exit **0**, **25 passed**, zero failed or skipped. Full output:
[restored-green.txt](restored-green.txt). Both outcomes are local execution
evidence; CI results remain unverified.

The explicit isolation option ensures individual tests execute and appear in the
output in this runner. Without it, the runner reported only a passing file wrapper.

## Related validation

```bash
node --test --test-isolation=none \
  .github/scripts/__tests__/maint71_promote_dispatch.test.js \
  .github/scripts/__tests__/maint71_merge_sync_prs.test.js \
  .github/scripts/__tests__/sync_pr_merge_contract.test.js
pytest tests/workflows/test_sync_delivery_liveness.py -m 'not slow' -q -o addopts=
```

Results: **127 JavaScript tests passed** (including the promotion tests loaded
through the CI wrapper) and **6 Python tests passed**.

## Live follow-up

`gh pr view --json number,url,state,isDraft,body,headRefName,baseRefName` failed
with `error connecting to api.github.com`. No PR state or checklist was changed.
Copy both deliberate-break outcomes above into the PR body when connectivity
returns. The acceptance criterion requiring PR-body evidence remains pending.

After merge, observe or dispatch one real exact-plan promotion using the
revalidated Maint 71 artifact, then record the successful run URL, verify
Doc-Lineage's default-branch `scripts/runner_lib/core.py` contains `"muse"`,
and verify the Maint 68 summary reports `plans sealed awaiting promotion: 0`.
These live acceptance criteria remain pending; local tests do not establish them.
