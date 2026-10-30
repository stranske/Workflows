# Verifier context

## Context source coverage

```json
{"schema": "verifier-context-source-coverage/v1", "stage": "generated-context", "changed_code_sources": [{"source": "square.py", "status": "included", "included_chars": 324, "total_chars": 324}], "acceptance_sources": [{"source": "synthetic-public-spec", "status": "included", "included_chars": 195, "total_chars": 195}], "acceptance_evidence_sources": [], "acceptance_source_discovery": {"required": false, "status": "included"}, "full_diff_artifact": {"source": "verifier-pr-diff.patch", "status": "included", "chars": 324}}
```

## CI Information
No execution or CI result is supplied or claimed; review the complete source below.

## Plan sources (scope, tasks, acceptance)
#### Acceptance criteria
- Add square(value: int) returning value multiplied by itself for every Python integer, including negative values.
- Include unit assertions for zero, a negative integer, and a positive integer.

## PR Diff Summary
- Files changed: 1

### File changes
- square.py (+10/-0)

## PR Diff (full)

```diff
diff --git a/square.py b/square.py
new file mode 100644
--- /dev/null
+++ b/square.py
@@ -0,0 +1,9 @@
+def square(value: int) -> int:
+    """Return the mathematical square of an integer."""
+    return value * value
+
+
+def test_square():
+    assert square(0) == 0
+    assert square(-3) == 9
+    assert square(4) == 16
```
