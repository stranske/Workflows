# dev_check.sh Evaluation

## Status: ✅ IMMEDIATELY ADAPTED + ⏳ DEFERRED WORK TRACKED

**Copied from:** `stranske/Trend_Model_Project` scripts/dev_check.sh (305 lines)  
**Purpose:** Ultra-fast development validation (2-5 second target)  
**Date Copied:** 2025-12-16  
**Date Adapted:** 2025-12-16

---

## ✅ What to Keep

### Core Structure (Preserve)
- **Tool version synchronization** (lines 16-33): PIN_FILE loading and validation
- **ensure_package_version function** (lines 35-58): Runtime version enforcement  
- **Command-line argument parsing** (lines 66-78): --fix, --changed, --verbose flags
- **Timeout protection** (lines 63, 80, 192-194): DEV_CHECK_TIMEOUT with 120s default
- **Auto-fix with recheck logic** (lines 207-218): Attempt fix, then re-validate
- **Color-coded output** (lines 8-13): User-friendly terminal display
- **quick_check function** (lines 176-242): Reusable check executor with error handling

### Timing Target
- 2-5 seconds for rapid development feedback ✅
- 25s timeout for --changed mode (line 80) ✅

---
✅ Immediate Adaptations (Completed 2025-12-16)

| Component | Action Taken | Lines Modified |
|-----------|--------------|----------------|
| **BLACK_TARGETS** | Removed `streamlit_app`, replaced `src tests` with `scripts .github` | Line 65 |
| **Exclusion patterns** | Simplified to `archive/ .extraction/` | Lines 153, 160 |
| **Directory targets** | Changed from `src/ tests/ scripts/` to `scripts/ .github/` | Line 174 |
| **Flake8 targets** | Removed `src/ tests/`, kept `scripts/` only | Line 273 |

- Replaced with TODO marker and yellow warning message
- Will add `actionlint` or `yamllint` validation

**Line 260: Import test** - Commented out with TODO  
- Replaced with TODO marker for Phase 4 (workflow validation) and Phase 5 (keepalive scripts)
- Will add `node --check scripts/keepalive-runner.js` when available

**Line 284: Type checking** - Commented out with TODO`, keep `scripts` and `.github`

**Lines 153-155: Exclusion patterns**
```bash
grep -v -E '^(Old/|notebooks/old/|archives/|archives/legacy_assets/)'
```
**Reason:** Trend_Model_Project-specific legacy folders  
**Action:** Simplify or remove (workflow repo won't have these)

**Line 254: Syntax check target**
```bash
quick_check "Syntax check" "python -m compileall src/ -q" ""
```
**Reason:** `src/` directory is Python package-specific  
**Action:** Replace with workflow file validation

**Lines 273-278: Linting targets**
```bash
- Replaced with TODO marker
- Will add `actionlint --verbose` for workflow validation

### Phase 5: Keepalive System (Week 10-12)

**Line 296: Keepalive test** - Commented out with TODO
## 🔧 What to Adapt

### Workflow-Specific Validation

**Replace Python validation with:**

1. **YAML Syntax Check** (replace line 254):
   ```bash
   # Validate workflow YAML syntax
   yamllint .github/workflows/*.yml
   # OR
   actionlint .github/workflows/*.yml
   ```

2. **JavaScript Validation for Keepalive Scripts** (replace line 260):
- Test path will be updated when keepalive system extracted
- Will validate `scripts/keepalive-runner.js` with Node.js

### Phase 1 Completion: Tool Sync Infrastructure

**Lines 17-22, 132-140: Tool version synchronization**
- Script references `.github/workflows/autofix-versions.env` (not yet extracted)
- Script calls `python -m scripts.sync_tool_versions` (not yet extracted)
- **Status:** Will work after remaining Phase 1 files copied

---

## 🎯 Current Script Status

### ✅ Usable Now (With Warnings)
- Core infrastructure works (timeout, recheck, auto-fix patterns)
- Black formatting for scripts/ and .github/ directories
- Flake8 linting for scripts/ directory  
- Git change detection

### ⚠️ Displays Warnings (Expected)
- "Workflow validation deferred to Phase 4" - where Python validation was removed
- "Type checking deferred to Phase 4" - where mypy was removed
- "Keepalive tests deferred to Phase 5" - test not yet extracted

### ❌ Will Fail If Run
- **Missing dependency:** `.github/workflows/autofix-versions.env` (being extracted in Phase 1)
- **Missing dependency:** `scripts/sync_tool_versions.py` (being extracted in Phase 1)

---

