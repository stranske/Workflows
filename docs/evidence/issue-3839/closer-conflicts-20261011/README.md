# Existing PR3841 conflict recovery

Original ecf00747704492cedb4ca549136c3e67cc48cf3e: 56 existing resolver tests fail at YAML parsing (raw log retained). Resolve committed conflict markers in both reporter workflows and pair.12. Preserve current main skip reasons and branch unresolved-error outcomes together. Consumer scenarios now load the consumer helper. Skip grants no PR binding; genuine lookup/input failures still produce diagnostics and failure. No permission, token, dispatch or authority changes.

Validation: 89 focused Python tests PASS; 29 Node applicability tests PASS; all root and consumer workflow YAML parse; actionlint PASS with external shellcheck/pyflakes disabled; normalized drift checker, Black, Ruff and diff checks PASS. Original parse RED is not a deliberate behavioral mutation proof. Hosted full topology, exact-head review threads, seven-minute floor and post-merge comparison remain required. Source3839 stays open.
