# Grouped shared-span join regression

The existing loader accepted join declarations listing multiple span IDs but checked shared spans only against singleton declaration tuples. The two-span complete execution fixture fails before the repair with `shared evidence span lacks an exact declared join`. After indexing each member of an already ownership-validated group, the same capture prepares both prompts with both exact shared byte spans. Missing-span and wrong-owner controls continue to reject.

Commands: `python3 -m pytest tests/tools/test_verifier_semantic_rules.py -q` (pre-fix: 1 failed,12 passed); final focused semantic loader/execution/acceptance/package-recovery/integration suite:71 passed. Source/template sync and completeness outputs retained. This fixture is a regression control, not a claim that the empty production registry contains a failing deployed capture. Original root3820 acceptance and live missing evidence remain unchanged.
