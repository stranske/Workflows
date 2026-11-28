# Comparison receipt identity recovery

At PR3800 head d9ff67be44dc68f5932ea1179c672be7e3b22b7d the helper accepted a bundle with manifest source_run_id39999999999 under requested run123, and permitted a follow-up for another repository/PR. These summaries could misattribute provider results when used by the receiving steward.

The helper now rejects conflicting run IDs in the manifest, corpus decision or terminal disposition, requires at least one recorded run binding, rejects conflicting target fields, binds both summaries to Workflows#3769, and rejects a zero follow-up run ID. This validates declared identity consistency; it does not authenticate file contents or replace the independent live artifact/topology gates.

Command: `/opt/anaconda3/bin/python3 -m pytest tests/tools/test_verifier_compare_run_receipt.py -q`.
Six new regression cases: original helper6FAILED/7PASSED (exit1); repaired helper13PASSED (exit0). The [original validation logs](#recover-the-original-validation-logs) retain the console output. Focused source-context/verifier-builder suites185PASSED; Black/Ruff/diff checks passed. No live verifier dispatch or original-verdict relabeling.

## Current-head continuation8352ee67

Keepalive added actual follow-up capture and a source-repair guard. Hosted lint37567819697/job112619513057 fails SIM103 in that new function. Independently, missing or unavailable acceptance-source discovery passed the new repair guard. Four actual negative controls failed before repair; after requiring explicit required=false plus included/not_required status, all20receipt tests pass. The same edit fixes the exact SIM103 condition. The same packet records the full repository Ruff and Black results. Original provider/campaign verdicts remain unchanged; the receipt is still not independent deployment or source3757topology acceptance.

## Recover the original validation logs

The [original identity and discovery packet](https://github.com/stranske/Workflows/tree/8e7fcfd78bfe1d22547dc0a17b3edb14a1d0b9e6/docs/evidence/issue-3770/post-merge-compare/identity-recovery)
contains all six console captures and the contemporaneous README. Recover their
original repository-relative paths from a Workflows checkout.

```bash
(
  set -e
  revision=8e7fcfd78bfe1d22547dc0a17b3edb14a1d0b9e6
  directory=docs/evidence/issue-3770/post-merge-compare/identity-recovery
  if ! git cat-file -e "$revision^{commit}" 2>/dev/null; then
    git fetch --no-tags --depth=1 origin "$revision"
  fi
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/issue-3770-evidence.XXXXXX")
  git archive --output="$recovered/evidence.tar" "$revision" -- "$directory"
  tar -xf "$recovered/evidence.tar" -C "$recovered"
  rm "$recovered/evidence.tar"
  printf '%s\n' "$recovered"
)
```
