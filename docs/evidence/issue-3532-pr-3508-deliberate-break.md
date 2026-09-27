# PR #3508 deliberate-break evidence disposition

Issue [#3532](https://github.com/stranske/Workflows/issues/3532) records that merged
PR [#3508](https://github.com/stranske/Workflows/pull/3508) did not preserve the
deliberate-break transcript required by source issue
[#3370](https://github.com/stranske/Workflows/issues/3370). The original PR head was
`8c8a421902d29584aa9fcf625a9c6f3835d9fb78`, and the squash merge was
`688a9835467da23dc77b209ea2e183b59f4a8856`.

## Historical record

The PR body and comments contain the named test requirement, the final successful Gate and
test contexts, and the post-merge provider report, but they do not contain the intentional
failure and restored-pass console output. The complete GraphQL review-thread page reports
`hasNextPage: false` and zero active non-outdated unresolved threads. The missing transcript
cannot be represented as output captured during PR #3508 without inventing historical
evidence.

## Current reproduction

The gate remains reproducible on `main`. On 2026-09-27, at base commit
`c9c523461`, the heading `## Blocked Without Redesign` was temporarily renamed in
`templates/consumer-repo/docs/TARGET_WORK_ENVIRONMENT.md`. No product or test assertion was
changed.

Command:

```text
python -m pytest tests/workflows/test_target_work_environment_template.py::test_template_documents_hosting_block -q
```

Raw captured failure while the heading was renamed (unmodified pytest output):

```text
F                                                                        [100%]
=================================== FAILURES ===================================
____________________ test_template_documents_hosting_block _____________________

    def test_template_documents_hosting_block() -> None:
        text = TEMPLATE_DOC.read_text(encoding="utf-8")

>       assert "## Blocked Without Redesign" in text
E       AssertionError: assert '## Blocked Without Redesign' in '# Target Work Environment\n\nRead this before proposing a delivery shape for a fleet consumer. These constraints desc...https://github.com/stranske/Ready/blob/main/research-program/artifacts/work-bundle/INFORMATION-REQUEST-RESPONSE.md).\n'

tests/workflows/test_target_work_environment_template.py:15: AssertionError
=========================== short test summary info ============================
FAILED tests/workflows/test_target_work_environment_template.py::test_template_documents_hosting_block
1 failed in 0.28s
```

The original heading was then restored with no residual diff. The exact command passed:

```text
.                                                                        [100%]
1 passed in 0.19s
```

The full focused file also passed after restoration:

```text
python -m pytest tests/workflows/test_target_work_environment_template.py -q
....                                                                     [100%]
4 passed in 0.27s
```

This is a current, reproducible fail-to-pass proof for the same named gate. It closes the
durable evidence gap without claiming that the output was captured during the historical PR
#3508 implementation run.
