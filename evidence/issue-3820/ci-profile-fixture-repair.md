# Deterministic configured-adapter profile fixture repair

Base: PR #3821, `96528ac6b7888f4add72c72799128371c5230da2` (local HEAD verified unchanged).
Date: 2026-10-10.

The supplied hosted failure is Gate run 38065872631, Python 3.13 job
114253624766: nine OpenAI compatibility failures, 102286 passed, 7 skipped,
3 xfailed. Hosted `langchain-openai==1.4.1` supplies a Terra profile; this
hosted result/version is task input, not a fresh hosted execution by this worker.

## Scope

Only `tests/scripts/test_pr_verifier_recovery.py` and this evidence file change.
The fixture still constructs the registry-selected real OpenAI/Anthropic adapters
using their existing builders and checks their native request model/messages.
It deliberately sets `profile=None` for absent-capacity cases instead of
requiring the installed SDK to omit model facts. An additional real OpenAI
adapter case receives explicit test-only positive input/output limits. Its
Chat Completions payload still has no supported native message counter, so
expanded evaluate, compare, and schema repair must return CONCERNS, record the
specific unavailable-counter reason, and never invoke generation. Default and
standard modes still invoke exactly once and emit no capacity receipt in all
three operations. HTTP send is mocked and asserted unused for every case.
No provider substitution or production capacity/behavior change is introduced.

## Deliberate RED

Starting with the exact base test, `apply_patch` added `monkeypatch` to
`configured_native_client` and, immediately after its real OpenAI payload
assertions, assigned the actual constructed OpenAI adapter:

```python
monkeypatch.setattr(
    client, "profile", {"max_input_tokens": 100000, "max_output_tokens": 1000}
)
```

The original `assert client.profile is None` remained intact for this run:

```sh
python -m pytest -q tests/scripts/test_pr_verifier_recovery.py -k test_configured_native_client_compatibility > /private/tmp/issue-3820-profile-red.txt 2>&1
```

Exit 1: **9 failed, 9 passed, 36 deselected in 5.88s**. Every OpenAI
evaluate/compare/repair × default/standard/expanded case failed at that assertion:

```text
E AssertionError: assert {'max_input_tokens': 100000, 'max_output_tokens': 1000} is None
tests/scripts/test_pr_verifier_recovery.py:61: AssertionError
```

This reproduces the brittle assumption independently of installed model facts,
on the actual configured adapter, without an SDK upgrade or a network request.
The final fixture keeps the same populated dictionary as its explicit control,
alongside deterministic absent-facts cases. No production mutation occurred.

## GREEN and checks

```sh
python -m pytest -q tests/scripts/test_pr_verifier_recovery.py > /private/tmp/issue-3820-profile-green.txt 2>&1
```

Exit 0: **62 passed, 1 skipped in 7.78s**. The skip is the pre-existing
owner-local immutable authenticated capture requiring
`VERIFIER_RECOVERY_CAPTURE_DIR`; no authenticated capture replay is claimed.

```sh
python -m pytest -q tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/tools/test_langchain_client.py > /private/tmp/issue-3820-profile-focused.txt 2>&1
```

Exit 0: **4008 passed, 1 skipped in 44.53s**, with the same capture-only skip.
This includes the configured-adapter fixture matrix, prompt capacity/coverage,
comparison, structured/schema output, and existing adapter construction tests.

```sh
python -m ruff check tests/scripts/test_pr_verifier_recovery.py
python -m black --check --target-version py312 tests/scripts/test_pr_verifier_recovery.py
python -m black --check --fast tests/scripts/test_pr_verifier_recovery.py
git diff --check
```

All exit 0: Ruff reports all checks passed; both Black checks leave the file
unchanged; diff whitespace validation is clean. Black's configured Python 3.13
target cannot perform its AST safety check under the local Python 3.12 runner,
so both the explicit Python 3.12 AST check and configured-target formatting-only
check were run. The initial plain Black check identified one wrapping change,
which was applied with `apply_patch` before these passing checks.

An intermediate test run added a new `not result.used_llm` assertion and failed
three schema-repair cases: existing schema-repair metadata sets that flag even
when the capacity guard blocks invocation. That added assertion was removed;
the existing verdict, invocation, receipt, compatibility, and repair PASS
assertions remain. No production behavior was changed to satisfy the test.

## Environment and limits

Local validation: Python 3.12.2, langchain-openai 1.3.2,
langchain-anthropic 1.4.6, pytest 9.1.1, Ruff 0.16.7, Black 26.5.1.
System Python 3.13.13 lacks the LangChain adapters and Black; no dependencies
were installed. These local results do not establish a hosted Python 3.13 Gate
pass or a full-suite pass. The deterministic profile control covers the reported
SDK-profile difference without relying on package metadata or remote calls.

Original test SHA-256: `1feb7b1a78e31e421b2caf661751d820c571a793f898cabe7117610309fdfb3f`.
Final test SHA-256: `f6eb47473e05c89977fd3775c178191bcae1396a828668aafd1e6da64429598f`.
RED log SHA-256: `d36414be2a0e92d95bc269f8e5a1832f838e1b07034ad90b96561e928a0af93e`.
Recovery GREEN log SHA-256: `2f0718abb4467b891ef5b5ce34339f040da280218d621ba2d26018684abca723`.

No production/template/documentation edits, git writes, GitHub writes, automation
actions, or changes to the independent source-capacity worker/worktree occurred.
Publication remains parent-owned.
