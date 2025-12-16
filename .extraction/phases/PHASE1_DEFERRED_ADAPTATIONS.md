# Phase 1: Deferred Adaptations Tracker

**Purpose:** Track validation script adaptations that cannot be completed until later phases.

**Last Updated:** 2025-12-16

---

## 🎯 Adaptation Status Legend

- ✅ **Completed Now** - Adapted immediately during Phase 1
- ⏳ **Deferred to Phase 4** - Requires workflow validation approach (Week 7-9)
- ⏳ **Deferred to Phase 5** - Requires keepalive system (Week 10-12)
- ⚠️ **Blocked** - Cannot proceed without dependency

---

## scripts/dev_check.sh (305 lines)

### ✅ Immediate Adaptations (Completed)

| Line(s) | Original | Adapted | Reason |
|---------|----------|---------|--------|
| 65 | `BLACK_TARGETS="src tests scripts streamlit_app"` | `BLACK_TARGETS="scripts .github"` | Removed project-specific `streamlit_app`, replaced `src tests` with workflow dirs |
| 153-155 | `grep -v -E '^(Old/\|notebooks/old/\|archives/\|archives/legacy_assets/)'` | `grep -v -E '^(archive/\|\.extraction/)'` | Simplified to workflow repo structure |
| 174 | `ALL_FILES="src/ tests/ scripts/"` | `ALL_FILES="scripts/ .github/"` | Updated directory targets for workflow repo |
| 254 | `python -m compileall src/ -q` | Removed (see deferred) | Python package structure doesn't apply |
| 260 | `python -c 'import src.trend_analysis'` | Removed (see deferred) | Project-specific import |
| 273 | `flake8 src/ tests/ scripts/` | `flake8 scripts/` | Removed `src/ tests/` Python package dirs |
| 284 | `mypy src/` | Removed (see deferred) | Python package type checking |

### ⏳ Deferred to Phase 4: Workflow System (Week 7-9)

**Blocker:** Need to define workflow-specific validation approach

| Validation Type | Current Behavior | Planned Replacement | File/Line |
|----------------|------------------|---------------------|-----------|
| **Syntax Check** | `python -m compileall src/` | `actionlint .github/workflows/*.yml` OR `yamllint` | Line 254 |
| **Import Test** | `python -c 'import src.trend_analysis'` | `node --check scripts/keepalive-runner.js` (if exists) | Line 260 |
| **Type Check** | `mypy src/` | `actionlint --verbose` for workflow validation | Line 284 |

**Action Required in Phase 4:**
1. Decide on workflow validation tooling (actionlint vs yamllint vs custom)
2. Add validation checks in TODO-marked sections (lines 254, 260, 284)
3. Benchmark timing - must maintain 2-5s target

### ⏳ Deferred to Phase 5: Keepalive System (Week 10-12)

**Blocker:** Keepalive system not yet extracted

| Component | Current Status | Required Action | File/Line |
|-----------|---------------|-----------------|-----------|
| **Keepalive Test** | `pytest tests/workflows/test_keepalive_workflow.py` | Update path to match extracted structure | Line 296 |
| **Node.js Validation** | Skipped if Node missing | Add JavaScript validation for keepalive runner | Line 295-299 |

**Action Required in Phase 5:**
1. Update test path when keepalive tests extracted
2. Add `node --check scripts/keepalive-runner.js` validation
3. Ensure Node.js availability check remains

### ⏳ Deferred to Phase 1 Completion (Week 2-3)

**Blocker:** Need to extract sync_tool_versions.py first

| Component | Current Issue | Required Action | File/Line |
|-----------|--------------|-----------------|-----------|
| **Tool Version Sync** | `python -m scripts.sync_tool_versions` | Works after sync script extracted | Line 132-140 |
| **PIN_FILE** | `.github/workflows/autofix-versions.env` | Works after autofix-versions.env extracted | Line 17-22 |

