# Issue #4718 / PR #4726 — round 3 verification

Check date: 2026-11-16 America/Chicago (2026-11-17T04:18:14Z).
Verified implementation head: `91372fb376e41586451aa5edb78cb6c900bbeb1d`.

Outcome: the reusable workflow uses
`bot-comments-reusable-${{ github.repository }}-pr-${{ inputs.pr_number }}`
with `cancel-in-progress: false`. The named regression test parses the reusable
workflow and both caller YAMLs, checks repository/PR separation, and checks
distinct caller keys. T1 and T2 were already implemented; no source edit was
needed in this round.

The command that prints the acceptance outcome is:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest tests/workflows/test_bot_comment_handler.py::test_reusable_concurrency_group_is_scoped_to_target_pr -q
```

Results:

- Deliberately restored `${{ github.workflow }}-${{ github.ref }}` and
  `cancel-in-progress: true`: the named test failed at the group assertion,
  `1 failed in 0.15s`, exit 1.
- Restored the original workflow bytes: the named test passed,
  `1 passed in 0.15s`, exit 0.
- Ran `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest
  tests/workflows/test_bot_comment_handler.py -q`: `19 passed in 0.58s`, exit 0.
- `git diff --exit-code HEAD -- .github/workflows/reusable-bot-comment-handler.yml
  tests/workflows/test_bot_comment_handler.py` passed after restoration.

The initial invocation without plugin isolation stopped before test execution:
an installed pytest-asyncio plugin raised a deprecation warning during pytest
configuration, exit 3. Disabling external plugin autoload let the focused YAML
tests execute without changing repository configuration or dependencies.

Stop rule set before verification: two repair attempts or 20 minutes.
No hosted workflow execution or lossless queueing claim is established by these
local configuration tests. GitHub CI and post-push review remain separate gates.
