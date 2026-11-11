# test_remote_tree_transport_failure_preserves_unknown

Deliberate break:
```diff
--- scripts/check_consumer_sync_drift.py
+++ scripts/check_consumer_sync_drift.py
@@ -919,7 +919,7 @@
         repo_response = session.get(f"https://api.github.com/repos/{repo}")
     except requests.RequestException as exc:
         return (
-            None,
+            {},
             f"{repo}: repository access preflight failed (requests.{type(exc).__name__})",
         )
     if repo_response.status_code >= 400:
@@ -936,7 +936,7 @@
         )
     except requests.RequestException as exc:
         return (
-            None,
+            {},
             f"{repo}: repository tree fetch failed (requests.{type(exc).__name__})",
         )
     if tree_response.status_code >= 400:
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_check_consumer_sync_drift.py::test_remote_tree_transport_failure_preserves_unknown -m 'not slow' --tb=short -q
FFFF                                                                     [100%]
=================================== FAILURES ===================================
__ test_remote_tree_transport_failure_preserves_unknown[repo-ConnectionError] __
tests/scripts/test_check_consumer_sync_drift.py:41: in test_remote_tree_transport_failure_preserves_unknown
    assert check_consumer_sync_drift.fetch_remote_tree(session, "owner/repo") == (
E   AssertionError: assert ({}, 'owner/r...ectionError)') == (None, 'owner...ectionError)')
E
E     At index 0 diff: {} != None
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       (
E     -     None,
E     +     {},
E           'owner/repo: repository access preflight failed (requests.ConnectionError)',
E       )
______ test_remote_tree_transport_failure_preserves_unknown[repo-Timeout] ______
tests/scripts/test_check_consumer_sync_drift.py:41: in test_remote_tree_transport_failure_preserves_unknown
    assert check_consumer_sync_drift.fetch_remote_tree(session, "owner/repo") == (
E   AssertionError: assert ({}, 'owner/r...sts.Timeout)') == (None, 'owner...sts.Timeout)')
E
E     At index 0 diff: {} != None
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       (
E     -     None,
E     +     {},
E           'owner/repo: repository access preflight failed (requests.Timeout)',
E       )
__ test_remote_tree_transport_failure_preserves_unknown[tree-ConnectionError] __
tests/scripts/test_check_consumer_sync_drift.py:41: in test_remote_tree_transport_failure_preserves_unknown
    assert check_consumer_sync_drift.fetch_remote_tree(session, "owner/repo") == (
E   AssertionError: assert ({}, 'owner/r...ectionError)') == (None, 'owner...ectionError)')
E
E     At index 0 diff: {} != None
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       (
E     -     None,
E     +     {},
E           'owner/repo: repository tree fetch failed (requests.ConnectionError)',
E       )
______ test_remote_tree_transport_failure_preserves_unknown[tree-Timeout] ______
tests/scripts/test_check_consumer_sync_drift.py:41: in test_remote_tree_transport_failure_preserves_unknown
    assert check_consumer_sync_drift.fetch_remote_tree(session, "owner/repo") == (
E   AssertionError: assert ({}, 'owner/r...sts.Timeout)') == (None, 'owner...sts.Timeout)')
E
E     At index 0 diff: {} != None
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       (
E     -     None,
E     +     {},
E           'owner/repo: repository tree fetch failed (requests.Timeout)',
E       )
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_remote_tree_transport_failure_preserves_unknown[repo-ConnectionError] - AssertionError: assert ({}, 'owner/r...ectionError)') == (None, 'owner...ectionError)')

  At index 0 diff: {} != None

  Full diff: (-: missing in left side, +: extra in left side)
    (
  -     None,
  +     {},
        'owner/repo: repository access preflight failed (requests.ConnectionError)',
    )
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_remote_tree_transport_failure_preserves_unknown[repo-Timeout] - AssertionError: assert ({}, 'owner/r...sts.Timeout)') == (None, 'owner...sts.Timeout)')

  At index 0 diff: {} != None

  Full diff: (-: missing in left side, +: extra in left side)
    (
  -     None,
  +     {},
        'owner/repo: repository access preflight failed (requests.Timeout)',
    )
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_remote_tree_transport_failure_preserves_unknown[tree-ConnectionError] - AssertionError: assert ({}, 'owner/r...ectionError)') == (None, 'owner...ectionError)')

  At index 0 diff: {} != None

  Full diff: (-: missing in left side, +: extra in left side)
    (
  -     None,
  +     {},
        'owner/repo: repository tree fetch failed (requests.ConnectionError)',
    )
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_remote_tree_transport_failure_preserves_unknown[tree-Timeout] - AssertionError: assert ({}, 'owner/r...sts.Timeout)') == (None, 'owner...sts.Timeout)')

  At index 0 diff: {} != None

  Full diff: (-: missing in left side, +: extra in left side)
    (
  -     None,
  +     {},
        'owner/repo: repository tree fetch failed (requests.Timeout)',
    )
4 failed in 0.95s
exit=1

Exact reversion:
```diff
--- scripts/check_consumer_sync_drift.py
+++ scripts/check_consumer_sync_drift.py
@@ -919,7 +919,7 @@
         repo_response = session.get(f"https://api.github.com/repos/{repo}")
     except requests.RequestException as exc:
         return (
-            {},
+            None,
             f"{repo}: repository access preflight failed (requests.{type(exc).__name__})",
         )
     if repo_response.status_code >= 400:
@@ -936,7 +936,7 @@
         )
     except requests.RequestException as exc:
         return (
-            {},
+            None,
             f"{repo}: repository tree fetch failed (requests.{type(exc).__name__})",
         )
     if tree_response.status_code >= 400:
```
Restored source SHA-256: 4a339397f54b680719432f7d2a4fd136d7bdd40b2ad3dd267170c61c7eeb26c5

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_check_consumer_sync_drift.py::test_remote_tree_transport_failure_preserves_unknown -m 'not slow' --tb=short -q
....                                                                     [100%]
4 passed in 0.85s
exit=0
