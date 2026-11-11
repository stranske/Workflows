# test_main_caches_failed_blob_reads_by_repo_and_sha

Deliberate break:
```diff
--- scripts/check_consumer_sync_drift.py
+++ scripts/check_consumer_sync_drift.py
@@ -1076,7 +1076,7 @@

     def read_blob(repo: str, sha: str) -> str | None:
         key = (repo, sha)
-        if key not in blob_text_cache:
+        if blob_text_cache.get(key) is None:
             blob_text_cache[key] = remote_blob_text(session, repo, sha)
         return blob_text_cache[key]

```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_failed_blob_reads_by_repo_and_sha -m 'not slow' --tb=short -q
F                                                                        [100%]
=================================== FAILURES ===================================
______________ test_main_caches_failed_blob_reads_by_repo_and_sha ______________
tests/scripts/test_check_consumer_sync_drift.py:100: in test_main_caches_failed_blob_reads_by_repo_and_sha
    assert Counter(call.args for call in read_blob.call_args_list) == Counter(
E   AssertionError: assert Counter({(<ob...ble-sha'): 3}) == Counter({(<ob...ble-sha'): 1})
E
E     Differing items:
E     {(<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 3} != {(<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 1}
E     {(<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 3} != {(<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 1}
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       Counter({
E     -     (<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 1,
E     ?                                                                           ^
E     +     (<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 3,
E     ?                                                                           ^
E     -     (<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 1,
E     ?                                                                            ^
E     +     (<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 3,
E     ?                                                                            ^
E       })
----------------------------- Captured stdout call -----------------------------
gate triggers: owner/first unknown (Gate unreadable)
gate triggers: owner/second unknown (Gate unreadable)
::warning::Consumer repo drift detected
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_failed_blob_reads_by_repo_and_sha - AssertionError: assert Counter({(<ob...ble-sha'): 3}) == Counter({(<ob...ble-sha'): 1})

  Differing items:
  {(<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 3} != {(<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 1}
  {(<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 3} != {(<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 1}

  Full diff: (-: missing in left side, +: extra in left side)
    Counter({
  -     (<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 1,
  ?                                                                           ^
  +     (<object object at 0x7ec1ce581840>, 'owner/first', 'unreadable-sha'): 3,
  ?                                                                           ^
  -     (<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 1,
  ?                                                                            ^
  +     (<object object at 0x7ec1ce581840>, 'owner/second', 'unreadable-sha'): 3,
  ?                                                                            ^
    })
1 failed in 0.82s
exit=1

Exact reversion:
```diff
--- scripts/check_consumer_sync_drift.py
+++ scripts/check_consumer_sync_drift.py
@@ -1076,7 +1076,7 @@

     def read_blob(repo: str, sha: str) -> str | None:
         key = (repo, sha)
-        if blob_text_cache.get(key) is None:
+        if key not in blob_text_cache:
             blob_text_cache[key] = remote_blob_text(session, repo, sha)
         return blob_text_cache[key]

```
Restored source SHA-256: 4a339397f54b680719432f7d2a4fd136d7bdd40b2ad3dd267170c61c7eeb26c5

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_failed_blob_reads_by_repo_and_sha -m 'not slow' --tb=short -q
.                                                                        [100%]
1 passed in 0.74s
exit=0
