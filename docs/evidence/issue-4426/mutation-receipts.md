# Issue #4426 deliberate-break receipts

Checked 2026-11-06T19:13:08Z. Machine-readable output is
`mutation-receipts.json`. Each row is one pytest process against one
mutation of the named production symbol. The mutation was then removed and
the same command was run again. Both production files match the restored
SHA-256 below. This record does not replace the original about 180
uncovered-statement-and-branch rule.

Command, with the node id substituted:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q <nodeid> -m "not slow" --tb=line -p no:cacheprovider
```

Every focused command finished in under two seconds. Red exit 1 is the
mutant. Green exit 0 is the restored source.

## Restored source

| File | Restored SHA-256 |
| --- | --- |
| `scripts/langchain/pr_verifier.py` | `bf7a8b0c238ee3720f6bb90fcec82eab0b30ffe534b429ad62969ce310602886` |
| `scripts/langchain/verifier_config.py` | `18d6a89ee9894496342d22385fae79019d36a4f5ca67940b9b44c49d43d22ff7` |

## `expanded_comparison_verdict`

These are the 13 tests in
`tests/scripts/test_pr_verifier_expanded_comparison_verdict.py`.

| Receipt | Named failure | Result |
| --- | --- | --- |
| `semantic-non-dict` | `assert 'PASS' == 'CONCERNS'` at line 71 | red exit 1, green exit 0 |
| `semantic-bad-signature` | `assert 'FAIL' == 'CONCERNS'` at line 86 | red exit 1, green exit 0 |
| `semantic-unreadable-key` | `IsADirectoryError: [Errno 21] Is a directory` | red exit 1, green exit 0 |
| `semantic-admission-allowlist` | `assert 'UNVERIFIABLE_INPUT' == 'CONCERNS'` at line 111 | red exit 1, green exit 0 |
| `semantic-signed-verdict` | `assert 'CONCERNS' == 'FAIL'` at line 129 | red exit 1, green exit 0 |
| `legacy-two-providers` | `assert 'PASS' == 'CONCERNS'` at line 137 | red exit 1, green exit 0 |
| `legacy-results-shape` | `assert 'PASS' == 'CONCERNS'` at line 146 | red exit 1, green exit 0 |
| `legacy-both-judges` | `assert 'CONCERNS' == 'PASS'` at line 158 | red exit 1, green exit 0 |
| `configured-fail` | `assert 'CONCERNS' == 'FAIL'` at line 177 | red exit 1, green exit 0 |
| `impersonation-guard` | `assert 'FAIL' == 'CONCERNS'` at line 201 | red exit 1, green exit 0 |
| `concerns-block-pass` | `assert 'PASS' == 'CONCERNS'` at line 227 | red exit 1, green exit 0 |
| `unverifiable-both-slots` | `assert 'CONCERNS' == 'UNVERIFIABLE_INPUT'` at line 248 | red exit 1, green exit 0 |
| `model-overrides` | `assert 'CONCERNS' == 'PASS'` at line 256 | red exit 1, green exit 0 |

`semantic-unreadable-key` removes the `OSError`/`ValueError` handler in
`expanded_comparison_verdict`. The test points `VERIFIER_SEMANTIC_KEY_PATH`
at a directory, so the named failure is `IsADirectoryError` rather than an
assertion message.

## Landed `verifier_config.py` tests

PR #4000 landed three tests. Its body describes the coercion break only, and
it does not keep stdout or exit codes. PR #4405 cites
`/tmp/3998-mutation-transcript.txt` on the repair runner. That file is not in
this clone and is not a GitHub Actions artifact. Gate run 39003191738 has no
downloadable artifacts. The rows below are new local runs of those landed
tests, including nested-list handling, payload handling, artifact coercion,
and duplicate-verdict parsing.

| Receipt | Symbol | Named failure | Result |
| --- | --- | --- | --- |
| `nested-list` | `is_terminal_artifact` | `test_verifier_config.py:139` `assert False` on the nested verdict list | red exit 1, green exit 0 |
| `nested-payload` | `is_terminal_artifact` | `test_verifier_config.py:142` `assert False` on the payload dict | red exit 1, green exit 0 |
| `artifact-coercion` | `_coerce_artifact` | `test_verifier_config.py:154` `assert False` on `Dumpable()` | red exit 1, green exit 0 |
| `duplicate-verdicts` | `artifact_from_verification_text` | `assert 'PASS' == 'FAIL'` at `test_verifier_config.py:162` | red exit 1, green exit 0 |

`nested-list` and `nested-payload` exercise the same test. They fail on
different assertions: line 139 is the list of terminal artifacts, and line
142 is the nested payload. The duplicate-verdict mutant changes `max` to
`min`, so PASS outranks FAIL.
