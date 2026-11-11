# test_consumer_mirror_enforces_catalog_timestamp

Deliberate break:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -293,6 +293,8 @@
     satellite schema it declares.
     """
     ingests = entry.get("ingests", []) or []
+    if "document-mirror/v1" in ingests:
+        report.fail("mirror routing regression", "ingests")
     if not ingests:
         report.fail(
             f"consumer {report.repo} declares no 'ingests' schemas to validate",
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_consumer_mirror_enforces_catalog_timestamp -m 'not slow' --tb=short -q
FF                                                                       [100%]
=================================== FAILURES ===================================
___________ test_consumer_mirror_enforces_catalog_timestamp[invalid] ___________
tests/scripts/test_validate_run_contract.py:1231: in test_consumer_mirror_enforces_catalog_timestamp
    assert [(v.path, v.message) for v in report.violations] == expected
E   assert [('ingests', ...'date-time'")] == [('', "ingest...'date-time'")]
E
E     At index 0 diff: ('ingests', 'mirror routing regression') != ('', "ingested-as-document-mirror/v1: 'not-a-timestamp' is not a 'date-time'")
E     Left contains one more item: ('', "ingested-as-document-mirror/v1: 'not-a-timestamp' is not a 'date-time'")
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       [
E     +     (
E     +         'ingests',
E     +         'mirror routing regression',
E     +     ),
E           (
E               '',
E               "ingested-as-document-mirror/v1: 'not-a-timestamp' is not a "
E               "'date-time'",
E           ),
E       ]
____________ test_consumer_mirror_enforces_catalog_timestamp[valid] ____________
tests/scripts/test_validate_run_contract.py:1230: in test_consumer_mirror_enforces_catalog_timestamp
    assert report.conformant is valid_timestamp
E   AssertionError: assert False is True
E    +  where False = Report(repo='owner/mirror-consumer', role='consumer', conformant=False, skipped=False, violations=[Violation(message='mirror routing regression', path='ingests')]).conformant
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_consumer_mirror_enforces_catalog_timestamp[invalid] - assert [('ingests', ...'date-time'")] == [('', "ingest...'date-time'")]

  At index 0 diff: ('ingests', 'mirror routing regression') != ('', "ingested-as-document-mirror/v1: 'not-a-timestamp' is not a 'date-time'")
  Left contains one more item: ('', "ingested-as-document-mirror/v1: 'not-a-timestamp' is not a 'date-time'")

  Full diff: (-: missing in left side, +: extra in left side)
    [
  +     (
  +         'ingests',
  +         'mirror routing regression',
  +     ),
        (
            '',
            "ingested-as-document-mirror/v1: 'not-a-timestamp' is not a "
            "'date-time'",
        ),
    ]
FAILED tests/scripts/test_validate_run_contract.py::test_consumer_mirror_enforces_catalog_timestamp[valid] - AssertionError: assert False is True
 +  where False = Report(repo='owner/mirror-consumer', role='consumer', conformant=False, skipped=False, violations=[Violation(message='mirror routing regression', path='ingests')]).conformant
2 failed in 0.79s
exit=1

Exact reversion:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -293,8 +293,6 @@
     satellite schema it declares.
     """
     ingests = entry.get("ingests", []) or []
-    if "document-mirror/v1" in ingests:
-        report.fail("mirror routing regression", "ingests")
     if not ingests:
         report.fail(
             f"consumer {report.repo} declares no 'ingests' schemas to validate",
```
Restored source SHA-256: 5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_consumer_mirror_enforces_catalog_timestamp -m 'not slow' --tb=short -q
..                                                                       [100%]
2 passed in 0.71s
exit=0
