# test_main_rejects_unreadable_artifact_manifest

Deliberate break:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -759,7 +759,7 @@
             manifest = _load_json(args.manifest) if args.manifest else None
         except (OSError, json.JSONDecodeError) as exc:
             print(f"ERROR: cannot load artifact manifest {args.manifest}: {exc}", file=sys.stderr)
-            return 2
+            return 1
         report = validate_envelope(
             envelope=envelope,
             schema_dir=args.schema_dir,
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_main_rejects_unreadable_artifact_manifest -m 'not slow' --tb=short -q
FFF                                                                      [100%]
=================================== FAILURES ===================================
___________ test_main_rejects_unreadable_artifact_manifest[missing] ____________
tests/scripts/test_validate_run_contract.py:1243: in test_main_rejects_unreadable_artifact_manifest
    assert (
E   AssertionError: assert 1 == 2
E    +  where 1 = <function main at 0x7081930d59b0>(['/home/runner/work/Workflows/Workflows/tests/fixtures/backplane/valid_run.json', '--manifest', '/tmp/pytest-of-runner...st.json', '--registry', '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a0/registry.json', '--repo', ...])
E    +    where <function main at 0x7081930d59b0> = vrc.main
----------------------------- Captured stderr call -----------------------------
ERROR: cannot load artifact manifest /tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a0/manifest.json: [Errno 2] No such file or directory: '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a0/manifest.json'
__________ test_main_rejects_unreadable_artifact_manifest[directory] ___________
tests/scripts/test_validate_run_contract.py:1243: in test_main_rejects_unreadable_artifact_manifest
    assert (
E   AssertionError: assert 1 == 2
E    +  where 1 = <function main at 0x7081930d59b0>(['/home/runner/work/Workflows/Workflows/tests/fixtures/backplane/valid_run.json', '--manifest', '/tmp/pytest-of-runner...st.json', '--registry', '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a1/registry.json', '--repo', ...])
E    +    where <function main at 0x7081930d59b0> = vrc.main
----------------------------- Captured stderr call -----------------------------
ERROR: cannot load artifact manifest /tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a1/manifest.json: [Errno 21] Is a directory: '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a1/manifest.json'
_________ test_main_rejects_unreadable_artifact_manifest[invalid-json] _________
tests/scripts/test_validate_run_contract.py:1243: in test_main_rejects_unreadable_artifact_manifest
    assert (
E   AssertionError: assert 1 == 2
E    +  where 1 = <function main at 0x7081930d59b0>(['/home/runner/work/Workflows/Workflows/tests/fixtures/backplane/valid_run.json', '--manifest', '/tmp/pytest-of-runner...st.json', '--registry', '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a2/registry.json', '--repo', ...])
E    +    where <function main at 0x7081930d59b0> = vrc.main
----------------------------- Captured stderr call -----------------------------
ERROR: cannot load artifact manifest /tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a2/manifest.json: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_main_rejects_unreadable_artifact_manifest[missing] - AssertionError: assert 1 == 2
 +  where 1 = <function main at 0x7081930d59b0>(['/home/runner/work/Workflows/Workflows/tests/fixtures/backplane/valid_run.json', '--manifest', '/tmp/pytest-of-runner...st.json', '--registry', '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a0/registry.json', '--repo', ...])
 +    where <function main at 0x7081930d59b0> = vrc.main
FAILED tests/scripts/test_validate_run_contract.py::test_main_rejects_unreadable_artifact_manifest[directory] - AssertionError: assert 1 == 2
 +  where 1 = <function main at 0x7081930d59b0>(['/home/runner/work/Workflows/Workflows/tests/fixtures/backplane/valid_run.json', '--manifest', '/tmp/pytest-of-runner...st.json', '--registry', '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a1/registry.json', '--repo', ...])
 +    where <function main at 0x7081930d59b0> = vrc.main
FAILED tests/scripts/test_validate_run_contract.py::test_main_rejects_unreadable_artifact_manifest[invalid-json] - AssertionError: assert 1 == 2
 +  where 1 = <function main at 0x7081930d59b0>(['/home/runner/work/Workflows/Workflows/tests/fixtures/backplane/valid_run.json', '--manifest', '/tmp/pytest-of-runner...st.json', '--registry', '/tmp/pytest-of-runner/pytest-35/test_main_rejects_unreadable_a2/registry.json', '--repo', ...])
 +    where <function main at 0x7081930d59b0> = vrc.main
3 failed in 0.83s
exit=1

Exact reversion:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -759,7 +759,7 @@
             manifest = _load_json(args.manifest) if args.manifest else None
         except (OSError, json.JSONDecodeError) as exc:
             print(f"ERROR: cannot load artifact manifest {args.manifest}: {exc}", file=sys.stderr)
-            return 1
+            return 2
         report = validate_envelope(
             envelope=envelope,
             schema_dir=args.schema_dir,
```
Restored source SHA-256: 5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_main_rejects_unreadable_artifact_manifest -m 'not slow' --tb=short -q
...                                                                      [100%]
3 passed in 0.71s
exit=0
