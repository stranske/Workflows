# ignore-branches

Command: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget -m 'not slow' -q`

## Deliberate change
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -121,7 +121,7 @@
         print(f"invalid coverage: {exc}", file=sys.stderr)
         return 2
     print(json.dumps(stats, indent=2, sort_keys=True))
-    total_missing = sum(stats[t]["missing_lines"] + stats[t]["missing_branches"] for t in TARGETS)
+    total_missing = sum(stats[t]["missing_lines"] for t in TARGETS)
     print(f"combined_missing_units={total_missing}", file=sys.stderr)
     if args.max_missing is not None and total_missing > args.max_missing:
         print(f"coverage budget exceeded: {total_missing} > {args.max_missing}", file=sys.stderr)
```

## Broken result
```text
FFFF                                                                     [100%]
=================================== FAILURES ===================================
_____________ test_cli_enforces_inclusive_missing_unit_budget[0-1] _____________

reports = (PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi0/coverage.json'), PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi0/coverage.xml'))
limit = 0, expected_status = 1

    @pytest.mark.parametrize("limit,expected_status", [(0, 1), (8, 1), (9, 0), (10, 0)])
    def test_cli_enforces_inclusive_missing_unit_budget(reports, limit, expected_status):
        json_path, xml_path = reports
        result = cli(json_path, "--xml", xml_path, "--max-missing", limit)
        assert result.returncode == expected_status, result.stderr
        assert json.loads(result.stdout) == {
            target: {"missing_lines": 1, "missing_branches": 2, "percent_covered": 25.0}
            for target in extractor.TARGETS
        }
        expected_error = "combined_missing_units=9\n"
        if expected_status:
            expected_error += f"coverage budget exceeded: 9 > {limit}\n"
>       assert result.stderr == expected_error
E       AssertionError: assert 'combined_mis...eded: 3 > 0\n' == 'combined_mis...eded: 9 > 0\n'
E         
E         - combined_missing_units=9
E         ?                        ^
E         + combined_missing_units=3
E         ?                        ^
E         - coverage budget exceeded: 9 > 0
E         ?                           ^
E         + coverage budget exceeded: 3 > 0
E         ?                           ^

tests/scripts/test_issue_4001_target_coverage.py:92: AssertionError
_____________ test_cli_enforces_inclusive_missing_unit_budget[8-1] _____________

reports = (PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi1/coverage.json'), PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi1/coverage.xml'))
limit = 8, expected_status = 1

    @pytest.mark.parametrize("limit,expected_status", [(0, 1), (8, 1), (9, 0), (10, 0)])
    def test_cli_enforces_inclusive_missing_unit_budget(reports, limit, expected_status):
        json_path, xml_path = reports
        result = cli(json_path, "--xml", xml_path, "--max-missing", limit)
>       assert result.returncode == expected_status, result.stderr
E       AssertionError: combined_missing_units=3
E         
E       assert 0 == 1
E        +  where 0 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...ng_branches": 2,\n    "missing_lines": 1,\n    "percent_covered": 25.0\n  }\n}\n', stderr='combined_missing_units=3\n').returncode

tests/scripts/test_issue_4001_target_coverage.py:84: AssertionError
_____________ test_cli_enforces_inclusive_missing_unit_budget[9-0] _____________

reports = (PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi2/coverage.json'), PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi2/coverage.xml'))
limit = 9, expected_status = 0

    @pytest.mark.parametrize("limit,expected_status", [(0, 1), (8, 1), (9, 0), (10, 0)])
    def test_cli_enforces_inclusive_missing_unit_budget(reports, limit, expected_status):
        json_path, xml_path = reports
        result = cli(json_path, "--xml", xml_path, "--max-missing", limit)
        assert result.returncode == expected_status, result.stderr
        assert json.loads(result.stdout) == {
            target: {"missing_lines": 1, "missing_branches": 2, "percent_covered": 25.0}
            for target in extractor.TARGETS
        }
        expected_error = "combined_missing_units=9\n"
        if expected_status:
            expected_error += f"coverage budget exceeded: 9 > {limit}\n"
>       assert result.stderr == expected_error
E       AssertionError: assert 'combined_missing_units=3\n' == 'combined_missing_units=9\n'
E         
E         - combined_missing_units=9
E         ?                        ^
E         + combined_missing_units=3
E         ?                        ^

tests/scripts/test_issue_4001_target_coverage.py:92: AssertionError
____________ test_cli_enforces_inclusive_missing_unit_budget[10-0] _____________

reports = (PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi3/coverage.json'), PosixPath('/tmp/pytest-of-runner/pytest-6/test_cli_enforces_inclusive_mi3/coverage.xml'))
limit = 10, expected_status = 0

    @pytest.mark.parametrize("limit,expected_status", [(0, 1), (8, 1), (9, 0), (10, 0)])
    def test_cli_enforces_inclusive_missing_unit_budget(reports, limit, expected_status):
        json_path, xml_path = reports
        result = cli(json_path, "--xml", xml_path, "--max-missing", limit)
        assert result.returncode == expected_status, result.stderr
        assert json.loads(result.stdout) == {
            target: {"missing_lines": 1, "missing_branches": 2, "percent_covered": 25.0}
            for target in extractor.TARGETS
        }
        expected_error = "combined_missing_units=9\n"
        if expected_status:
            expected_error += f"coverage budget exceeded: 9 > {limit}\n"
>       assert result.stderr == expected_error
E       AssertionError: assert 'combined_missing_units=3\n' == 'combined_missing_units=9\n'
E         
E         - combined_missing_units=9
E         ?                        ^
E         + combined_missing_units=3
E         ?                        ^

tests/scripts/test_issue_4001_target_coverage.py:92: AssertionError
=========================== short test summary info ============================
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget[0-1] - AssertionError: assert 'combined_mis...eded: 3 > 0\n' == 'combined_mis...eded: 9 > 0\n'
  
  - combined_missing_units=9
  ?                        ^
  + combined_missing_units=3
  ?                        ^
  - coverage budget exceeded: 9 > 0
  ?                           ^
  + coverage budget exceeded: 3 > 0
  ?                           ^
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget[8-1] - AssertionError: combined_missing_units=3
  
assert 0 == 1
 +  where 0 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...ng_branches": 2,\n    "missing_lines": 1,\n    "percent_covered": 25.0\n  }\n}\n', stderr='combined_missing_units=3\n').returncode
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget[9-0] - AssertionError: assert 'combined_missing_units=3\n' == 'combined_missing_units=9\n'
  
  - combined_missing_units=9
  ?                        ^
  + combined_missing_units=3
  ?                        ^
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_enforces_inclusive_missing_unit_budget[10-0] - AssertionError: assert 'combined_missing_units=3\n' == 'combined_missing_units=9\n'
  
  - combined_missing_units=9
  ?                        ^
  + combined_missing_units=3
  ?                        ^
4 failed in 1.00s

exit=1
```

## Exact reversion
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -121,7 +121,7 @@
         print(f"invalid coverage: {exc}", file=sys.stderr)
         return 2
     print(json.dumps(stats, indent=2, sort_keys=True))
-    total_missing = sum(stats[t]["missing_lines"] for t in TARGETS)
+    total_missing = sum(stats[t]["missing_lines"] + stats[t]["missing_branches"] for t in TARGETS)
     print(f"combined_missing_units={total_missing}", file=sys.stderr)
     if args.max_missing is not None and total_missing > args.max_missing:
         print(f"coverage budget exceeded: {total_missing} > {args.max_missing}", file=sys.stderr)
```
Restored SHA-256: `f2d2b9c8de02855fa6bc5413b842c9fee2585abcad4f458984a2014976869a95`

## Restored result
```text
....                                                                     [100%]
4 passed in 0.90s

exit=0
```
