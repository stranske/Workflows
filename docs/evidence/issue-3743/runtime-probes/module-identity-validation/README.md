# Runtime replay module identity validation

The replay validator previously accepted a JUnit case from another module when
its test name and outcome matched the requested case. It now requires the
pytest module classname derived from the selected node's file path as well.
The new regression exercises both RED and GREEN receipt rejection. The existing
three validator tests now provide their module identity in synthetic reports.

`module-control.json` records the real validator mutation and byte-identical
restoration: disabling the module comparison makes the new regression fail
(exit 1), and restoration makes it pass (exit 0). Separate command receipts,
raw console streams and JUnit retain both phases. The driver suite passes four
cases. This fixes a receipt-validation defect; the distributed runtime helper
bytes remain equal to each other and to selected base `98b6ed3d`.

The full replay used a new directory under `/tmp/unique-runtime-probe-proof-*`.
All fourteen named production decisions were broken and restored separately.
Every RED phase exited 1 with one executed test failure; every GREEN phase
exited 0 with one pass. Every original/restored source hash matches. The retained
copy in `replay/` preserves actual argv, cwd and temporary output paths, plus
unabridged console/JUnit embedded in `controls.json`.

Each `*.command.json` records the actual argv, cwd, observed exit, and byte count
and SHA-256 digest of decoded stdout/stderr. Raw streams and failure JUnit are
losslessly gzip-compressed to preserve pytest diagnostics without introducing
trailing-whitespace diff errors. Production phase XML is also compressed; the
matched coverage JSON and successful suite JUnit remain plaintext.

`source-provenance.json` compares both production copies and the four baseline
test files against the selected base. The baseline and candidate commands use
identical coverage settings and differ only in the additional runtime-probe
file and output destinations. `comparison.json` checks test counts, coverage
universes and covered sets. These are focused helper measurements.

Multi-file Black cannot start its process pool in this sandbox. The retained
serial Black source-discovery runner performs the same AST-safe formatting
checks and populates a writable cache, after which the required unmodified
repository Black command checks that cache. Focused Black, Ruff, template sync,
completeness, and diff outputs are retained separately.

`task-reconciliation.md` reconciles the previously stale seven PR checkboxes.
Automatic approval review rejected the remote PR-body update because the run's
approval policy is `never`. No remote checkbox update is claimed.