## 🔧 Original "What to Adapt" Section (Now Completed)bose
   ```

4. **Formatting for Scripts** (lines 262-269 - adapt):
   ```bash
   # Keep Black for Python helper scripts
   # Add Prettier for YAML/JavaScript if needed
   BLACK_TARGETS="scripts .github"
   ```

### Directory Targets

**Line 174: Change detection** (adapt):
```bash
# Replace:
ALL_FILES="src/ tests/ scripts/"
# With:
ALL_FILES="scripts/ .github/"
```

**Line 153: Exclusion patterns** (simplify):
```bash
# Replace:
grep -v -E '^(Old/|notebooks/old/|archives/|archives/legacy_assets/)'
# With:
grep -v -E '^(archive/|\.extraction/)'
```

### Configuration Flexibility

**Make targets configurable via environment variables:**
- `WORKFLOW_VALIDATION_DIRS="${WORKFLOW_VALIDATION_DIRS:-.github/workflows scripts}"` 
- `WORKFLOW_FORMATS="${WORKFLOW_FORMATS:-yml yaml js}"` 

---

## 📊 Updated Generalization Strategy

### Phase 1 (Current - Week 2-3) - ✅ COMPLETED IMMEDIATE WORK
1. ✅ Copy script from source (305 lines)
2. ✅ Remove obvious project-specific elements (streamlit_app, src/, tests/, exclusion patterns)
3. ✅ Update directory targets for workflow repo structure
4. ✅ Add TODO markers for deferred work
5. ✅ Document deferred adaptations in PHASE1_DEFERRED_ADAPTATIONS.md
6. ⏳ Extract remaining Phase 1 dependencies (autofix-versions.env, sync_tool_versions.py)

### Phase 4 (Week 7-9: Workflow System) - DEFERRED WORK
**Tracked in:** PHASE1_DEFERRED_ADAPTATIONS.md  
**Time Estimate:** ~4 hours

Search for TODO markers: `grep "TODO Phase 4" scripts/dev_check.sh`

Actions:
1. Replace syntax check (line ~254) with actionlint/yamllint
2. Replace import test (line ~260) with workflow validation
3. Replace type check (line ~284) with actionlint --verbose
4. Test timing target (must maintain 2-5s)

### Phase 5 (Week 10-12: Keepalive System) - DEFERRED WORK
**Tracked in:** PHASE1_DEFERRED_ADAPTATIONS.md  
**Time Estimate:** ~2 hours

Search for TODO markers: `grep "TODO Phase 5" scripts/dev_check.sh`

Actions:
1. Update keepalive test path (line ~296)
2. Add `node --check scripts/keepalive-runner.js` validation
3. Ensure timing target maintained

---Updated Readiness Assessment

| Component | Status | Blocker |
|-----------|--------|---------|
| Core infrastructure | ✅ Ready | None |
| Directory targets | ✅ Adapted | None |
| Formatting (Black) | ✅ Adapted | None |
| Linting (Flake8) | ✅ Adapted | None |
| Workflow validation | ⏳ Deferred | Phase 4 (actionlint/yamllint) |
| Type checking | ⏳ Deferred | Phase 4 (workflow validation) |
| Tool version sync | ❌ Blocked | Need autofix-versions.env + sync_tool_versions.py |
| Keepalive tests | ⏳ Deferred | Phase 5 (keepalive extraction) |
| Timing target | ⚠️ Unknown | Test after Phase 4 adaptations |

**Overall:** Script immediately adapted where possible. Core infrastructure ready. Deferred work clearly marked with TODO comments and tracked in PHASE1_DEFERRED_ADAPTATIONS.md. Script will be fully functional after Phase 1 completes (tool sync infrastructure) and Phase 4 adds workflow validation

---

## 🚦 Readiness Assessment

| Component | Status | Blocker |
|-----------|--------|---------|
| Core infrastructure | ✅ Ready | None |
| Python-specific validation | ❌ Requires replacement | Need workflow validation approach (Phase 4) |
| Tool version sync | ⚠️ Partial | Need sync_tool_versions.py extracted |
| Keepalive tests | ❌ Not applicable yet | Keepalive system not extracted (Phase 5) |
| Timing target | ⚠️ Unknown | Need workflow-specific validation benchmarks |

**Overall:** Script copied successfully but NOT ready for use. Requires Phase 4 (Workflow System) completion to define replacement validation logic.

---

## 📋 Next Steps

1. ✅ **Copy validate_fast.sh** (next file in Phase 1)
2. ✅ **Copy check_branch.sh** (third file in Phase 1)
3. ⬜ **Copy autofix-versions.env** (tool version pins)
4. ⬜ **Copy sync_tool_versions.py** (version sync infrastructure)
5. ⬜ **Wait for Phase 4** - define workflow-specific validation
6. ⬜ **Adapt dev_check.sh** - replace Python validation with workflow validation
7. ⬜ **Test timing** - verify 2-5s target maintained

---

## 📝 Notes

- **Do not use this script yet** - contains hardcoded Trend_Model_Project references
- Timing infrastructure (timeout, recheck) is solid and should be preserved
- Auto-fix patterns are excellent and should remain
- Consider: Do we need Python validation at all for a workflows-only repo? Most validation may be YAML/JavaScript-based.
