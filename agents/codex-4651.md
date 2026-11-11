<!-- bootstrap for codex on issue #4651 run:43083618531-1 -->

Health 85 recovery handoff for #4642
==================================

The first task remains incomplete. GitHub reads confirmed that #4642 is closed
and still has `ci-budget`. The connected account is the issue owner, `stranske`,
but reopening, posting the owner handoff comment, and adding `needs-human` to
PR #4659 were each rejected: the connector requires approval and this run's
approval policy is `never`. No GitHub write succeeded.

Required owner action: `gh issue reopen 4642 --repo stranske/Workflows`.
Preserve `ci-budget`; `scripts/ci_time_budget.py::reconcile` reads open issues
with that label. Leave #4642 open while daily evidence remains incomplete.

The report read from `ci-time-budget:docs/reports/ci-budget.json` retains:

- 2026-11-10: p50 11.133333333333333 minutes, native run
  <https://github.com/stranske/Workflows/actions/runs/42838942059>.
- 2026-11-11: p50 10.5 minutes, native run
  <https://github.com/stranske/Workflows/actions/runs/43013607206>.

Both exceed the ten-minute target. Seven consecutive qualifying UTC dates and
the Health 85 closure comment remain unverified. The required `gh issue view`
and report-content commands were attempted, but local GitHub access failed with
`error connecting to api.github.com`; the GitHub connector supplied the reads.

Added a parametrized regression in `tests/scripts/test_ci_time_budget.py` that
confirms owner reopening lets reconciliation reuse the existing labeled issue,
preserves its checklist and labels, keeps it open through missing, unknown, and
over-target dates, and posts seven dated values before closing. Its simulated
observations are test inputs, not evidence of live acceptance.

Validation: `pytest tests/scripts/test_ci_time_budget.py
tests/scripts/test_health85_followup.py -m 'not slow' -q` passed (44 tests).
Ruff passed for the changed test. The required full Black command passed with
1,006 files unchanged, using `BLACK_NUM_WORKERS=1` and a writable temporary cache
populated by serial Black checks with the current configured exclusions. The
default worker setup failed on the sandbox's blocked forkserver socket, and
uncached worker runs stalled; the serial check retained the normal safety checks.

The requested commit could not be created: `git add` failed while creating
`.git/index.lock` because `.git` is mounted read-only. The validated changes
remain in the working tree on `codex/issue-4651`; no branch or PR was created.
PR #4659 was verified open with `isDraft=false`.

Next iteration: daily report persistence
---------------------------------------

Added `test_daily_runs_reload_native_sources_and_publish_before_recovery_closure`
in `tests/scripts/test_ci_time_budget.py`. Unlike the earlier row-level regression,
this exercises `run`, `load_report`, `publish`, and `reconcile` together through
the report Contents API boundary. Each invocation reloads serialized state and
uses the preceding blob SHA when publishing to `ci-time-budget`. The three cases
retain native daily sources across missing, unavailable, and over-target dates,
keep the reopened issue open until seven consecutive qualifying dates, and verify
publication before the closure comment and issue close. Inputs remain simulated;
this test does not establish live acceptance or modify the published report.

Validation: `pytest tests/scripts/test_ci_time_budget.py
tests/scripts/test_health85_followup.py -m 'not slow' -q` passed all 47 tests.
`ruff check tests/scripts/test_ci_time_budget.py` and `git diff --check` passed.
The required `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` passed with 1,006 files unchanged. As in the
prior iteration, serial Black checks populated a temporary cache before running
the exact CLI check with one worker; the uncached worker invocation stalled.

Live connector reads still show #4642 closed with `ci-budget`, and only the two
over-target November 10/11 observations described above. The prior denied owner
handoff writes were not repeated. No task or acceptance checkbox was completed.
Both required CLI read commands were attempted again; `gh` could not connect to
GitHub. PR #4659 remains open with `isDraft=false`.

Staging this iteration also failed with `.git/index.lock: Read-only file system`.
The test change remains uncommitted on the existing PR branch for the runner to
commit; no branch or PR was created.
