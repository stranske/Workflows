## Summary
- Fix `docs/runbooks/headless_ingest.md` quickstart so a fresh checkout stages PDF/XLSX bytes beside a trimmed bundle JSON (production `content_root` contract unchanged).
- Add `tests/docs/test_headless_ingest_runbook.py` with `test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout`.

Closes #1061

## Test plan
- [x] CI Gate runs `test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout`
- [x] Deliberate-break → revert on runbook text (per issue acceptance)

<!-- pr-preamble:start -->
<!-- meta:issue:1061 -->
> **Source:** Issue #1061

Closes #1061

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [x] Replace the quickstart in `docs/runbooks/headless_ingest.md:13-19` with a command that succeeds on a fresh checkout (either document the colocated-bytes layout with a minimal `mkdir`/`cp` example, or point at `tests.conftest.stage_headless_reference_bundle` / an equivalent one-liner).
- [x] Add `tests/docs/test_headless_ingest_runbook.py` that reads `docs/runbooks/headless_ingest.md`, extracts the documented shell command, runs it in a temp directory layout that matches the runbook text, and asserts exit code 0 plus `run.json` in `--out`.

#### Acceptance criteria
- [x] Named test: `test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout` asserting the runbook’s primary example command exits 0 and writes `run.json`.
- [x] Deliberate-break → revert: restore the broken `tests/fixtures/intake/pdf_primary_mixed_bundle.json`-only example in the runbook → confirm the named test FAILS → revert.

<!-- auto-status-summary:end -->

