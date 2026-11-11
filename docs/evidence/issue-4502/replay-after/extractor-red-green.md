# Extractor deliberate-break and restoration checks

## XML branch-count regression

Deliberate break:
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -96,7 +96,7 @@
                 covered, total = map(int, match.groups())
                 if not 0 <= covered <= total or total == 0:
                     raise ValueError(f"{target}: invalid XML branch counts {condition!r}")
-                missing_branches += total - covered
+                missing_branches += total - covered + 1
         actual = (missing_lines, missing_branches)
         expected = (stats[target]["missing_lines"], stats[target]["missing_branches"])
         if actual != expected:
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports -m 'not slow' --tb=short -q
FFFF                                                                     [100%]
=================================== FAILURES ===================================
___ test_cli_reproduces_counts_from_plain_or_compressed_reports[False-False] ___
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
___ test_cli_reproduces_counts_from_plain_or_compressed_reports[False-True] ____
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
___ test_cli_reproduces_counts_from_plain_or_compressed_reports[True-False] ____
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
____ test_cli_reproduces_counts_from_plain_or_compressed_reports[True-True] ____
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
=========================== short test summary info ============================
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[False-False] - AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[False-True] - AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[True-False] - AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[True-True] - AssertionError: invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...'', stderr='invalid coverage: scripts/aggregate_agent_metrics.py: XML missing counts (1, 3) differ from JSON (1, 2)\n').returncode
4 failed in 1.05s
exit=1

Exact reversion:
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -96,7 +96,7 @@
                 covered, total = map(int, match.groups())
                 if not 0 <= covered <= total or total == 0:
                     raise ValueError(f"{target}: invalid XML branch counts {condition!r}")
-                missing_branches += total - covered + 1
+                missing_branches += total - covered
         actual = (missing_lines, missing_branches)
         expected = (stats[target]["missing_lines"], stats[target]["missing_branches"])
         if actual != expected:
```
Restored SHA-256: 67004ae2669acbbf8244bf0d4b7769b4b456c98b7fa3294725f0d5a34abe780b

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports -m 'not slow' --tb=short -q
....                                                                     [100%]
4 passed in 0.98s
exit=0

## Compressed-input regression

Deliberate break:
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -24,7 +24,7 @@
 def read_report(path: Path) -> bytes:
     """Read a complete retained report, optionally compressed with gzip."""
     if path.suffix == ".gz":
-        return gzip.decompress(path.read_bytes())
+        return path.read_bytes()
     return path.read_bytes()
 
 
```

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports -m 'not slow' --tb=short -q
.FFF                                                                     [100%]
=================================== FAILURES ===================================
___ test_cli_reproduces_counts_from_plain_or_compressed_reports[False-True] ____
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...code=2, stdout='', stderr="invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte\n").returncode
___ test_cli_reproduces_counts_from_plain_or_compressed_reports[True-False] ____
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: not well-formed (invalid token): line 1, column 0
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...rage.xml.gz'], returncode=2, stdout='', stderr='invalid coverage: not well-formed (invalid token): line 1, column 0\n').returncode
____ test_cli_reproduces_counts_from_plain_or_compressed_reports[True-True] ____
tests/scripts/test_issue_4001_target_coverage.py:65: in test_cli_reproduces_counts_from_plain_or_compressed_reports
    assert result.returncode == 0, result.stderr
E   AssertionError: invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte
E     
E   assert 2 == 0
E    +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...code=2, stdout='', stderr="invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte\n").returncode
=========================== short test summary info ============================
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[False-True] - AssertionError: invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...code=2, stdout='', stderr="invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte\n").returncode
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[True-False] - AssertionError: invalid coverage: not well-formed (invalid token): line 1, column 0
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...rage.xml.gz'], returncode=2, stdout='', stderr='invalid coverage: not well-formed (invalid token): line 1, column 0\n').returncode
FAILED tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports[True-True] - AssertionError: invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte
  
assert 2 == 0
 +  where 2 = CompletedProcess(args=['/opt/hostedtoolcache/Python/3.14.10/x64/bin/python', '/home/runner/work/Workflows/Workflows/do...code=2, stdout='', stderr="invalid coverage: 'utf-8' codec can't decode byte 0x8b in position 1: invalid start byte\n").returncode
3 failed, 1 passed in 1.06s
exit=1

Exact reversion:
```diff
--- docs/evidence/issue-4001/extract_target_coverage.py
+++ docs/evidence/issue-4001/extract_target_coverage.py
@@ -24,7 +24,7 @@
 def read_report(path: Path) -> bytes:
     """Read a complete retained report, optionally compressed with gzip."""
     if path.suffix == ".gz":
-        return path.read_bytes()
+        return gzip.decompress(path.read_bytes())
     return path.read_bytes()
 
 
```
Restored SHA-256: 67004ae2669acbbf8244bf0d4b7769b4b456c98b7fa3294725f0d5a34abe780b

$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_issue_4001_target_coverage.py::test_cli_reproduces_counts_from_plain_or_compressed_reports -m 'not slow' --tb=short -q
....                                                                     [100%]
4 passed in 1.00s
exit=0
