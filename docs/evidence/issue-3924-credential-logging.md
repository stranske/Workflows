# Source3924 credential-bearing storage diagnostics

Owner-directed finite correction on existing PR3961. Release3944 remains with its original steward.

The logger previously printed unprefixed password/client_secret values and spaced x-access-token values from an untrusted API message. It now discards the complete message when it names credential-bearing fields; HTTP status/error type remain. This deliberately avoids guessing where quoted, spaced or multiword values end. Existing known-token/URL redaction, 200-character limit, malformed/nested JSON handling, and authoritative-storage fail-closed routing remain unchanged.

Actual execution with `/opt/anaconda3/bin/python3`:

- Before repair: `python -m pytest tests/scripts/test_runner_lib.py -q -k discards_credential_fields`: 9 assertion failures, exit1. Synthetic values only.
- After repair: `python -m pytest tests/scripts/test_runner_lib.py -q`: 204 passed, exit0, including original HTTP-message and nested-decoder tests.
- Causal mutation: remove only the two-line `_STORAGE_FAILURE_CREDENTIAL_FIELD_RE.search(message)` return guard, run the same new cases: 9 assertion failures, exit1. Restore original source bytes and rerun full module: 204 passed, exit0.
- Original/restored core SHA256: `0095a0947228626d17114e1e22e25b848a072586eed77c7bdd4ca5b4732b3931`.
- Changed-file Black, Ruff and git diff --check pass.

Each new case exercises `should_dispatch` through the actual `_log_storage_failure`, verifies `authoritative-storage-unavailable`, no dispatch, no synthetic secret or http_message/URL output, HTTP403 retained, and no fallback records. Cases include password assignments, quoted uppercase password, client_secret and client secret, x-access-token with whitespace/multiword value, and Basic authorization.

The shared source is `scripts/runner_lib/`, already mapped by `.github/sync-manifest.yml`; there is no separate template core to diverge. Distribution itself and release refresh are separate obligations. This local evidence is neither hosted CI nor provider PASS. Exact-head CI/topology, independent review, review threads and seven-minute floor remain mandatory before squash merge.

## Material opaque-field correction

Independent actual logger evidence on prior head58da7b260110d15f9b5645425438723b54d2fc61 found bare token and secret assignments still leaking synthetic opaque values. That head and its advisory approval are superseded for source delivery. Generic token/secret field names are now included in the conservative message-discard predicate. This intentionally suppresses messages mentioning credential fields rather than parsing or printing any part of their unknown values.

Added actual dispatch/logger cases with token="synthetic-private-value" and secret="synthetic-private-value": old implementation2FAIL/9PASS,exit1; correction206modulePASS,exit0. Removing only generic token|secret alternatives reproduces2FAIL/9PASS,exit1; exact source restoration returns206PASS,exit0. Original/restored coreSHA256 70b1a24defa865fd17007550d82e415e98018dd5b0e8471070554e1bb6c59131. The module also retains original benign403/status, bounds, failclosed and RecursionError controls. Black/Ruff/diff checks pass. Independent current-head review and full hosted gates/floor remain required; prior head CI is not new-head evidence.
