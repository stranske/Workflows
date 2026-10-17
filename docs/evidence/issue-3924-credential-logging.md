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

## Generic quoted/assignment/header syntax correction

The independent packet expanded to bare pwd/auth/credentials fields, which were not covered by the intermediate token/secret spelling correction. Message text is now rejected if it contains quoting, assignment, or header delimiters, regardless of field spelling, in addition to credential-keyword suppression. Plain benign Resource not accessible by integration, HTTP403/type metadata, the200character bound, failclosed dispatch and recursive-decoder controls remain unchanged. This deliberately suppresses structured/freeform diagnostic detail rather than trying to parse an unknown opaque value boundary; arbitrary unlabeled plain-text secrets remain unrecognizable and are not claimed universally detectable.

Five added actual-logger cases cover pwd,auth,credentials,an unrecognized_field assignment,and a standalone quoted opaque value. Removing only the syntax-rejection prefix yields5FAIL/11PASS,exit1; byte-identical restoration yields211modulePASS,exit0. Original/restored coreSHA256 e9f4bdfc78c9adcb33ce65ed95185a14ccf06e7c09c12fcbda817ccafe8fdc33. Earlier stage receipts are historical, not current-head acceptance. Fresh changed-head advisory review, CI/topology/thread/floor remain required.

## Plain and compound credential-marker correction

Current-head review identified actual leaks for bare pwd/auth/credentials. The independent37-case helper/logger sweep identified9unquoted opaque-value leaks, including singular credential and apiToken/authToken/auth_token/session_token/sessionToken. These are real original-redaction gaps. The owner clarified that the prior delivery-only assumption is not a hold or withdrawal of the standing finite source authorization.

Marker matching now deliberately covers marker substrings across plain,camel-case,prefixed and underscore identifiers, including pwd/auth/credential families, without regex word-boundary escapes. Generic quoted/assignment/header suppression is retained as the conservative owner-approved trade-off; punctuation-bearing benign detail may be omitted while the original exact benign integration-refusal diagnostic remains. No fallback,dispatch,log-format or output-bound change.

All37parent helper+actual-logger cases pass before push against candidate coreblob2a3735cc1d7034464909fd643e4829abb0d203fb. Tests use opaqueVALUE123ONLY, not a recognizable token pattern that could mask a field leak. Observable dispatch/logger unit coverage now includes42plain/compound field cases (the whole parent plain-marker matrix plus additional prefix/suffix/underscore forms). Final full module253PASS. Removing only the production message-suppression guard produces42named assertion failures,exit1; byte-identical restore returns253PASS,exit0. Raw named JUnit/console and argv captured in the automation final-delivery-3961 evidence. Original/restored coreSHA256 2a6d889d1229f6485146b8dcb9f476a1ad5d981ddfbceec1a8820749e7eadf36. Black/Ruff/diff checks pass. Prior26d74 and earlier advisory/safety packets do not establish this changed head; renewed review and complete new-head CI/topology/threads/floor remain mandatory.
