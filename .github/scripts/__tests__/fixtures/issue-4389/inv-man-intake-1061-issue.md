## Why (verified evidence)

The headless ingest runbook documents a copy-paste quickstart that fails on the current tip with exit code 1. `docs/runbooks/headless_ingest.md:15-18` shows `inv-man-ingest tests/fixtures/intake/pdf_primary_mixed_bundle.json --out ./.run-out`, but production `run_pipeline` resolves document bytes only from the bundle JSON directory (`src/inv_man_intake/run.py:179` sets `content_root=bundle_path.parent`), while the repo ships those PDF/XLSX bytes under `tests/fixtures/extraction/` (`tests/conftest.py:47-49` copies from there when staging a working bundle). Running the documented command therefore raises `real document bytes not found for 'summit_arc_investment_update.pdf' at .../tests/fixtures/intake/summit_arc_investment_update.pdf`. An operator following the runbook cannot complete IMI-1 without discovering the unstaged layout requirement.

Reproduction:
```bash
cd /path/to/Inv-Man-Intake
inv-man-ingest tests/fixtures/intake/pdf_primary_mixed_bundle.json --out /tmp/imi-runbook-out
# exit 1; stderr contains real document bytes not found
```

## Tasks
- [ ] Replace the quickstart in `docs/runbooks/headless_ingest.md:13-19` with a command that succeeds on a fresh checkout (either document the colocated-bytes layout with a minimal `mkdir`/`cp` example, or point at `tests.conftest.stage_headless_reference_bundle` / an equivalent one-liner).
- [ ] Add `tests/docs/test_headless_ingest_runbook.py` that reads `docs/runbooks/headless_ingest.md`, extracts the documented shell command, runs it in a temp directory layout that matches the runbook text, and asserts exit code 0 plus `run.json` in `--out`.

## Acceptance Criteria
- Named test: `test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout` asserting the runbook’s primary example command exits 0 and writes `run.json`.
- Deliberate-break → revert: restore the broken `tests/fixtures/intake/pdf_primary_mixed_bundle.json`-only example in the runbook → confirm the named test FAILS → revert.

## Non-Goals
- Do NOT change production `content_root` resolution in `src/inv_man_intake/run.py` (colocated bytes remain the contract).
- Do NOT add a hosted API or change intake validation rules.
- No scaffolding / TODO-only changes; every task is a concrete edit verified by the gate above.

Reproduction:
```bash
inv-man-ingest tests/fixtures/intake/pdf_primary_mixed_bundle.json --out /tmp/imi-runbook-out
# expected: exit 0 and run.json (today: exit 1, bytes not found)
```

_Surfaced by Track D audit 2026-11-02; verified by running the runbook command on tip `2960e93cb0a1c1e1cb2917dcbd0e13e651ee62b5`._

