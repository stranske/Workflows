# Issue 4484 focused validation

Check date: 2026-11-06. Interpreter: /opt/anaconda3/bin/python3.

The concrete SubscriptionClient.invoke(prompt, **_kwargs) accepts config; the real implementation is exercised with only availability and the subprocess boundary mocked. No subscription CLI is launched.

## Deliberate break: _llm_client.py

`/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py::test_no_arg002_violations[_llm_client.py]`

```text
F                                                                        [100%]
=================================== FAILURES ===================================
__________________ test_no_arg002_violations[_llm_client.py] ___________________

filename = '_llm_client.py'

    @pytest.mark.parametrize("filename", ["_llm_client.py", "pr_verifier.py"])
    def test_no_arg002_violations(filename: str) -> None:
        """Check each copy-delivered source with the consumer's unused-argument rule."""
        source = ROOT / "scripts" / "langchain" / filename
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "ARG002", str(source)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    
>       assert result.returncode == 0, result.stdout + result.stderr
E       AssertionError: ARG002 Unused method argument: `config`
E           --> scripts/langchain/_llm_client.py:40:35
E            |
E         38 |     client: Any
E         39 |
E         40 |     def invoke(self, prompt: Any, config: Any = None, **kwargs: Any) -> Any:
E            |                                   ^^^^^^
E         41 |         if not isinstance(prompt, str):
E         42 |             to_string = getattr(prompt, "to_string", None)
E            |
E         
E         Found 1 error.
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/opt/anaconda3/bin/python3', '-m', 'ruff', 'check', '--isolated', '--select', 'ARG002', '/User...e(prompt, str):\n42 |             to_string = getattr(prompt, "to_string", None)\n   |\n\nFound 1 error.\n', stderr='').returncode

tests/langchain/test_arg002_regression.py:29: AssertionError
=========================== short test summary info ============================
FAILED tests/langchain/test_arg002_regression.py::test_no_arg002_violations[_llm_client.py]
1 failed in 0.39s

Exit: 1
```

Restored the retained fix:

```text
.                                                                        [100%]
1 passed in 0.20s
Exit: 0
```

## Deliberate break: pr_verifier.py

`/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py::test_no_arg002_violations[pr_verifier.py]`

```text
F                                                                        [100%]
=================================== FAILURES ===================================
__________________ test_no_arg002_violations[pr_verifier.py] ___________________

filename = 'pr_verifier.py'

    @pytest.mark.parametrize("filename", ["_llm_client.py", "pr_verifier.py"])
    def test_no_arg002_violations(filename: str) -> None:
        """Check each copy-delivered source with the consumer's unused-argument rule."""
        source = ROOT / "scripts" / "langchain" / filename
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "ARG002", str(source)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    
>       assert result.returncode == 0, result.stdout + result.stderr
E       AssertionError: ARG002 Unused method argument: `config`
E             --> scripts/langchain/pr_verifier.py:8735:35
E              |
E         8733 |         )
E         8734 |
E         8735 |     def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:
E              |                                   ^^^^^^
E         8736 |         import urllib.error
E         8737 |         import urllib.request
E              |
E         
E         Found 1 error.
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/opt/anaconda3/bin/python3', '-m', 'ruff', 'check', '--isolated', '--select', 'ARG002', '/User...^^^^\n8736 |         import urllib.error\n8737 |         import urllib.request\n     |\n\nFound 1 error.\n', stderr='').returncode

tests/langchain/test_arg002_regression.py:29: AssertionError
=========================== short test summary info ============================
FAILED tests/langchain/test_arg002_regression.py::test_no_arg002_violations[pr_verifier.py]
1 failed in 0.31s

Exit: 1
```

Restored the retained fix:

```text
.                                                                        [100%]
1 passed in 0.23s
Exit: 0
```
## Final focused checks

`/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py tests/scripts/test_verifier_capacity_backup.py`

Printed `101 passed in 9.72s` on the first focused run.

`/opt/anaconda3/bin/python3 -m ruff check --isolated --select ARG002 scripts/langchain/_llm_client.py scripts/langchain/pr_verifier.py`

Printed `All checks passed!`.

The two exact template-parity tests that failed in run 42291331314 printed
`2 passed in 0.26s` after aligning the retained verifier suppression:

- `tests/scripts/test_pr_verifier_sync_manifest.py::test_pr_verifier_source_and_consumer_template_are_identical`
- `tests/scripts/test_native_capacity_registry.py::test_native_facts_and_helper_are_managed_with_exact_template_parity`

## First unresolved step

The ledger has unquoted colon-containing notes and unsupported `completed`
statuses. The session marks `.agents` read-only; writing the correction returned
`PermissionError: [Errno 1] Operation not permitted`. No bypass was attempted.
A proposed patch at `/tmp/4487-ledger-repair.patch` quotes note strings, changes
`completed` to `done`, and binds finished entries to retained substantive commit
`de5f440ac`. Validating its temporary copy with
`/opt/anaconda3/bin/python3 scripts/ledger_validate.py /tmp/issue-4484-ledger.yml`
printed `Validated /tmp/issue-4484-ledger.yml`. This is proposed-patch evidence,
not validation of the unchanged repository ledger.

Guarded source delivery remains blocked by ledger validation. Consumer lint on
an automatically regenerated PR and the next sync-core classification remain
unproven and must follow source delivery. The generated consumer PR was not edited.
