# Keepalive System Transition Plan

## Executive Summary

The keepalive system is a sophisticated PR automation framework that manages iterative instruction posting, round tracking, branch synchronization, and safety guardrails. It comprises ~1,500 lines of JavaScript across multiple files, comprehensive documentation (10+ files), extensive test coverage, and workflow integration points. This document details the complete transition strategy.

## System Overview

**Purpose**: Automated PR keepalive instruction posting with round tracking, branch sync mechanisms, and guardrails to prevent runaway automation.

**Complexity**: High - central orchestration system with multiple integration points

**Dependencies**: 
- GitHub Actions workflows (3+ workflows)
- Multiple helper scripts (4 JavaScript files)
- Node.js runtime environment
- GitHub API (Octokit)
- Status tracking system (NDJSON + Markdown)

## Component Inventory

### Core Components

#### 1. Main Orchestration Script
**File**: `scripts/keepalive-runner.js` (~1,065 lines)

**Key Functions**:
- `runKeepalive()` - Main orchestration entry point
- `dispatchKeepaliveCommand()` - Handles keepalive dispatch workflow triggering
- `extractScopeTasksAcceptanceSections()` - Parses codex instruction structure
- `buildTraceToken()` - Creates unique trace identifiers for observability
- `findLatestKeepaliveComment()` - Locates most recent keepalive post
- `shouldPostKeepalive()` - Implements posting eligibility logic
- `postKeepaliveInstruction()` - Creates/updates keepalive comments

**Dependencies**:
```javascript
@actions/core
@actions/github (or @octokit/rest as fallback)
fs, path, util (Node.js built-ins)
```

**Integration Points**:
- Called by `agents-70-orchestrator.yml` (keepalive sweep job)
- Reads from `.github/templates/keepalive-instruction.md`
- Writes to `keepalive_status.md` and `docs/keepalive/status/PR-*.md`
- Triggers `agents-keepalive-dispatch-handler.yml` workflow

#### 2. Helper Scripts

**File**: `.github/scripts/keepalive_gate.js` (~300-400 lines estimated)

**Purpose**: Pre-execution gate checks and validation
**Key Functions**:
- Validates keepalive eligibility
- Checks activation guardrails
- Enforces run caps and pause controls
- Implements repeat contract verification

**File**: `.github/scripts/keepalive_post_work.js` (~200-300 lines estimated)

**Purpose**: Post-execution cleanup and state updates
**Key Functions**:
- Updates status tracking files
- Performs branch sync reconciliation
- Handles trace token cleanup
- Records execution metrics

**File**: `.github/scripts/agents_pr_meta_keepalive.js` (~150-250 lines estimated)

**Purpose**: PR metadata extraction for keepalive context
**Key Functions**:
- Extracts PR metadata (author, labels, reviewers)
- Determines PR state for eligibility
- Gathers conversation context
- Provides input data for keepalive decisions

#### 3. Workflow Integration

**Workflow**: `.github/workflows/agents-70-orchestrator.yml`

**Keepalive Sweep Job**:
```yaml
keepalive_sweep:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    - name: Run keepalive sweep
      uses: actions/github-script@v7
      with:
        script: |
          const keepalive = require('./scripts/keepalive-runner.js');
          await keepalive.runKeepalive({ github, context, core });
```

**Workflow**: `.github/workflows/agents-keepalive-branch-sync.yml`

**Purpose**: Synchronizes keepalive branches with upstream changes
**Triggers**: Manual dispatch, scheduled (optional)
**Integration**: Called by keepalive system when sync needed

**Workflow**: `.github/workflows/agents-keepalive-dispatch-handler.yml`

**Purpose**: Handles keepalive command dispatches
**Triggers**: `workflow_dispatch` with keepalive command payload
**Integration**: Triggered by `dispatchKeepaliveCommand()` in main runner

**Workflow**: `.github/workflows/reusable-16-agents.yml`

**Keepalive Integration**: Includes keepalive mode parameter handling
**Purpose**: Reusable agent workflow with keepalive support

### Documentation

#### Core Documentation (Immediate Transition)

