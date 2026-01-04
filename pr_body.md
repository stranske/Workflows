<!-- pr-preamble:start -->
> **Source:** Issue #457

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
Current post-CI summaries (`post_ci_summary.py` / gate summary workflow) effectively show **what failed** but not **what to do next**. Developers and agents must manually spelunk logs to understand root causes and identify fixes.

#### Tasks
- [ ] Port prototype from `stranske/Trend_Model_Project/tools/ci_failure_triage.py`
- [ ] Add pattern-based triage (works without LLM)
- [ ] Add optional LLM triage layer (gated by env var)
- [ ] Integrate with gate summary workflow
- [ ] Map error types to existing playbook docs
- [ ] Add tests for common error patterns
- [ ] Document triage output format

#### Acceptance criteria
- [ ] Pattern-based triage identifies: mypy, pytest, coverage, import, syntax errors
- [ ] Each error type maps to a suggested fix template
- [ ] LLM triage is opt-in (`KEEPALIVE_USE_LLM_TRIAGE=true`)
- [ ] Output includes: error_type, root_cause, suggested_fix, relevant_files
- [ ] Playbook links are included when available
- [ ] Works standalone and integrated with gate summary

<!-- auto-status-summary:end -->
