# Matched-comparison raw-input regression validation

Check date: 2026-11-06T19:53:52.452357+00:00
Inspected commit: `fb7e532ed89c5e2d514dd30c4844fc83d2c86e96`
Actual interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3`
cwd: `/home/runner/work/Workflows/Workflows`

This test-only increment adds seventeen raw-input regression cases to
`tests/scripts/test_shebang_rejection_matched_comparison.py`. The twenty-four
comparison tests verify command drift rejection and coverage faults separately
for the root and template helpers. The first full-repository Black attempt timed out after 180 seconds with one
worker. A two-worker retry was rejected by the sandbox multiprocessing socket
restriction. Individual checks of all 927 files using the repository configuration
then populated Black's ordinary cache; the required full-repository command
passes using that cache. Concurrent cache writes lost 243 entries; a 120-second attempt
stalled on those misses. Serial checks retained the missing entries before
the final successful full-repository run. Every individual command, exit and console
is retained in `black-individual-checks.json.gz` and `black-cache-fill.json.gz`; no formatting check was disabled or skipped.
Raw JUnit and focused comparison-module
coverage output are retained here. No percentage target is claimed.

The literal Anaconda command attempts both exit 127 in this runner. The focused
installed-interpreter command confirms eight passes but does not satisfy those
literal commands. `/tmp/fresh-shebang-rejection-proof` remains uncreated.
The stop rule is one attempt per literal command and 120 seconds per focused
command; no substitute interpreter is installed at the required path.

Existing `acceptance-run/` receipts describe a prior successful Anaconda run;
`matched-comparison/` retains the earlier 340/348 comparison. All pre-existing
evidence files and archives are unchanged and their bindings still verify.
This run tests rejection of altered copies of those raw inputs. It does not
claim a fresh baseline/candidate execution or a fresh Anaconda mutation replay.

Measured validation file counts: {"black_files": 927, "manifest_workflow_targets": 35, "ruff_files": 15, "strict_validation_inputs": 166, "template_directory_yml": 35, "workflows_directory_yml": 130}.
`input-bindings.json` records the source, test, replay and raw receipt hashes.
`preserved-inputs.json` records every pre-existing evidence file's hash/length.
`proof.tar.gz` retains these receipts losslessly with `manifest.json`; its hash
and member count are recorded in the external `summary.json`.

The canonical checkout has a read-only `.git`: staging failed because
`.git/index.lock` could not be created. The validated payload is committed in
`/tmp/shebang-rejection-reviewed-checkout`; a portable patch and Git bundle
are exported under `/tmp` for transfer into a writable checkout.
