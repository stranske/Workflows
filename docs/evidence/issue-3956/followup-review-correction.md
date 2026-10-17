# Current review correction

The former empty-label regression reached `_guard_payloads` branch `124->126`
by inspecting the caller frame and mutating its local payload list. That is not
an observable production contract: all production constructors use nonempty
label literals. The test and its now-unused `inspect` import were removed after
review, instead of changing production solely to manufacture coverage.

Current focused result: 199 tests pass; 853/853 statements are covered and one
of 388 branches remains defensively uncovered, for 99.92% combined coverage.
The prior empty-label and 100% receipts remain historical records and do not
establish current genuine branch coverage. Existing nonempty-label behavior,
injection blocking, real parsing/CLI/OSError contracts and their assertions
remain covered. No production bytes change in this correction.

Command: repository-selected Python, `-m pytest tests/test_followup_issue_generator.py
-q -o addopts= --cov=scripts.langchain.followup_issue_generator --cov-branch
--cov-report=term`. The same199 cases pass after integrating accepted main.
Current-head hosted checks and reviewer disposition remain separate gates.
