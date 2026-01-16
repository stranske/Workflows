# Long-Term Planning: LangChain Phases 4-5 & Beyond

> **Created:** January 10, 2026  
> **Status:** Initial Draft  
> **Scope:** 4-8 weeks post Phase 3  
> **Dependencies:** Phase 3 functional testing complete ✅

> **Last reviewed:** 2026-01-11
> **Note:** This is planning context, not a runbook. Validate the current state in `docs/ci/WORKFLOW_SYSTEM.md`.

---

## Executive Summary

With Phase 3 complete (capability check, task decomposition, duplicate detection, auto-labeling), the focus shifts to:

1. **Phase 4: Full Automation** - Auto-pilot workflow, user guide, verification-to-issue
2. **Phase 5: Intelligence** - Learning from feedback, improved accuracy
3. **Infrastructure:** Performance, monitoring, cost optimization

---

## Current State (January 10, 2026)

### Phase 3 Completed ✅

| Component | Status | PRs | Validation |
|-----------|--------|-----|------------|
| Capability Check | ✅ Working | #696, #699 | Suite A executed |
| Task Decomposition | ✅ Working | #696 | Suite B: 3/3 PRs created |
| Duplicate Detection | ✅ Tuned | #731 | Threshold 0.92, 40% word overlap |
| Auto-Label | ✅ Tuned | #731, #733, #735 | Bug→bug, Feature→enhancement |

### Blocked Items

| Item | Blocker | Resolution |
|------|---------|------------|
| Label Cleanup | Token lacks delete permission | Manual execution needed (12 labels) |
| Conflicted PRs | Token lacks merge permission | #134, #135 ready for manual merge |

---

## Phase 4: Full Automation (3-4 Weeks)

### 4A. Label Cleanup ✅ AUDITED - NEEDS MANUAL EXECUTION

**Status:** Audit complete, bloat identified

| Repo | Bloat Labels | Idiosyncratic |
|------|--------------|---------------|
| Manager-Database | 1 | 4 |
| Travel-Plan-Permission | 5 | 25 |
| Portable-Alpha-Extension-Model | 2 | 20 |
| Trend_Model_Project | 2 | 55 |
| Workflows | 2 | 45 |
| Template | 0 | 3 |
| trip-planner | 0 | 2 |
| Collab-Admin | 0 | 2 |

**Bloat to Remove (12 total):**
- `codex` - Redundant with `agent:codex`
- `agents:pause` - Consolidated to `agents:paused`
- `ai:agent` - Unused
- `auto-merge-audit` - Unused
- `automerge:ok` - Unused variant

**Action Required:** Manual execution of cleanup commands (see SHORT_TERM_PLAN)

---

### 4B. Workflow User Guide

**Priority:** HIGH - Enables adoption
**Effort:** 4-6 hours

**Deliverable:** `docs/WORKFLOW_USER_GUIDE.md`

**Content:**
1. **Quick Start** (30 min read)
   - Issue → Agent PR in 5 steps
   - Most common label workflows
   - Copy-paste examples

2. **Issue Creation Flow**
   - Raw idea → `agents:optimize` → `agents:apply-suggestions` → `agent:codex`
   - Screenshots of each step

3. **PR Automation Flow**
   - Labels that affect PR lifecycle
   - When to use `autofix`, `agents:keepalive`
   - Auto-merge criteria

4. **Label Decision Tree**
   ```
   Is this a bug? → Add issue → agents:optimize
                            → Then agent:codex
   
   Is PR failing CI? → Is it lint/format? → autofix
                    → Is it substantive? → agents:keepalive
   
   Is PR ready? → All checks green? → automerge
   ```

5. **Troubleshooting**
   - "Agent is stuck" → Check for `agent:needs-attention`
   - "PR won't merge" → Check Gate status, labels
   - "Keepalive isn't running" → Check `agents:paused`, timing

**Implementation:**
- [ ] Create initial draft
- [ ] Test each documented flow
- [ ] Add to sync manifest
- [ ] Link from repo READMEs

---

### 4C. Auto-Pilot Workflow (`agents:auto-pilot`) ✅ IMPLEMENTED

**Status:** Initial implementation complete (2026-01-10)

**Implementation:**
- ✅ `agents-auto-pilot.yml` workflow created (~490 lines)
- ✅ Inline issue prep (format/optimize/apply) with self re-dispatch
- ✅ Progress comments at each step (step tracking)
- ✅ Safety controls: 10 step max, 4hr timeout, pause/failed labels
- ✅ Labels created: `agents:auto-pilot`, `agents:auto-pilot-pause`, `agents:auto-pilot-failed`
- ✅ Pagination for timeline/comment APIs
- ✅ Secure env variable passing (no direct interpolation)

**Flow:**
1. User adds `agents:auto-pilot` to issue
2. Auto-pilot formats issue inline and marks `agents:formatted`
3. Auto-pilot optimizes issue inline and posts suggestions
4. Auto-pilot applies suggestions inline and marks `agents:apply-suggestions`
5. Auto-pilot assigns `agent:codex` and waits for agent branch
6. Auto-pilot creates PR and dispatches PR meta update
7. Gate workflow_run triggers keepalive loop until tasks complete
8. Auto-pilot adds `automerge`, then `verify:evaluate`, then removes itself

**Testing Needed:**
- [ ] Create test issue with `agents:auto-pilot`
- [ ] Verify each step transition
- [ ] Test pause/resume functionality
- [ ] Test failure handling (exceed cycle limit)

---

### 4D. Conflict Resolution ✅ IMPLEMENTED

**Status:** Code complete, deployed to all 7 repos

