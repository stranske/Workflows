# Follow-up generator coverage evidence

Run: 2026-10-16, starting at `4ccaac9082ce07b889ba922e2804ec80771fc723`.
This is a PR-body supplement for the existing coverage PR, not a separate PR.

This round continues the issue's explicitly selected target,
`scripts/langchain/followup_issue_generator.py`. It does not select another target.
The canonical escaped-defect/churn/uncovered-mass ranking is not available in this
checkout. Historical `issue-3743` ranking artifacts explicitly use repair-subject
proxies rather than verified escaped defects; they cannot independently establish
the first unchecked next-target criterion. That criterion remains unverified.

The root `coverage.json` predates this work and measures a different scope. It
cannot establish repository-wide coverage or trigger the repository-wide 90%
stop condition. The figures below are fresh, targeted measurements only.

| Target | Before | After | Missing statements before/after | Missing branches before/after |
| --- | --- | --- | --- | --- |
| `scripts/langchain/followup_issue_generator.py` | 92.64% | 94.98% | 51 / 30 | 40 / 32 |

The denominator is unchanged at 846 statements plus 390 branches. This round
covers **29 additional units** (21 statements and 8 branches); it does not claim
60 additional units for this iteration or a repository-wide coverage increase.
Production code is unchanged. No real bug was exposed by these tests.

The new cases verify plain-prompt invocation when LangChain messages are absent,
preservation of the underlying invocation failure, trace-failure diagnostics,
four-round evidence forwarding and issue assembly, and bounded background history.

Coverage command, before and after:

```console
pytest tests/test_followup_issue_generator.py --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing -m 'not slow' -q
# Before: 170 passed; target Cover 92.64%.
# After:  178 passed; target Cover 94.98%.
```

The supplied slash-form module selector collected no coverage; the dotted module
selector above measures the actual imported module.

Each new parameter case was run independently with a deliberate source mutation,
then again after restoring the original source. All eight RED runs exited 1 with
an assertion failure; all eight restored GREEN runs exited 0 with one test passed.
The source was restored in a `finally` block for each mutation and verified to
have no diff afterward. Exact test IDs, replacements, assertion failures, exit
codes, and pytest summaries are retained in
[`followup-coverage-proof.json`](followup-coverage-proof.json).

Every test ID below has the prefix `tests/test_followup_issue_generator.py::`.
The proof command was `pytest '<test-id>' -m 'not slow' -q`.

| New test / parameter case | Deliberate break | RED | Restored GREEN |
| --- | --- | --- | --- |
| `test_invoke_without_langchain_uses_plain_prompts_and_preserves_output[configured]` | Replace the configured plain prompt with a different prompt | 1 failed | 1 passed |
| `test_invoke_without_langchain_uses_plain_prompts_and_preserves_output[fallback]` | Replace the retry's plain prompt with a different prompt | 1 failed | 1 passed |
| `test_invoke_without_langchain_reports_plain_prompt_failure_with_cause` | Drop the original exception cause | 1 failed | 1 passed |
| `test_trace_failures_preserve_generated_text_and_log_the_cause[missing-module]` | Remove the missing-module diagnostic | 1 failed | 1 passed |
| `test_trace_failures_preserve_generated_text_and_log_the_cause[extract-error]` | Remove the extraction-error diagnostic | 1 failed | 1 passed |
| `test_llm_rounds_forward_evidence_and_assemble_issue_with_optional_traces[populated]` | Suppress trace comments in the final issue | 1 failed | 1 passed |
| `test_llm_rounds_forward_evidence_and_assemble_issue_with_optional_traces[empty]` | Replace the fallback title focus | 1 failed | 1 passed |
| `test_structured_followup_keeps_structural_findings_and_caps_non_actionable_history` | Remove the five-item history cap | 1 failed | 1 passed |

Related validation after restoring all mutations:

```console
pytest tests/test_followup_issue_generator.py tests/test_verdict_policy.py tests/test_verdict_policy_integration.py tests/scripts/test_verifier_config.py -m 'not slow' -q
# 238 passed.
ruff check tests/test_followup_issue_generator.py
# All checks passed.
black --check --line-length 100 tests/test_followup_issue_generator.py
# Passed; the changed file was also formatted before validation.
git diff --check
# Passed.
```

The required repository-wide Black command was attempted. Its default worker
startup failed with `PermissionError` while binding the multiprocessing
forkserver socket. Single-worker retries did not finish and were stopped; no
successful repository-wide formatting result is claimed. No commit is permitted
until that gate passes in an environment where it can complete.

GitHub API access failed (`error connecting to api.github.com`). No PR-body or
checkbox edits were made, and PR readiness could not be independently verified.
Committing is also blocked: `git add` failed because `.git/index.lock` cannot be
created on the read-only `.git` filesystem. The changes remain uncommitted.
The full repository suite and CI Gate were not run locally; the results above
cover the target and related verdict/configuration tests.
