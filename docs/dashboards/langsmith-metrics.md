# LangSmith Metrics Dashboard

> **Last Updated:** 2026-05-30 20:16 UTC
> **Period:** Last 7 days

---

## LangSmith Trace Coverage

_No autopilot/verifier trace metrics were found for this period._

---

# LangSmith Fleet Artifact Status

- Registry entries: 8
- Valid: 0
- Missing: 8
- Stale: 0
- Invalid: 0

| Repo | Surface | Issue | Status | Records | Latest | First Error |
|------|---------|-------|--------|---------|--------|-------------|
| stranske/Counter_Risk | risk-reporting | stranske/Counter_Risk#610 | missing | 0 |  |  |
| stranske/Inv-Man-Intake | intake-extraction | stranske/Inv-Man-Intake#438 | missing | 0 |  |  |
| stranske/Manager-Database | ai-api | stranske/Manager-Database#1048 | missing | 0 |  |  |
| stranske/Pension-Data | nl-to-sql | stranske/Pension-Data#445 | missing | 0 |  |  |
| stranske/Portable-Alpha-Extension-Model | scenario-analysis | stranske/Portable-Alpha-Extension-Model#1802 | missing | 0 |  |  |
| stranske/Trend_Model_Project | llm-replay | stranske/Trend_Model_Project#5311 | missing | 0 |  |  |
| stranske/Workflows | agent-automation | stranske/Workflows#2150 | missing | 0 |  |  |
| stranske/trip-planner | planner-runtime | stranske/trip-planner#1208 | missing | 0 |  |  |

---

## How to Read This Dashboard

### Overall Trace Coverage

The **trace coverage percentage** indicates what portion of LLM
operations successfully captured a LangSmith trace ID.

- ✅ **90%+** - Excellent coverage
- ⚠️ **70-89%** - Good, but investigate gaps
- ❌ **<70%** - Action required

### Coverage by Operation Type

Different operation types (from `metric_type` field):
- **step** - Autopilot pipeline steps (format, optimize, etc.)
- **evaluation** - PR verification evaluations
- **generation** - Issue/followup generation

### Coverage by Autopilot Step

Traces grouped by `step_name` for autopilot operations.

---

## Accessing Traces

1. **In PR comments:** Look for "🔍 LangSmith Trace" section in verifier reports
2. **In workflow logs:** Check for GitHub notices titled "LangSmith Trace"
3. **In LangSmith UI:** Visit [https://smith.langchain.com](https://smith.langchain.com)

---

## Related Links

- [Integration Status](../LANGSMITH_INTEGRATION_STATUS.md)
- [E2E Validation](../LANGSMITH_E2E_VALIDATION.md)
- [Integration Skill](../../.claude/skills/langsmith-integration/skill.md)
- [Weekly Reports (Issues)](../../issues?q=is%3Aissue+label%3Alangsmith+label%3Ametrics)

