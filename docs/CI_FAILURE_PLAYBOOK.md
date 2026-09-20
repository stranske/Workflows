# CI Failure Playbook

This shared playbook is distributed by the Workflows sync manifest. Use the
exact failed job and PR head when diagnosing a failure; a green controller run
does not mean its delivery or tests passed.
The Gate triage summary links to this playbook in the repository producing
the failure, using the diagnosed PR head SHA when available and `main` only
when no valid head is supplied. External playbook URLs remain unchanged.

## Type Errors

Read the reported mypy file, line and error code. Reproduce with the repository's
configured type-check command. Correct the type contract or narrowing rather
than suppressing the check. If the file is managed by Workflows, repair its
source there and regenerate the consumer delivery.

## Test Failures

Read the first real assertion or exception in the failed pytest job and run
the named test with the same configuration. Fix the implementation when the
assertion expresses the intended contract. Change expectations only when the
contract intentionally changes; retain a regression test. Rerun relevant
tests and required CI on the new exact head.

## Coverage Failures

Inspect the coverage report and the repository's configured required threshold.
Add behavioral tests for missing branches or newly introduced code. Do not
lower thresholds or omit changed production files simply to clear the gate.
Use the same coverage configuration as the failed job.

## Import Errors

Check the missing import, installed distribution, optional dependency group,
and package/module path in the failed environment. Correct packaging or the
owning dependency declaration and validate a clean install. Do not add an
unrelated package merely because its name resembles the missing import.

## Syntax Errors

Use the reported file and line to reproduce the parser failure with the Python
version used by CI. Correct syntax or indentation and check supported Python
versions before running formatting, lint and focused tests. Do not remove
failing code or tests just to make parsing succeed.
