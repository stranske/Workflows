# exclusive-limit

Command: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget -m 'not slow' -q`

## Deliberate change
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -123,7 +123,7 @@
     print(json.dumps(stats, indent=2, sort_keys=True))
     total_missing = sum(stats[t]["missing_lines"] + stats[t]["missing_branches"] for t in TARGETS)
     print(f"combined_missing_units={total_missing}", file=sys.stderr)
-    if args.max_missing is not None and total_missing > args.max_missing:
+    if args.max_missing is not None and total_missing >= args.max_missing:
         print(f"coverage budget exceeded: {total_missing} > {args.max_missing}", file=sys.stderr)
         return 1
     return 0
```

## Broken result
```text
..F.                                                                     [100%]
=================================== FAILURES ===================================
_____________ test_cli_enforces_inclusive_missing_unit_budget[9-0] _____________

reports = (PosixPath('/tmp/pytest-of-runner/pytest-4/test_cli_enforces_inclusive_mi2/coverage.json'), PosixPath('/tmp/pytest-of-runner/pytest-4/test_cli_enforces_inclusive_mi2/coverage.xml'))
limit = 9, expected_status = 0

    @pytest.mark.parametrize("limit,expected_status", [(0, 1), (8, 1), (9, 0), (10, 0)])
    def test_cli_enforces_inclusive_missing_unit_budget(reports, limit, expected_status):
        json_path, xml_path = reports
        result = cli(json_path, "--xml", xml_path, "--max-missing", limit)
>       assert result.returncode == expected_status, result.stderr
E       AssertionError: combined_missing_units=9
E         coverage budget exceeded: 9 > 9
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...nes": 1,\n    "percent_covered": 25.0\n  }\n}\n', stderr='combined_missing_units=9\ncoverage budget exceeded: 9 > 9\n').returncode

tests/scripts/test_issue_4001_target_coverage.py:84: AssertionError
=========================== short test summary info ============================
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget[9-0] - AssertionError: combined_missing_units=9
  coverage budget exceeded: 9 > 9
  
assert 1 == 0
 +  where 1 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...nes": 1,\n    "percent_covered": 25.0\n  }\n}\n', stderr='combined_missing_units=9\ncoverage budget exceeded: 9 > 9\n').returncode
1 failed, 3 passed in 0.96s

exit=1
```

## Exact reversion
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -123,7 +123,7 @@
     print(json.dumps(stats, indent=2, sort_keys=True))
     total_missing = sum(stats[t]["missing_lines"] + stats[t]["missing_branches"] for t in TARGETS)
     print(f"combined_missing_units={total_missing}", file=sys.stderr)
-    if args.max_missing is not None and total_missing >= args.max_missing:
+    if args.max_missing is not None and total_missing > args.max_missing:
         print(f"coverage budget exceeded: {total_missing} > {args.max_missing}", file=sys.stderr)
         return 1
     return 0
```
Restored SHA-256: `f2d2b9c8de02855fa6bc5413b842c9fee2585abcad4f458984a2014976869a95`

## Restored result
```text
....                                                                     [100%]
4 passed in 0.92s

exit=0
```
