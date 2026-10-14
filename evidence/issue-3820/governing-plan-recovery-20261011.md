# Governing plan in bounded diagnostic recovery — 2026-10-11

- [ ] Add bounded prompt recovery/partitioning for obligations that exceed exact-model capacity.

This change advances the remaining task by supplying the full governing plan in
every diagnostic request. Previously a later evidence/code range carried source
identities but could lack the scope, tasks and criteria needed to interpret it.
The planner now repeats the complete builder-owned acceptance section as escaped,
untrusted captured text, including linked-issue bodies. Its character count and
UTF-8 hash are retained in `governing_sources`. Existing native counting includes
this repeated text and the unchanged actual output reserve.

Missing governing plans reject before native counting. If the complete governing
plan cannot fit alongside the dependency contract and range identity, the
existing finite planning bounds reject all generation. Plans are not clipped,
summarized, replaced or assigned independent acceptance. The 8 MiB capture,
64-request and 127-planning-count limits remain unchanged. Source/template code
is identical and existing manifest copy coverage remains in place.

Cross-range evidence obligations remain globally dependent, so diagnostic
recovery always withholds PASS. This is not semantic partition acceptance or a
recovery of unavailable authenticated capture inputs. The task stays unchecked.
No live provider calls, workflow edits or generated consumer PR changes were
made. Publication, fleet sync and live acceptance remain outstanding.

## Validation

Before edits the partition suite passed: **50 passed**. The new tests executed
on that implementation with **8 behavioral failures**, including requests
missing governing context, oversized criteria wrongly admitted through bisection,
and absent governing plans wrongly admitted. No collection failure counted as RED.

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py -k governing_plan -m "not slow" --no-cov -q --tb=short
```

[Raw RED transcript](governing-plan-recovery-red.txt).

On final code the partition suite passed: **58 passed**, covering both configured
native adapters and evaluate/compare paths, intact Unicode/quoted fenced headings,
absence/overflow rejection and continued NON_PASS after diagnostic completion.

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py -m "not slow" --no-cov -q --tb=short
```

The combined focused suite passed: **4,640 passed, 19 skipped**. One skip needs
the owner-local authenticated capture; 18 are existing provider-inapplicable
Anthropic Models API cases. Provider HTTP outcomes are simulated in these tests.

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_native_capacity_registry.py tests/tools/test_verifier_capture_obligation_manifest.py tests/scripts/test_verifier_capture_integration.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_pr_verifier_config_and_report.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/workflows/test_verifier_evidence_profile.py -m "not slow" --no-cov -q
```

[Combined GREEN transcript](governing-plan-recovery-green.txt).

Ruff passed on both verifier copies and the test file;
`python scripts/validate_template_sync.py` and `git diff --check` passed.
Black formatted each changed Python file at line length 100.
The required full check passed: **701 files would be left unchanged**:

```bash
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The sandbox rejects Black's process scheduler and stalls its single-worker async
scheduler. A temporary `/tmp/verifier-governing-black-bin/black` launcher calls the
installed Black CLI with only scheduling replaced by sequential calls to its
unmodified `reformat_one`. File discovery, options, formatting, reporting and
exit status remain Black's own; no repository formatter settings changed.

## Publication limits

Canonical staging failed because `.git/index.lock` cannot be created on the
read-only Git mount. The source/test changes are committed in the writable local
clone `/tmp/verifier-governing-plan-3831`, with an exported bundle at
`/tmp/verifier-governing-plan-3831.bundle`. Canonical working-tree changes remain
available for the owning runner to stage and publish. No push was attempted.

`gh pr view 3831 --repo stranske/Workflows --json isDraft,state,headRefName,headRefOid`
failed connecting to `api.github.com`. Remote readiness and PR-body/comment
updates could not be verified or performed. No PR was created or changed by
this run. The incomplete task checkbox remains unchecked.