**File**: `docs/keepalive/GoalsAndPlumbing.md` (180 lines)

**Content**: Canonical reference document covering:
- Activation guardrails (PR state requirements)
- Repeat contract (when to post new vs update existing)
- Run cap enforcement (maximum iterations per PR)
- Pause controls (emergency stop mechanisms)
- Trace token system (observability contract)
- Branch sync coordination

**File**: `docs/keepalive/Keepalive_Reliability_Plan.md`

**Content**: Failure analysis and recovery strategies:
- Common failure modes and detection
- Implementation checklist for guardrails
- Recovery procedures
- Monitoring requirements

**File**: `docs/keepalive/Observability_Contract.md`

**Content**: Observability and debugging infrastructure:
- Trace token format and usage
- Status file structure
- Log aggregation strategy
- Metrics collection points

#### Evaluation Documentation

**Pattern**: `docs/keepalive/pr-XXXX-eval-roundN.md`

**Purpose**: Real-world keepalive execution logs
**Content**: Per-PR, per-round evaluation notes
**Transition Strategy**: Archive pattern examples, exclude PR-specific logs

**File**: `docs/keepalive/pr-XXXX-status.md`

**Purpose**: Current status tracking for active PRs
**Transition Strategy**: Exclude (runtime data, not system documentation)

#### Status Tracking

**File**: `keepalive_status.md` (root)

**Purpose**: Index of all PRs with keepalive activity
**Format**: Markdown table with links to detailed status files
**Transition Strategy**: Provide template/schema, not actual data

**Directory**: `docs/keepalive/status/`

**Files**: `PR-*.md` per active PR
**Purpose**: Detailed per-PR keepalive execution history
**Transition Strategy**: Exclude runtime data, document format/schema

### Templates

**File**: `.github/templates/keepalive-instruction.md`

**Purpose**: Template for keepalive instruction comments
**Variables**: Supports templating (round number, trace token, context)
**Usage**: Loaded by `postKeepaliveInstruction()` in keepalive-runner.js

**Transition Priority**: HIGH - Core template required for system operation

### Test Infrastructure

#### Test Files

**File**: `tests/workflows/test_keepalive_workflow.py` (~500+ lines estimated)

**Coverage**:
- Main keepalive workflow execution
- Gate logic validation
- Status tracking updates
- Error handling scenarios
- Edge cases (PR states, branch conditions)

**Node.js Test Harness**: Uses Node.js subprocess to execute JavaScript functions

**File**: `tests/workflows/test_keepalive_post_work.py`

**Coverage**:
- Post-execution cleanup logic
- State file updates
- Branch sync coordination
- Cleanup error handling

#### Test Fixtures

**Directory**: `tests/workflows/fixtures/keepalive/`

**File**: `harness.js` (Node.js test harness)

**Purpose**: 
- Loads keepalive-runner.js in isolated context
- Provides mock GitHub API (Octokit)
- Simulates file system operations
- Captures function outputs for assertion

**Mock Data**:
- Sample PR metadata
- Mock comment structures
- Fake status files
- Simulated API responses

## Transition Strategy

### Phase 1: Foundation (Week 1-2)

#### 1.1 Core Script Migration

**Priority**: CRITICAL
**Timeline**: 3-5 days

**Tasks**:
1. Create `scripts/keepalive-runner.js` in Workflows repo
   - Copy main orchestration script
   - Update require() paths for new repo structure
   - Update relative file references
   - Verify Node.js 20+ compatibility

2. Create helper scripts directory `.github/scripts/`
   - Copy `keepalive_gate.js`
   - Copy `keepalive_post_work.js`  
   - Copy `agents_pr_meta_keepalive.js`
   - Update cross-references between scripts

3. Dependency Management
   - Document Node.js version requirement (v20+)
   - Document required npm packages (@actions/core, @actions/github or @octokit/rest)
   - Create package.json with dependency declarations
   - Add npm installation to setup documentation

**Validation**:
- Run Node.js syntax validation: `node --check scripts/keepalive-runner.js`
- Verify all require() statements resolve
- Check for hardcoded repository-specific paths

