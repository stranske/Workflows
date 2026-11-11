# test_verifier_ledger_counts_escalations_without_duplicating_shared_followups

Deliberate break:
```diff
--- scripts/aggregate_agent_metrics.py
+++ scripts/aggregate_agent_metrics.py
@@ -836,7 +836,7 @@
         if followup_issue is not None:
             ledger_followup_issues.add(followup_issue)
         if bool(entry.get("needs_human")) or disposition == "needs-human":
-            ledger_needs_human += 1
+            ledger_needs_human += 2
         chain_depth = _safe_int(entry.get("chain_depth"))
         if chain_depth is not None:
             ledger_chain_depths.append(chain_depth)
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_verifier_ledger_counts_escalations_without_duplicating_shared_followups -m 'not slow' --tb=short -q
F                                                                        [100%]
=================================== FAILURES ===================================
_ test_verifier_ledger_counts_escalations_without_duplicating_shared_followups _
tests/scripts/test_aggregate_agent_metrics.py:477: in test_verifier_ledger_counts_escalations_without_duplicating_shared_followups
    assert {key: value for key, value in summary.items() if key.startswith("ledger_")} == {
E   AssertionError: assert {'ledger_reco...sues': 1, ...} == {'ledger_reco...sues': 1, ...}
E
E     Omitting 10 identical items, use -vv to show
E     Differing items:
E     {'ledger_needs_human': 4} != {'ledger_needs_human': 2}
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       {
E           'ledger_records': 2,
E     -     'ledger_dispositions': {
E     +     'ledger_dispositions': Counter({
E     ?                            ++++++++
E               'follow-up': 1,
E               'needs-human': 1,
E     -     },
E     +     }),
E     ?      +
E           'ledger_prs': 1,
E           'ledger_followup_issues': 1,
E     -     'ledger_needs_human': 2,
E     ?                           ^
E     +     'ledger_needs_human': 4,
E     ?                           ^
E           'ledger_avg_chain_depth': 2.0,
E           'ledger_max_chain_depth': 3,
E           'ledger_policy_records': 0,
E     -     'ledger_policy_actions': {},
E     ?                              ^^
E     +     'ledger_policy_actions': Counter(),
E     ?                              ^^^^^^^^^
E     -     'ledger_policy_triggers': {},
E     ?                               ^^
E     +     'ledger_policy_triggers': Counter(),
E     ?                               ^^^^^^^^^
E           'ledger_policy_depth_limit_exceeded': 0,
E       }
=========================== short test summary info ============================
FAILED tests/scripts/test_aggregate_agent_metrics.py::test_verifier_ledger_counts_escalations_without_duplicating_shared_followups - AssertionError: assert {'ledger_reco...sues': 1, ...} == {'ledger_reco...sues': 1, ...}

  Omitting 10 identical items, use -vv to show
  Differing items:
  {'ledger_needs_human': 4} != {'ledger_needs_human': 2}

  Full diff: (-: missing in left side, +: extra in left side)
    {
        'ledger_records': 2,
  -     'ledger_dispositions': {
  +     'ledger_dispositions': Counter({
  ?                            ++++++++
            'follow-up': 1,
            'needs-human': 1,
  -     },
  +     }),
  ?      +
        'ledger_prs': 1,
        'ledger_followup_issues': 1,
  -     'ledger_needs_human': 2,
  ?                           ^
  +     'ledger_needs_human': 4,
  ?                           ^
        'ledger_avg_chain_depth': 2.0,
        'ledger_max_chain_depth': 3,
        'ledger_policy_records': 0,
  -     'ledger_policy_actions': {},
  ?                              ^^
  +     'ledger_policy_actions': Counter(),
  ?                              ^^^^^^^^^
  -     'ledger_policy_triggers': {},
  ?                               ^^
  +     'ledger_policy_triggers': Counter(),
  ?                               ^^^^^^^^^
        'ledger_policy_depth_limit_exceeded': 0,
    }
1 failed in 0.78s
exit=1

Exact reversion:
```diff
--- scripts/aggregate_agent_metrics.py
+++ scripts/aggregate_agent_metrics.py
@@ -836,7 +836,7 @@
         if followup_issue is not None:
             ledger_followup_issues.add(followup_issue)
         if bool(entry.get("needs_human")) or disposition == "needs-human":
-            ledger_needs_human += 2
+            ledger_needs_human += 1
         chain_depth = _safe_int(entry.get("chain_depth"))
         if chain_depth is not None:
             ledger_chain_depths.append(chain_depth)
```
Restored source SHA-256: e03bd53293d5627de350405f9dcfdda966b9071c7954c59241ced4cbf12bd1df

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_verifier_ledger_counts_escalations_without_duplicating_shared_followups -m 'not slow' --tb=short -q
.                                                                        [100%]
1 passed in 0.67s
exit=0
