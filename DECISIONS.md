# Decisions

## 2026-02-07 - PR #1307 Missing Verification Artifacts
Decision: Document the missing verification artifacts as a high-severity concern and require a
re-verification run before any additional code-level actions are taken.

Rationale: The repository does not contain the verifier context or extracted concerns needed to
review acceptance criteria. Without those artifacts, any remediation would be speculative.

Evidence: [Evidence: PR #1307 missing artifacts](docs/reverification/1307-missing-artifacts.md)

## 2026-02-07 - PR #1304 Ledger Hygiene
Decision: Treat the ledger clean-up as documentation-only work; no new runtime tests are required
to verify the removal of placeholder entries.

Rationale: The change updates `.agents/issue-1313-ledger.yml` to reference real repository paths and
concerns, which is a metadata correction rather than executable behavior.

## 2026-02-07 - PR #1304 Auth Coverage Baseline
Decision: Record the post-test coverage for auth-related modules after adding null-handling and
authentication scenario tests: `scripts/api_client.py` at 56.64% and `scripts/cli_handler.py` at
73.04%.

Rationale: Both modules are below the 80% target. Follow-up coverage improvements should add
targeted unit tests for API retry/error branches in `scripts/api_client.py` and for CLI issue
selection and scope-check branches in `scripts/cli_handler.py`.

## 2026-02-07 - Auth Coverage Baseline (PR #1325 Follow-Up)
Decision: Record the auth coverage baseline as a reproducible command instead of a committed
generated artifact. Recreate the historical output with
`pytest tests/test_auth_validator.py tests/test_authentication.py --cov=scripts.auth_validator --cov=scripts.api_client --cov-report=term-missing -m "not slow"`.

Rationale: The command captures the exact test selection and coverage targets for
`scripts/auth_validator.py` and `scripts/api_client.py`. Generated coverage output should be
recreated when needed rather than kept as root-level repository debris.

<a id="auth-coverage-artifact-2026-02-08"></a>
## 2026-02-08 - Auth Coverage Baseline (PR #1334 Follow-Up)
Decision: Record the updated auth coverage baseline as a reproducible command instead of a
committed generated artifact. Recreate the historical output with
`pytest tests/test_auth_validator.py tests/scripts/test_issue_dedup_smoke.py -k "fetch_oauth_scopes or validate_auth_payload" --cov=scripts.auth_validator --cov=scripts.api_client --cov-report=term-missing -m "not slow"`.

Rationale: The command preserves the exact test selection and coverage targets for
`scripts/auth_validator.py` and `scripts/api_client.py` after the validation and scope-fetching
separation changes. Generated coverage output should be recreated when needed rather than kept as
root-level repository debris.