**Action Required:**
1. Copy `.github/workflows/autofix-versions.env` (next in Phase 1)
2. Copy `scripts/sync_tool_versions.py` (next in Phase 1)
3. Test integration

---

## scripts/validate_fast.sh (439 lines)

### ✅ Immediate Adaptations (Completed)

| Line(s) | Original | Adapted | Reason |
|---------|----------|---------|--------|
| 133 | `grep -v -E '^(Old/\|notebooks/old/\|archives/legacy_assets/)'` | `grep -v -E '^(archive/\|\.extraction/)'` | Simplified exclusion patterns |
| 269 | `FORMAT_SCOPE="src tests scripts"` | `FORMAT_SCOPE="scripts .github"` | Updated directory targets |
| 257 | `python -c 'import src.trend_analysis'` | Commented with TODO | Project-specific import removed |
| 330, 374, 377 | `flake8 src/ tests/ scripts/` | `flake8 scripts/` | Removed Python package dirs |

### ⏳ Deferred to Phase 4: Workflow System (Week 7-9)

**Blocker:** Need to define workflow-specific validation approach

| Validation Type | Current Behavior | Planned Replacement | File/Line |
|----------------|------------------|---------------------|-----------|
| **Import Test** | `python -c 'import src.trend_analysis'` | Workflow YAML validation or Node.js validation | Line 257 |
| **SRC_FILES Detection** | Detects `^src/` Python files | Remove or replace with `.github/workflows/` detection | Lines 138, 146, 164, 308 |
| **AUTOFIX_FILES Detection** | Detects project-specific autofix scripts | Remove entirely (not applicable) | Lines 141, 156-159, 322, 362, 421 |
| **Type Checking (Incremental)** | `mypy` on limited source files | `actionlint` or workflow validation | Lines 308-315 |
| **Type Checking (Comprehensive/Full)** | `mypy src/` | `actionlint --verbose` | Lines 337-341, 382-386 |
| **Test Coverage** | `pytest --cov=src --cov-fail-under=80` | Remove (not applicable to workflows) | Lines 406-410 |

**Action Required in Phase 4:**
1. Remove or adapt `SRC_FILES` detection logic (lines 138, 146, 164)
2. Remove `AUTOFIX_FILES` detection entirely (lines 141, 156-159)
3. Add workflow validation in TODO-marked sections
4. Update strategy selection logic if needed (line 178-181)
5. Test timing targets (5-30s adaptive strategy)

### ⏳ Deferred to Phase 1 Completion (Week 2-3)

**Blocker:** Need to extract sync_tool_versions.py first

| Component | Current Issue | Required Action | File/Line |
|-----------|--------------|-----------------|-----------|
| **Tool Version Sync** | `python -m scripts.sync_tool_versions` | Works after sync script extracted | Line 117-126 |
| **PIN_FILE** | `.github/workflows/autofix-versions.env` | Works after autofix-versions.env extracted | Line 18-33 |

---

## scripts/check_branch.sh (274 lines)

### ✅ Immediate Adaptations (Completed)

| Line(s) | Original | Adapted | Reason |
|---------|----------|---------|--------|
| 180 | `black --check .` | `black --check scripts/ .github/` | Updated directory targets |
| 180 | `black .` | `black scripts/ .github/` | Updated directory targets for auto-fix |
| 185 | `flake8 src/ tests/ scripts/` | `flake8 scripts/` | Removed Python package directories |
| 57-67 | Virtual environment check | Added TODO Phase 4 | May not need venv for pure workflow repo |

### ⏳ Deferred to Phase 4: Workflow System (Week 7-9)

**Blocker:** Need to define comprehensive workflow validation approach

| Validation Type | Current Behavior | Planned Replacement | File/Line |
|----------------|------------------|---------------------|-----------|
| **Type Checking** | `mypy src/` | `actionlint` or workflow validation tool | Lines 188-192 |
| **Package Installation** | `pip install -e .` | Remove (not applicable) | Lines 196-200 |
| **Import Validation** | `python -c 'import src.trend_analysis'` | Workflow YAML validation | Lines 203-207 |
| **Test Coverage** | `pytest --cov=src --cov-fail-under=80` | Remove (Python package specific) | Lines 227-231 |