#### 1.2 Template Migration

**Priority**: CRITICAL
**Timeline**: 1 day

**Tasks**:
1. Create `.github/templates/` directory
2. Copy `keepalive-instruction.md` template
3. Update any repository-specific placeholders
4. Document template variable system

**Validation**:
- Verify template renders correctly with sample data
- Check variable substitution logic in keepalive-runner.js

### Phase 2: Workflow Integration (Week 2-3)

#### 2.1 Primary Workflows

**Priority**: HIGH
**Timeline**: 5-7 days

**Tasks**:

1. **Orchestrator Workflow** (`agents-70-orchestrator.yml`)
   - Extract keepalive sweep job
   - Update script paths to new repository structure
   - Modify checkout actions to reference Workflows repo
   - Update Node.js setup configuration
   - Test isolated keepalive sweep execution

2. **Branch Sync Workflow** (`agents-keepalive-branch-sync.yml`)
   - Copy complete workflow definition
   - Update repository references
   - Modify branch sync logic for multi-repo architecture
   - Add cross-repository synchronization capability
   - Document manual dispatch parameters

3. **Dispatch Handler** (`agents-keepalive-dispatch-handler.yml`)
   - Copy workflow definition
   - Update script references
   - Modify dispatch event handling
   - Test workflow_dispatch triggering

**Integration Pattern**:
```yaml
# In consumer repository workflows
- name: Checkout Workflows repo
  uses: actions/checkout@v4
  with:
    repository: stranske/Workflows
    path: .workflows
    
- name: Run keepalive sweep
  uses: actions/github-script@v7
  with:
    script: |
      const keepalive = require('./.workflows/scripts/keepalive-runner.js');
      await keepalive.runKeepalive({ github, context, core });
```

#### 2.2 Reusable Workflow Integration

**File**: `reusable-16-agents.yml`

**Tasks**:
1. Extract keepalive mode handling
2. Add keepalive parameter to workflow inputs
3. Document keepalive integration points
4. Create usage examples

**Timeline**: 2-3 days

### Phase 3: Documentation (Week 3-4)

#### 3.1 Core Documentation Migration

**Priority**: HIGH
**Timeline**: 3-4 days

**Tasks**:

1. Create `docs/keepalive/` directory structure:
   ```
   docs/keepalive/
   ├── README.md (overview + quick start)
   ├── GoalsAndPlumbing.md (canonical reference)
   ├── Keepalive_Reliability_Plan.md (failure modes)
   ├── Observability_Contract.md (monitoring)
   ├── Integration.md (how to integrate with repos)
   └── examples/
       ├── basic-integration.md
       ├── custom-templates.md
       └── troubleshooting.md
   ```

2. Content Updates:
   - Update all repository references (Trend_Model_Project → consumer repo patterns)
   - Create generic integration examples
   - Add multi-repository usage patterns
   - Document environment variable configuration
   - Add troubleshooting guide

