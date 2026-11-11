# test_main_persists_valid_run_conformance

Deliberate break:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -796,7 +796,7 @@
         )
     if args.github_output:
         with args.github_output.open("a") as fh:
-            ok = report.conformant or report.skipped
+            ok = False
             fh.write(f"conformant={'true' if ok else 'false'}\n")

     if report.skipped or report.conformant:
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_main_persists_valid_run_conformance -m 'not slow' --tb=short -q
F                                                                        [100%]
=================================== FAILURES ===================================
___________________ test_main_persists_valid_run_conformance ___________________
tests/scripts/test_validate_run_contract.py:1296: in test_main_persists_valid_run_conformance
    assert output.read_text() == "earlier=value\nconformant=true\n"
E   AssertionError: assert 'earlier=valu...rmant=false\n' == 'earlier=valu...ormant=true\n'
E
E       earlier=value
E     - conformant=true
E     ?            ^^^
E     + conformant=false
E     ?            ^^^^
----------------------------- Captured stdout call -----------------------------
stranske/Pension-Data: run envelope conforms to run-contract/v1
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_main_persists_valid_run_conformance - AssertionError: assert 'earlier=valu...rmant=false\n' == 'earlier=valu...ormant=true\n'

    earlier=value
  - conformant=true
  ?            ^^^
  + conformant=false
  ?            ^^^^
1 failed in 0.78s
exit=1

Exact reversion:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -796,7 +796,7 @@
         )
     if args.github_output:
         with args.github_output.open("a") as fh:
-            ok = False
+            ok = report.conformant or report.skipped
             fh.write(f"conformant={'true' if ok else 'false'}\n")

     if report.skipped or report.conformant:
```
Restored source SHA-256: 5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_main_persists_valid_run_conformance -m 'not slow' --tb=short -q
.                                                                        [100%]
1 passed in 0.72s
exit=0
