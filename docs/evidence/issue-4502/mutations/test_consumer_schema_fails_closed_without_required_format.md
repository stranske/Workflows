# test_consumer_schema_fails_closed_without_required_format

Deliberate break:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -142,6 +142,8 @@

 def _validator_for_schema(schema_dir: Path, name: str) -> Draft202012Validator:
     schema = _load_schema(schema_dir, name)
+    if name in ('mosaic-core-v1.schema.json', 'document-mirror-v1.schema.json'):
+        raise RuntimeError('schema loading regression')
     if name == "mosaic-core-v1.schema.json":
         # Explicitly request the checker so a missing rfc3339-validator dependency
         # fails instead of silently accepting malformed checked_at timestamps.
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_consumer_schema_fails_closed_without_required_format -m 'not slow' --tb=short -q
FFF                                                                      [100%]
=================================== FAILURES ===================================
_ test_consumer_schema_fails_closed_without_required_format[document-mirror/v1-valid_document_mirror.json-date-time] _
tests/scripts/test_validate_run_contract.py:1206: in test_consumer_schema_fails_closed_without_required_format
    with pytest.raises(RuntimeError, match=f"unavailable: {format_name}"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   AssertionError: Regex pattern did not match.
E     Expected regex: 'unavailable: date-time'
E     Actual message: 'schema loading regression'
_ test_consumer_schema_fails_closed_without_required_format[document-mirror/v1-valid_document_mirror.json-uri] _
tests/scripts/test_validate_run_contract.py:1206: in test_consumer_schema_fails_closed_without_required_format
    with pytest.raises(RuntimeError, match=f"unavailable: {format_name}"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   AssertionError: Regex pattern did not match.
E     Expected regex: 'unavailable: uri'
E     Actual message: 'schema loading regression'
_ test_consumer_schema_fails_closed_without_required_format[mosaic-core/v1-valid_mosaic_thesis_check.json-date-time] _
tests/scripts/test_validate_run_contract.py:1206: in test_consumer_schema_fails_closed_without_required_format
    with pytest.raises(RuntimeError, match=f"unavailable: {format_name}"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   AssertionError: Regex pattern did not match.
E     Expected regex: 'unavailable: date-time'
E     Actual message: 'schema loading regression'
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_consumer_schema_fails_closed_without_required_format[document-mirror/v1-valid_document_mirror.json-date-time] - AssertionError: Regex pattern did not match.
  Expected regex: 'unavailable: date-time'
  Actual message: 'schema loading regression'
FAILED tests/scripts/test_validate_run_contract.py::test_consumer_schema_fails_closed_without_required_format[document-mirror/v1-valid_document_mirror.json-uri] - AssertionError: Regex pattern did not match.
  Expected regex: 'unavailable: uri'
  Actual message: 'schema loading regression'
FAILED tests/scripts/test_validate_run_contract.py::test_consumer_schema_fails_closed_without_required_format[mosaic-core/v1-valid_mosaic_thesis_check.json-date-time] - AssertionError: Regex pattern did not match.
  Expected regex: 'unavailable: date-time'
  Actual message: 'schema loading regression'
3 failed in 0.93s
exit=1

Exact reversion:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -142,8 +142,6 @@

 def _validator_for_schema(schema_dir: Path, name: str) -> Draft202012Validator:
     schema = _load_schema(schema_dir, name)
-    if name in ('mosaic-core-v1.schema.json', 'document-mirror-v1.schema.json'):
-        raise RuntimeError('schema loading regression')
     if name == "mosaic-core-v1.schema.json":
         # Explicitly request the checker so a missing rfc3339-validator dependency
         # fails instead of silently accepting malformed checked_at timestamps.
```
Restored source SHA-256: 5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_consumer_schema_fails_closed_without_required_format -m 'not slow' --tb=short -q
...                                                                      [100%]
3 passed in 0.72s
exit=0
