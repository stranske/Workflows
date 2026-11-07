# Delivered archive inventory validation

Check date: 2026-11-06. Inspected commit: `22714ae7987ba087336c6babf0801d176edb6252`.
Actual interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`. Commands and raw console are in
`checks.json`, `ruff-final.json`, `black.json`, and `black-final.json`; raw JUnit
is retained in the XML files. The first Ruff result identified a set-comparison
style issue; the final receipt records the corrected test passing.

The existing verifier's curated list covered five of six pre-existing archives.
The new test discovers every delivered archive, checks every member hash/length
and current loose receipt, and verifies current input bindings against the tree.
The first inventory run verifies all six pre-existing archives; this directory's
new archive also participates in subsequent runs. The final inventory run verifies
all seven archives, including this package; `inventory-final.xml` and
`inventory-final.json` retain its seven-pass result. The three original archives
remain historical receipts whose inputs need not equal current source bytes.
All pre-existing evidence files are unchanged, including the archived matched
comparison and eight-case command/replay receipts. Production helpers equal
each other and origin/main. `preservation.json` records the measured inventory
digest and production hashes; `input-bindings.json` binds this test and inputs.

Current installed-interpreter validation: eight focused passes, six initial
inventory passes, and 76 companion passes, with no errors or skips. The companion
suite includes a real eight-pair mutation replay and output-reuse preservation.
The literal Anaconda commands both stop with exit 127 because that interpreter
is absent. Prior `acceptance-run/` records a successful Anaconda execution; this
run does not constitute a fresh successful execution of those literal commands.
The stop rule is one attempt per literal command and 120 seconds per focused run.

Measured validation file counts: {"black_files": 928, "manifest_workflow_targets": 35, "ruff_files": 16, "strict_validation_inputs": 166, "template_directory_yml": 35, "workflows_directory_yml": 130}.
The uncached Black command timed out; serial real Black checks populated its
ordinary cache before the required full-repository command passed. Every serial
invocation is retained losslessly in `black-serial.json.gz`; no check was skipped.

Task reconciliation: the existing PR body already checks all tasks complete.
The discovered inventory gap is now covered by executable tests. Updating PR
metadata was rejected because the GitHub tool requires approval and the run's
policy is `never`; no new remote task or criterion checkmarks were applied.
PR #4472 was verified open and ready for review. The canonical `.git` is read-only;
the tested change is committed in `/tmp/shebang-inventory-commit` with a portable
bundle and patch under `/tmp` for handoff.
