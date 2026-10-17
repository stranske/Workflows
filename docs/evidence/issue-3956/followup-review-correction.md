# Historical review correction and subsequent helper proof

The former empty-label regression reached `_guard_payloads` branch `124->126`
by inspecting the caller frame and mutating its local payload list. That is not
an observable production contract: all production constructors use nonempty
label literals. The test and its now-unused `inspect` import were removed after
review, instead of changing production solely to manufacture coverage.

Intermediate focused result before the later helper extraction: 199 tests passed; 853/853 statements are covered and one
of 388 branches remains defensively uncovered, for 99.92% combined coverage.
The prior empty-label and 100% receipts remain historical records and do not
establish genuine branch coverage for that intermediate state. Existing nonempty-label behavior,
injection blocking, real parsing/CLI/OSError contracts and their assertions
remain covered. No production bytes change in this correction.

Command: repository-selected Python, `-m pytest tests/test_followup_issue_generator.py
-q -o addopts= --cov=scripts.langchain.followup_issue_generator --cov-branch
--cov-report=term`. The same 199 cases passed after integrating accepted main at that intermediate correction.
Current-head hosted checks and reviewer disposition remain separate gates.

Subsequently, the native implementation extracted `_blocked_reason_with_source`
and added `test_blocked_reason_with_source_omits_blank_annotation_for_empty_label`.
`followup-blocked-reason-helper-proof.json` records the causal failing mutation
and restored passing test. The later native completion reports 200 passing tests,
852 statements, 386 branches, zero misses, and 100.00% combined coverage. These
are later native results, distinct from the historical 199-test/99.92% result
above. OSError handling and helper extraction are limited production changes;
this PR is not test-only. This documentation correction changes no source or
test bytes and does not itself repeat or upgrade the native coverage evidence.
