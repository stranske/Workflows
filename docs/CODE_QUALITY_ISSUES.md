# Code Quality Issues

Tracked issues from Copilot code reviews and other sources. Fix all at once after sync PR merges complete.

## From PR #163 (Travel-Plan-Permission sync)

### 1. Redundant Ternary Operators in `agents-guard.yml` (3 instances)

**File:** `.github/workflows/agents-guard.yml`  
**Lines:** ~85-126, ~304-343, ~432-471  
**Priority:** Low

```javascript
// Current (redundant):
const remaining = typeof remainingRaw === 'string' ? Number(remainingRaw) : Number(remainingRaw);
const reset = typeof resetRaw === 'string' ? Number(resetRaw) : Number(resetRaw);

// Should be:
const remaining = Number(remainingRaw);
const reset = Number(resetRaw);
```

`Number()` handles both string and number inputs correctly.

---

### 2. DRY Violation: `withApiRetry` Defined 3 Times

**File:** `.github/workflows/agents-guard.yml`  
**Priority:** Medium

The `withApiRetry` function and `sleep` helper are copy-pasted in three separate workflow steps. Should be extracted to `.github/scripts/agents-guard.js` and imported once.

---

### 3. tomlkit `isinstance(x, dict)` Check Fails

**File:** `tools/resolve_mypy_pin.py`  
**Priority:** High

```python
# Current (broken with tomlkit):
tool = data.get("tool")
if not isinstance(tool, dict):
    tool = {}
mypy = tool.get("mypy")
if not isinstance(mypy, dict):
    mypy = {}

# Should be (duck typing):
tool = data.get("tool")
if not hasattr(tool, "get"):
    tool = {}
mypy = tool.get("mypy")
if not hasattr(mypy, "get"):
    mypy = {}
```

tomlkit returns `tomlkit.items.Table` objects which support `.get()` but are not instances of `dict`.

---

## From PR #164 (Travel-Plan-Permission sync)

### 4. Missing Indentation in `authorIsCodeowner` Return

**File:** `.github/scripts/agents-guard.js`  
**Priority:** Low

```javascript
// Current (2 spaces):
  authorIsCodeowner,

// Should be (4 spaces to match siblings):
    authorIsCodeowner,
```

---

### 5. Inconsistent Indentation in Array Literal

**File:** `.github/scripts/agents-guard.js`  
**Priority:** Low

Array element has 2 spaces instead of 6 spaces to align with other elements.

---

### 6. Type Validation for `python_version` Before `str()`

**File:** `tools/resolve_mypy_pin.py`  
**Priority:** Medium

```python
# Current:
return str(version) if version is not None else None

# Should be (validate type first):
if isinstance(version, (str, int, float)):
    return str(version)
return None
```

The `python_version` could be parsed as various types from TOML. Validate before converting.

---

## Summary

| Issue | File | Priority | Status |
|-------|------|----------|--------|
| Redundant ternary (×3) | agents-guard.yml | Low | ✅ Fixed |
| withApiRetry duplication | agents-guard.yml | Medium | ⬚ Open |
| tomlkit isinstance (×2) | resolve_mypy_pin.py | High | ✅ Fixed |
| Missing indentation | agents-guard.js | Low | ✅ Fixed |
| Inconsistent array indentation | agents-guard.js | Low | ✅ Fixed |
| Type validation python_version | resolve_mypy_pin.py | Medium | ✅ Fixed |
| Redundant instructions reassignment | agents-guard.js | Low | ✅ Fixed |
| Typo in numbered list comment | issue_scope_parser.js | Low | ⬚ N/A (not found) |
| Same typo in keepalive_loop.js | keepalive_loop.js | Low | ✅ Fixed |

---

## From PR #100 (Manager-Database sync)

### 7. Redundant `instructions = []` Reassignment

**File:** `.github/scripts/issue_scope_parser.js`  
**Line:** ~483  
**Priority:** Low

```javascript
// Current (redundant):
let instructions = [];
if (condition) {
  instructions = [];  // This is redundant
  ...
}

// Should be: Remove the redundant reassignment
```

---

### 8. Typo in Numbered List Comment

**File:** `.github/scripts/issue_scope_parser.js`  
**Priority:** Low

```javascript
// Current (inconsistent):
// Match bullet points (-, *, +) or numbered lists (1., 2), 3.))

// Should be:
// Match bullet points (-, *, +) or numbered lists (1., 2., 3.)
```

---

## From PR #37 (Template sync)

### 9. Same Typo in keepalive_loop.js

**File:** `.github/scripts/keepalive_loop.js`  
**Line:** ~193  
**Priority:** Low

```javascript
// Current (typo - "2]" should be "2."):
// Match bullet points (-, *, +) or numbered lists (1., 2), 3.)

// Should be:
// Match bullet points (-, *, +) or numbered lists (e.g. 1., 2., 3))
```

Same typo pattern as issue #8 - inconsistent parenthesis in numbered list examples.

---

## Notes

- All issues should be fixed in **stranske/Workflows** (source repo)
- After fixing, trigger sync to propagate to consumer repos
- Created: 2026-01-01
