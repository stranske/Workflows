# PR #3520 deliberate-break evidence disposition

Issue [#3533](https://github.com/stranske/Workflows/issues/3533) records that merged
PR [#3520](https://github.com/stranske/Workflows/pull/3520) did not preserve the
deliberate-break transcript required by source issue
[#3392](https://github.com/stranske/Workflows/issues/3392). The original PR head was
`2572f4010a3371f845b519ebe3f548cb58d7ee38`, and the squash merge was
`494c3b101dfcb192b23a62c3fac335b054649676`.

## Historical record

The PR body and comments hold the named-test requirement, the green Gate, a substitute
advisory review approving the exact head, and the post-merge provider comparison report
(PASS). They do not hold the intentional-failure and restored-pass console output that
#3392 requires. That output cannot be presented as captured during PR #3520 without
inventing historical evidence.

## Current reproduction

The gate is still reproducible on `main`. On 2026-09-27, at base commit `c716e2b7b`, the
`HAS_CURSOR_AUTH` line was temporarily deleted from the `Evaluate keepalive state` step's
`env:` in `templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml`, as
#3392 specifies. No test or other product file was changed.

Command:

```text
python -m pytest tests/workflows/test_keepalive_workflow.py::test_evaluate_steps_export_every_provider_flag_the_loop_reads -q
```

Captured failure while the flag was deleted (tail of the unmodified pytest output):

```text
            evaluate_steps = [
                step
                for job in workflow["jobs"].values()
                for step in job.get("steps", [])
                if "evaluateKeepaliveLoop(" in str((step.get("with") or {}).get("script", ""))
            ]
            assert len(evaluate_steps) == 1, (
                f"{workflow_path.relative_to(REPO_ROOT)} must contain exactly one "
                "evaluateKeepaliveLoop step"
            )
            exported_flags = set((evaluate_steps[0].get("env") or {}).keys())
>           assert required_flags <= exported_flags, (
                f"{workflow_path.relative_to(REPO_ROOT)} is missing provider flags: "
                f"{sorted(required_flags - exported_flags)}"
            )
E           AssertionError: templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml is missing provider flags: ['HAS_CURSOR_AUTH']
E           assert {'HAS_CLAUDE_..._GEMINI_AUTH'} <= {'HAS_CLAUDE_...E_RETRY', ...}
E             
E             Extra items in the left set:
E             'HAS_CURSOR_AUTH'

tests/workflows/test_keepalive_workflow.py:199: AssertionError
=========================== short test summary info ============================
FAILED tests/workflows/test_keepalive_workflow.py::test_evaluate_steps_export_every_provider_flag_the_loop_reads
1 failed in 0.33s
```

The failure names the file and the missing flag, as #3392 requires. The line was then
restored with no remaining diff, and the exact command passed:

```text
.                                                                        [100%]
1 passed in 0.35s
```

The full focused file also passed after the restore:

```text
python -m pytest tests/workflows/test_keepalive_workflow.py -q
.......................                                                  [100%]
23 passed in 1.78s
```

This is a current, reproducible fail-to-pass proof for the same named gate. It closes the
durable evidence gap without claiming the output was captured during the historical PR #3520
run.