3. New Documentation:
   - **Integration.md**: Step-by-step guide for integrating keepalive into consumer repos
   - **examples/**: Practical implementation examples
   - **Migration guide**: For repositories moving from Trend_Model_Project pattern

#### 3.2 Status Tracking Documentation

**Priority**: MEDIUM
**Timeline**: 2 days

**Tasks**:
1. Document status file format (`keepalive_status.md` schema)
2. Create status file templates
3. Document per-PR status file structure
4. Provide initialization scripts/procedures

**Deliverable**: `docs/keepalive/StatusTracking.md`

### Phase 4: Test Infrastructure (Week 4-5)

#### 4.1 Test Migration

**Priority**: HIGH
**Timeline**: 5-7 days

**Tasks**:

1. **Directory Structure**:
   ```
   tests/workflows/
   ├── test_keepalive_workflow.py
   ├── test_keepalive_post_work.py
   ├── test_keepalive_gate.py (new)
   └── fixtures/
       └── keepalive/
           ├── harness.js
           ├── mock_pr_data.json
           ├── mock_comments.json
           └── sample_status_files/
   ```

2. **Test File Updates**:
   - Update import paths for new repository structure
   - Modify script path references in harness.js
   - Update mock data to reflect generic patterns
   - Add tests for multi-repository scenarios

3. **Harness Enhancements**:
   - Update `harness.js` to handle new repo layout
   - Add mock for cross-repository operations
   - Enhance Octokit mocking for workflow dispatches
   - Add file system mock for status tracking

4. **New Test Coverage**:
   - Multi-repository integration scenarios
   - Cross-repository branch synchronization
   - Template rendering with various data
   - Error recovery procedures

#### 4.2 CI Integration

**Priority**: HIGH
**Timeline**: 2-3 days

**Tasks**:
1. Create workflow test job in `.github/workflows/`
2. Install Node.js 20+ in test environment
3. Install test dependencies (pytest, Node.js modules)
4. Configure test execution in CI
5. Add coverage reporting for keepalive tests

**Example CI Job**:
```yaml
keepalive-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        npm install @actions/core @actions/github
        pip install pytest pytest-subprocess
    - name: Run keepalive tests
      run: pytest tests/workflows/test_keepalive*.py -v
```

### Phase 5: Integration & Validation (Week 5-6)

#### 5.1 End-to-End Testing

**Priority**: CRITICAL
**Timeline**: 5-7 days

**Test Scenarios**:

1. **Basic Keepalive Cycle**:
   - Create test PR in Trend_Model_Project
   - Trigger keepalive sweep from Workflows repo
   - Verify comment posting
   - Validate status tracking updates
   - Confirm trace token generation

2. **Multi-Round Execution**:
   - Trigger multiple keepalive rounds
   - Verify round counter increments
   - Check repeat contract enforcement
   - Validate run cap limits

3. **Branch Synchronization**:
   - Modify base branch
   - Trigger keepalive branch sync
   - Verify changes propagated
   - Confirm conflict handling

4. **Error Scenarios**:
   - Simulate API failures
   - Test with invalid PR states
   - Verify pause control activation
   - Check recovery procedures

#### 5.2 Documentation Validation

**Priority**: HIGH
**Timeline**: 2-3 days

**Tasks**:
1. Follow integration guide to set up keepalive in test repository
2. Verify all code examples execute correctly
3. Test troubleshooting procedures
4. Validate configuration examples

#### 5.3 Performance Validation

**Priority**: MEDIUM
**Timeline**: 2 days

**Metrics**:
- Keepalive sweep execution time (target: <60 seconds)
- API call count per sweep (monitor rate limit consumption)
- Status file write latency
- Branch sync duration

## Dependencies & Prerequisites

### External Dependencies

**Node.js Environment**:
- Node.js v20+ (required)
- npm (package management)
- @actions/core (GitHub Actions integration)
- @actions/github or @octokit/rest (GitHub API)

**Python Environment** (for tests):
- Python 3.11+
- pytest
- pytest-subprocess

**GitHub Actions**:
- actions/checkout@v4
- actions/setup-node@v4
- actions/github-script@v7

### Repository Configuration

**Secrets Required**:
- `GITHUB_TOKEN` (automatic, provided by GitHub Actions)
- Optional: `PAT_TOKEN` (for cross-repository operations)

**Repository Settings**:
- Actions enabled
- Workflow permissions: Read/Write
- Allow workflow dispatch events

**Branch Protection**:
- Keepalive branches excluded from strict protection
- Allow force pushes to keepalive branches (for sync)

## Risk Assessment

### High Risk Areas

**1. Cross-Repository Orchestration**
- **Risk**: Keepalive system in Workflows repo managing PRs in consumer repos
- **Mitigation**: 
  - Comprehensive integration testing
  - Clear repository parameter passing
  - Fallback error handling
  - Detailed logging

**2. State File Management**
- **Risk**: Status tracking files may conflict in multi-repository setup
- **Mitigation**:
  - Repository-prefixed status files
  - Atomic write operations
  - Conflict detection and recovery
  - Regular state validation

**3. Branch Synchronization Complexity**
- **Risk**: Branch sync across repositories may fail or create conflicts
- **Mitigation**:
  - Conservative sync strategy
  - Conflict detection before sync
  - Manual intervention hooks
  - Comprehensive sync logging

### Medium Risk Areas

**4. API Rate Limiting**
- **Risk**: Keepalive sweep performs multiple API calls
- **Mitigation**:
  - Batch API operations
  - Cache PR metadata
  - Implement backoff strategy
  - Monitor rate limit consumption

**5. Template Rendering**
- **Risk**: Template variables may not render correctly across repos
- **Mitigation**:
  - Extensive template testing
  - Variable validation
  - Default value handling
  - Clear error messages

## Success Criteria

### Phase Completion Criteria

**Phase 1 Complete When**:
- [ ] All JavaScript files execute without errors
- [ ] Template renders with sample data
- [ ] Node.js syntax validation passes
- [ ] All require() statements resolve

**Phase 2 Complete When**:
- [ ] Keepalive sweep executes in isolation
- [ ] Branch sync workflow completes successfully
- [ ] Dispatch handler responds to triggers
- [ ] Cross-repository script loading works

**Phase 3 Complete When**:
- [ ] All core documentation migrated
- [ ] Integration guide available
- [ ] Status tracking documented
- [ ] Examples validated

**Phase 4 Complete When**:
- [ ] All keepalive tests migrated
- [ ] Test harness functions correctly
- [ ] CI job executes successfully
- [ ] Test coverage meets baseline (>80%)

**Phase 5 Complete When**:
- [ ] End-to-end keepalive cycle succeeds
- [ ] Multi-round execution verified
- [ ] Branch sync tested
- [ ] Error scenarios handled gracefully

### System Acceptance Criteria

**Functional Requirements**:
- [ ] Keepalive instruction posting works in test repository
- [ ] Round tracking increments correctly
- [ ] Run caps enforced
- [ ] Pause controls functional
- [ ] Branch sync operational
- [ ] Status tracking updates correctly

**Performance Requirements**:
- [ ] Keepalive sweep completes in <90 seconds
- [ ] API rate limit consumption <50% of limit
- [ ] Zero failed sweeps due to timeouts
- [ ] Status file writes complete in <5 seconds

**Quality Requirements**:
- [ ] Zero critical bugs in production testing
- [ ] Integration documentation complete and accurate
- [ ] Test coverage >80% for core keepalive logic
- [ ] All error paths have recovery procedures

## Timeline Summary

| Phase | Duration | Priority | Dependencies |
|-------|----------|----------|--------------|
| Phase 1: Foundation | 1-2 weeks | CRITICAL | None |
| Phase 2: Workflow Integration | 1-2 weeks | HIGH | Phase 1 |
| Phase 3: Documentation | 1 week | HIGH | Phase 1 |
| Phase 4: Test Infrastructure | 1-2 weeks | HIGH | Phase 1, 2 |
| Phase 5: Integration & Validation | 1-2 weeks | CRITICAL | Phase 1-4 |
| **Total Duration** | **5-8 weeks** | | |

**Critical Path**: Phases 1 → 2 → 5 (minimum 3-6 weeks)

## Post-Transition Considerations

### Maintenance

**Regular Tasks**:
- Monitor keepalive execution logs
- Review status tracking data
- Update templates as needed
- Refresh integration documentation
- Track API rate limit usage

**Quarterly Reviews**:
- Evaluate guardrail effectiveness
- Review run cap limits
- Assess branch sync reliability
- Analyze failure modes
- Update documentation

### Evolution

**Planned Enhancements**:
- Multi-tenant keepalive (supporting multiple consumer repos simultaneously)
- Advanced scheduling (time-of-day restrictions)
- Conditional keepalive (based on PR content)
- Metrics dashboard (keepalive health monitoring)
- Automated status cleanup (archive old PR data)

**Integration Opportunities**:
- Connect with PR comment system for unified instruction management
- Integrate with agent orchestration for coordinated automation
- Add Slack/Discord notifications for keepalive events
- Create web dashboard for status visualization

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-XX  
**Status**: Draft - Ready for Review