**Implementation:**
- ✅ `conflict_detector.js` (366 lines)
- ✅ Integration with `keepalive_loop.js`
- ✅ Integration with `keepalive_prompt_routing.js`
- ✅ `fix_merge_conflicts.md` prompt

**Testing:**
- [ ] Create intentionally conflicted branch
- [ ] Verify detection triggers
- [ ] Confirm agent resolves conflict
- [ ] Measure cycle efficiency

---

### 4E. Verification-to-Issue ✅ IMPLEMENTED

**Status:** Working (tested January 10)

**Evidence:**
- Issue #729 created from `verify:create-issue` label
- Enhanced structure with Tasks, Acceptance Criteria, Implementation Notes
- Deprecated duplicate workflow disabled

---

## Phase 5: Intelligence & Learning (4-8 Weeks)

### 5A. Feedback Loop Learning

**Concept:** Learn from human corrections to improve accuracy

**Data Sources:**
- Issues where human removed auto-applied label
- PRs where human corrected agent work
- Duplicate flags that were wrong (issue reopened)

**Implementation Ideas:**
- Track label application → removal patterns
- Adjust confidence thresholds per-label based on accuracy
- Store embedding vectors for "known good" label matches

**Complexity:** HIGH - Requires state persistence, ML infrastructure

---

### 5B. Multi-Model Arbitration

**Concept:** Use multiple models and vote on outcomes

**Use Cases:**
- High-stakes PRs get 3-model evaluation, majority wins
- Disagreement → human review

**Benefits:**
- Reduced false positives/negatives
- Model-specific strengths complementary

**Complexity:** MEDIUM - Already have compare mode, need voting logic

---

### 5C. Issue Priority Scoring

**Concept:** Auto-prioritize issues based on:
- Impact keywords (security, crash, data loss)
- Affected components (core vs. peripheral)
- User sentiment analysis

**Output:** Priority labels (`priority:high`, `priority:medium`, `priority:low`)

**Complexity:** LOW - Similar to label matcher

---

### 5D. Agent Performance Metrics

**Concept:** Dashboard showing:
- Issue → PR conversion rate
- Average time to merge
- Agent success rate by issue type
- Common failure patterns

**Implementation:**
- GitHub Actions workflow summary aggregation
- Daily/weekly report generation
- Trend analysis

**Complexity:** MEDIUM - Data collection exists, need visualization

---

## Infrastructure Improvements

### Performance

| Issue | Current | Target | Solution |
|-------|---------|--------|----------|
| Embedding cold start | 5-10s | <2s | Pre-warm embeddings on workflow start |
| Rate limit handling | Retry with backoff | Predictive throttling | Track quota, schedule batches |
| Large issue processing | Timeout on 10K+ chars | Handle gracefully | Chunking, summarization |

### Cost Optimization

| Optimization | Savings | Effort |
|--------------|---------|--------|
| Cache embeddings per-issue | 40% token reduction | Medium |
| Use smaller models for screening | 30% cost reduction | Low |
| Skip expensive ops on trivial changes | Variable | Medium |

### Monitoring

**Key Metrics:**
- LLM API latency (p50, p95, p99)
- Token consumption per workflow
- Error rate by provider
- Workflow success rate

**Alerting:**
- Rate limit approaching
- Error spike
- Token budget breach

---

## Prioritized Roadmap

### Week 1-2 (Immediate)
1. ✅ Phase 3 validation complete
2. Manual label cleanup (12 labels)
3. User Guide v1 draft
4. Test conflict resolution

### Week 3-4
1. User Guide complete + deployed
2. Auto-pilot design finalized
3. Auto-pilot basic implementation
4. Conflict resolution validation

### Week 5-6
1. Auto-pilot testing (simple issues)
2. Performance optimizations
3. Metrics dashboard v1

### Week 7-8
1. Auto-pilot graduation (more complex issues)
2. Feedback loop design
3. Multi-model arbitration prototype

---

## Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Runaway automation | Bad PRs merged automatically | Safety limits, human gates |
| LLM hallucination | Wrong labels, bad advice | Multi-model verification |
| Token exhaustion | Workflows stop working | Budget alerts, fallback to regex |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Provider outage | Temporary degradation | Multi-provider fallback |
| Rate limiting | Delayed processing | Retry logic, queue management |
| Stale embeddings | Reduced accuracy | Periodic re-indexing |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Label bloat | User confusion | Regular cleanup audits |
| Documentation drift | Incorrect guidance | Sync with code changes |

---

## Success Metrics

### Phase 4 Success Criteria

| Metric | Target | Current |
|--------|--------|---------|
| Auto-pilot success rate | >80% (simple issues) | N/A |
| Time to merge (auto-pilot) | <2 hours | N/A |
| User guide adoption | >50% of issues use flow | N/A |
| Conflict auto-resolution | >70% success | N/A |

### Phase 5 Success Criteria

| Metric | Target | Current |
|--------|--------|---------|
| Label accuracy | >95% | ~90% |
| False positive rate | <5% | ~10% |
| Agent success rate | >85% | ~75% |

---

## Open Questions

1. **Auto-pilot scope:** Should it handle infrastructure changes or only code?
2. **Budget allocation:** Per-repo or per-org token budgets?
3. **Human approval gates:** Which steps require human sign-off?
4. **Learning persistence:** How to store learned patterns across restarts?
5. **Multi-repo coordination:** Can auto-pilot span dependent repos?

---

## Appendix: Deferred Ideas

- **Natural language issue creation** - "Create an issue for X" command
- **PR reviewer suggestions** - Recommend reviewers based on changed files
- **Automated release notes** - Generate from merged PRs
- **Cross-repo issue linking** - Detect related issues across repos
- **Agent specialization** - Different agents for different task types