**Action Required in Phase 4:**
1. Add workflow-specific validation in commented sections
2. Consider if venv check needed for workflow repo (line 57-67)
3. Decide on test strategy for workflow validation
4. Update recommendations section (lines 268-274) for workflow context
5. Test timing targets (30-120s comprehensive validation)

### ⏳ Deferred to Phase 1 Completion (Week 2-3)

**Blocker:** Need to extract sync_tool_versions.py first

| Component | Current Issue | Required Action | File/Line |
|-----------|--------------|-----------------|-----------|
| **Tool Version Sync** | `python -m scripts.sync_tool_versions` | Works after sync script extracted | Line 96-106 |
| **PIN_FILE** | `.github/workflows/autofix-versions.env` | Works after autofix-versions.env extracted | Line 17-20 |

---

## 📊 Timeline Summary

| Phase | Week | Deferred Work | Est. Time |
|-------|------|--------------|-----------|
| **Phase 1** (current) | Week 2-3 | Complete tool sync infrastructure | 1 hour |
| **Phase 4** | Week 7-9 | Replace Python validation with workflow validation (all 3 scripts) | 6 hours |
| **Phase 5** | Week 10-12 | Update keepalive test paths and validation | 2 hours |

**Total Deferred Work:** ~9 hours spread across 3 phases

**Scripts Completed:**
- ✅ dev_check.sh (305 lines) - Immediate adaptations done + TODO markers added
- ✅ validate_fast.sh (439 lines) - Immediate adaptations done + TODO markers added
- ✅ check_branch.sh (274 lines) - Immediate adaptations done + TODO markers added

**All validation scripts extracted and immediately adapted!**

---

## Tool Sync Infrastructure

### ✅ Files Extracted (Completed)

| File | Lines | Status |
|------|-------|--------|
| `.github/workflows/autofix-versions.env` | 9 | ✅ Copied verbatim - no adaptation needed |
| `scripts/sync_tool_versions.py` | 189 | ✅ Copied with fallback logging (line 177-185) |

### ⏳ Deferred to Phase 4: Logging Infrastructure (Week 7-9)

**Blocker:** Need to decide on logging approach for workflow repository

| Component | Current Behavior | Planned Replacement | File/Line |
|-----------|------------------|---------------------|-----------|
| **Script Logging** | `from trend_analysis.script_logging import setup_script_logging` | Simple logging or workflow-specific logging module | sync_tool_versions.py:177-181 |

**Action Required in Phase 4:**
1. Create minimal logging infrastructure or use stdlib only
2. Test script works with fallback logging
3. Consider if workflow repo needs structured logging

**Immediate Status:** Script functional with try/except fallback to basic logging.

---

---

## 🔔 Integration Checkpoints

### Before Phase 4 Begins (Week 7)
- [ ] Review all "Deferred to Phase 4" items
- [ ] Decide on workflow validation tooling (actionlint/yamllint)
- [ ] Create validation tool version pins in autofix-versions.env
- [ ] Update all TODO markers in validation scripts

### Before Phase 5 Begins (Week 10)
- [ ] Review all "Deferred to Phase 5" items  
- [ ] Confirm keepalive test structure
- [ ] Update test paths in all three validation scripts
- [ ] Test full validation pipeline

### Phase 1 Completion (Week 3)
- [ ] Tool sync infrastructure functional
- [ ] All validation scripts copied and immediately adapted
- [ ] Timing benchmarks documented (even if using placeholder validation)

---

## 📝 Notes

- **Immediate adaptations** focus on removing clear project-specific elements
- **Deferred adaptations** require architectural decisions or missing components
- Each script maintains TODO comments pointing to this tracker
- Use `grep -r "TODO.*Phase [0-9]" scripts/` to find all deferred work
