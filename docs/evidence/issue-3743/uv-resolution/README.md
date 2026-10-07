# Failed uv executable lookup coverage

Related to Workflows issue 3743. This is the next bounded chunk after PR 3814, whose independent closer acceptance permits continuation while its provider compare CONCERNS remain recorded. The umbrella repository-wide 90% goal is incomplete and full-repository coverage is UNKNOWN here.

## Behavior and scope

Eight root/template cases run a private executable named `uv` as a real subprocess. They verify that a nonzero lookup with plausible stdout, or a successful lookup with whitespace-only stdout, cannot create a PyYAML probe. Both the initial `which pytest` and nested shebang `which python3` boundaries are exercised. The exact lookup arguments, working directory and absence of additional launches are asserted. This is a subprocess boundary test, not an integration claim about an installed uv distribution. Neither production helper changes; both retain SHA256 `cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`.

Selection uses the latest 400 scripts-touching commits at base `0543a3f2712e08a83ed2f4eb40e3b72fd06ef14f`. The helper ranks first: 73 repair-subject matches / 82 touches, ahead of pr_verifier 30/36 and runner core 27/37. This is a transparent repair-history proxy, not a count of proven escaped defects. Exact history and interpretation are retained in ranking-history.txt and selection.json.

## Observed validation

- Identical seven-file baseline suite: 300 PASS; adding this one test module: 308 PASS. Exactly eight added nodes; all prior outcomes remain PASS.
- Same 591 statements, 262 branches, zero exclusions. Covered lines 568 → 570 and covered branches 241 → 243. Combined focused helper coverage 94.84% → 95.31%; statement coverage 96.11% → 96.45%; branch coverage 91.98% → 92.75%. New lines 680/685 and arcs 679→680 / 684→685. No previously covered line or branch disappears.
- Eight individual production guard mutations, one per new root/template node: each named test RED exit 1 while the guard is broken, then GREEN exit 0 after exact restoration. The private replay never mutates caller files. JUnit verifies one executed failure for RED and one executed pass for GREEN; collection errors/skips do not count.
- Whole-tree Black: 679 files unchanged. Focused Ruff PASS; template completeness PASS; git diff --check PASS.

## Replay and retained evidence

From repository root, using an environment with pytest, pytest-cov and defusedxml:

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break_uv_resolution.py -q -o addopts=
python3 docs/evidence/issue-3743/uv-resolution/replay_uv_resolution.py --output /tmp/uv-resolution-fresh-proof
```

The replay refuses an existing output directory. `validation.tar.gz` retains baseline/candidate exact argv, raw logs, JUnit and coverage JSON; all sixteen RED/GREEN command receipts/logs/JUnit files; and mutation/source/test/driver identities. `archive-index.json` binds every one of its 61 members by size and SHA256 plus the archive SHA256. `comparison.json` binds the matched outcome/coverage comparison and eight added test nodes. Extract the archive into a fresh directory to inspect or rerun the exact baseline/candidate argv from the two command JSON files. The baseline omits only the new module; production bytes and prior seven test files are identical.

Hosted Gate/check topology and provider verifier disposition remain separate acceptance gates. This chunk does not authorize merge, certify repository-wide 90%, or close source 3743.
