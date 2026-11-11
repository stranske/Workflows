# test_self_smoke_rejects_incomplete_schema_inventory

Deliberate break:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -821,11 +821,11 @@
             f"FAIL schema dir {schema_dir}: no *.schema.json files found; "
             "self-smoke cannot validate schemas"
         )
-        return 1
+        return 2
     missing = sorted(set(INGEST_SCHEMA_FILES.values()) - set(schema_names))
     if missing:
         print(f"FAIL schema dir {schema_dir}: missing registered schemas: {', '.join(missing)}")
-        return 1
+        return 2
     for name in schema_names:
         schema = _load_schema(schema_dir, name)
         Draft202012Validator.check_schema(schema)
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_self_smoke_rejects_incomplete_schema_inventory -m 'not slow' --tb=short -q
FF                                                                       [100%]
=================================== FAILURES ===================================
__________ test_self_smoke_rejects_incomplete_schema_inventory[empty] __________
tests/scripts/test_validate_run_contract.py:1325: in test_self_smoke_rejects_incomplete_schema_inventory
    assert vrc._self_smoke(schema_dir, registry) == 1
E   AssertionError: assert 2 == 1
E    +  where 2 = <function _self_smoke at 0x7357b2f7db10>(PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp0/schemas'), PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp0/registry.json'))
E    +    where <function _self_smoke at 0x7357b2f7db10> = vrc._self_smoke
----------------------------- Captured stdout call -----------------------------
FAIL schema dir /tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp0/schemas: no *.schema.json files found; self-smoke cannot validate schemas
___ test_self_smoke_rejects_incomplete_schema_inventory[missing-registered] ____
tests/scripts/test_validate_run_contract.py:1325: in test_self_smoke_rejects_incomplete_schema_inventory
    assert vrc._self_smoke(schema_dir, registry) == 1
E   AssertionError: assert 2 == 1
E    +  where 2 = <function _self_smoke at 0x7357b2f7db10>(PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp1/schemas'), PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp1/registry.json'))
E    +    where <function _self_smoke at 0x7357b2f7db10> = vrc._self_smoke
----------------------------- Captured stdout call -----------------------------
FAIL schema dir /tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp1/schemas: missing registered schemas: artifact-manifest-v1.schema.json, capability-bundle-v1.schema.json, document-mirror-v1.schema.json, evidence-object-v1.schema.json, mosaic-core-v1.schema.json, output-substrate-v1.schema.json, tracked-variable-v1.schema.json
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_self_smoke_rejects_incomplete_schema_inventory[empty] - AssertionError: assert 2 == 1
 +  where 2 = <function _self_smoke at 0x7357b2f7db10>(PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp0/schemas'), PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp0/registry.json'))
 +    where <function _self_smoke at 0x7357b2f7db10> = vrc._self_smoke
FAILED tests/scripts/test_validate_run_contract.py::test_self_smoke_rejects_incomplete_schema_inventory[missing-registered] - AssertionError: assert 2 == 1
 +  where 2 = <function _self_smoke at 0x7357b2f7db10>(PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp1/schemas'), PosixPath('/tmp/pytest-of-runner/pytest-39/test_self_smoke_rejects_incomp1/registry.json'))
 +    where <function _self_smoke at 0x7357b2f7db10> = vrc._self_smoke
2 failed in 0.81s
exit=1

Exact reversion:
```diff
--- scripts/validate_run_contract.py
+++ scripts/validate_run_contract.py
@@ -821,11 +821,11 @@
             f"FAIL schema dir {schema_dir}: no *.schema.json files found; "
             "self-smoke cannot validate schemas"
         )
-        return 2
+        return 1
     missing = sorted(set(INGEST_SCHEMA_FILES.values()) - set(schema_names))
     if missing:
         print(f"FAIL schema dir {schema_dir}: missing registered schemas: {', '.join(missing)}")
-        return 2
+        return 1
     for name in schema_names:
         schema = _load_schema(schema_dir, name)
         Draft202012Validator.check_schema(schema)
```
Restored source SHA-256: 5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_self_smoke_rejects_incomplete_schema_inventory -m 'not slow' --tb=short -q
..                                                                       [100%]
2 passed in 0.72s
exit=0
