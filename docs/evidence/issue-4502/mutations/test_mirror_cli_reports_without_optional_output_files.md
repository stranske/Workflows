# test_mirror_cli_reports_without_optional_output_files

Deliberate break:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -703,7 +703,7 @@
             args.evidence_objects or args.tracked_variables or args.mirror_manifest or []
         )
         if report.conformant:
-            print(f"{label}: {path_count} file(s) conform to schema")
+            print(f"{label}: {path_count} file(s) rejected by schema")
         else:
             print(
                 f"{label}: {len(report.violations)} conformance violation(s):",
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_mirror_cli_reports_without_optional_output_files -m 'not slow' --tb=short -q
F                                                                        [100%]
=================================== FAILURES ===================================
____________ test_mirror_cli_reports_without_optional_output_files _____________
tests/scripts/test_validate_run_contract.py:1313: in test_mirror_cli_reports_without_optional_output_files
    assert captured.out == "document-mirror/v1: 1 file(s) conform to schema\n"
E   AssertionError: assert 'document-mir...d by schema\n' == 'document-mir...m to schema\n'
E
E     - document-mirror/v1: 1 file(s) conform to schema
E     ?                                ------- ^
E     + document-mirror/v1: 1 file(s) rejected by schema
E     ?                               ++++  ^^^^^
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_mirror_cli_reports_without_optional_output_files - AssertionError: assert 'document-mir...d by schema\n' == 'document-mir...m to schema\n'

  - document-mirror/v1: 1 file(s) conform to schema
  ?                                ------- ^
  + document-mirror/v1: 1 file(s) rejected by schema
  ?                               ++++  ^^^^^
1 failed in 0.78s
exit=1

Exact reversion:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -703,7 +703,7 @@
             args.evidence_objects or args.tracked_variables or args.mirror_manifest or []
         )
         if report.conformant:
-            print(f"{label}: {path_count} file(s) rejected by schema")
+            print(f"{label}: {path_count} file(s) conform to schema")
         else:
             print(
                 f"{label}: {len(report.violations)} conformance violation(s):",
```
Restored source SHA-256: 5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_mirror_cli_reports_without_optional_output_files -m 'not slow' --tb=short -q
.                                                                        [100%]
1 passed in 0.71s
exit=0
