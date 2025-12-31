# Agent Issue Template

This template defines the canonical structure for issues that feed into the Codex keepalive automation pipeline. Follow this format to ensure issues are correctly parsed and actionable by agents.

## ⚠️ Critical Rule: Checkbox Conversion

**ALL bullet points (`-`) in Tasks and Acceptance Criteria sections are automatically converted to checkboxes.**

- ✅ **DO:** Use bullets only for actual tasks/criteria to check off
- ❌ **DON'T:** Use bullets for instructions, notes, or explanations

**Where to put different types of content:**

| Content Type | Put it in... | Format to Use |
|---|---|---|
| Background/context | Scope, Why, Implementation Notes | Any format |
| Instructions/steps | Scope, Implementation Notes | Numbered lists (1. 2. 3.) |
| Reminders/notes | Scope, Implementation Notes | Bold text, quotes, any format |
| Actual work items | Tasks | Bullet points (-) |
| Success conditions | Acceptance Criteria | Bullet points (-) |

## Template Structure

```markdown
## Why

<!-- Motivation: Explain the problem or opportunity this work addresses.
     Keep it brief but provide enough context for an agent to understand
     why this work matters. -->

## Scope

<!-- Define what this issue covers. Be specific about boundaries to prevent
     scope creep and help agents focus on the intended work. -->

## Non-Goals

<!-- List what is explicitly out of scope. This helps agents avoid
     unnecessary work and keeps the implementation focused. -->

## Tasks

<!-- Actionable checklist items. Each task should be:
     - Specific enough to verify completion
     - Small enough to complete in one iteration
     - Listed with unchecked boxes [ ] for new work
     
     IMPORTANT: Do NOT use bullet points for instructions or notes.
     Only use bullets for actual, actionable tasks. Lines starting with
     bullets will be automatically converted to checkboxes.
     
     CORRECT:
     - [ ] Add unit tests for feature X
     - [ ] Update documentation in README.md
     
     INCORRECT:
     - Before implementing, review the existing code  (instruction, not task)
     - Remember to run tests after each change  (reminder, not task)
     - 1. First do X, then do Y  (numbered guidance, not discrete tasks)
     
     Use sub-tasks (indented) for complex items. -->

- [ ] First task description
- [ ] Second task description
  - [ ] Sub-task if needed
- [ ] Third task description

## Acceptance Criteria

<!-- Verifiable conditions that must be met for this issue to be considered
     complete. These are checked by the verifier workflow after merge.
     
     IMPORTANT: Do NOT use bullet points for instructions on HOW to verify.
     Only use bullets for the actual criteria. Lines starting with bullets
     will be automatically converted to checkboxes.
     
     Write criteria that can be objectively verified:
     
     CORRECT:
     - [ ] All tests pass
     - [ ] Code coverage ≥95%
     - [ ] No regressions introduced
     
     INCORRECT:
     - Before marking complete, run pytest  (instruction, not criterion)
     - To verify coverage, check the report  (guidance, not criterion)
     - 1. Run tests 2. Check output  (numbered steps, not criteria)
     
     If you need to provide verification instructions, put them in a
     comment or in the Implementation Notes section. -->

- [ ] First criterion
- [ ] Second criterion

## Implementation Notes

<!-- Technical details, suggestions, or constraints for the implementation.
     Include:
     - Relevant file paths
     - API references
     - Design considerations
     - Branch naming conventions
     
     This section is optional but helpful for complex issues. -->
```

---

## Section Reference

### Required Sections

| Section | Aliases | Purpose |
|---------|---------|---------|
| **Tasks** | `Task List`, `Implementation` | Work items with checkboxes |
| **Acceptance Criteria** | `Acceptance`, `Definition of Done`, `Success criteria` | Verifiable completion conditions |

### Recommended Sections

| Section | Aliases | Purpose |
|---------|---------|---------|
| **Why** | `Goals`, `Summary`, `Motivation` | Context and rationale |
| **Scope** | `Background`, `Context`, `Overview` | What the issue covers |
| **Non-Goals** | `Out of Scope`, `Constraints` | Explicit exclusions |
| **Implementation Notes** | (none) | Technical guidance |

---

## Guidelines for Verifier Follow-Up Issues

When the agents-verifier workflow detects unmet acceptance criteria, it creates a follow-up issue. These follow-up issues should:

### 1. Reference the Source

Include links to the original PR and any parent issues:

```markdown
## Source

- Original PR: #123
- Parent issue: #100
- Verifier run: [link to workflow run]
```

### 2. Copy Unmet Criteria

Copy the **exact text** of acceptance criteria that weren't satisfied:

```markdown
## Acceptance Criteria

<!-- Copied from original issue - these criteria were not met -->
- [ ] API returns correct response codes
- [ ] Error messages include actionable guidance
```

### 3. Update Tasks Based on Gaps

If all original tasks were completed but criteria weren't met, add new tasks:

```markdown
## Tasks

<!-- New tasks to address unmet acceptance criteria -->
- [ ] Add validation for edge case X
- [ ] Update error response format
- [ ] Add test coverage for scenario Y
```

### 4. Preserve Context

Copy relevant sections from the original issue to maintain context:

```markdown
## Why

<!-- Preserved from parent issue -->
The API needs to return actionable error messages so clients can 
recover gracefully from failures.

## Scope

<!-- Updated scope for this follow-up -->
Address the specific gaps identified by the verifier for PR #123.
```

---

## Example: Complete Issue

```markdown
## Why

The keepalive loop doesn't properly handle transient API failures, causing
premature `needs-human` labels on PRs that could recover automatically.

## Scope

Implement error classification and recovery logic for the keepalive loop
and Codex run workflows.

## Non-Goals

- Changing the keepalive iteration limits
- Modifying the PR merge requirements
- Adding new agent types

## Tasks

- [ ] Create error classification module with category detection
- [ ] Add exponential backoff for transient failures
- [ ] Update keepalive to reset failure counter on transient errors
- [ ] Add diagnostic artifact collection for failures
- [ ] Write tests for error classification paths

## Acceptance Criteria

- [ ] Transient failures (rate limits, network errors) are retried with backoff
- [ ] Non-transient failures are reported with recovery guidance
- [ ] Failure counter only increments for non-transient failures
- [ ] Error diagnostics are captured as workflow artifacts
- [ ] Tests cover all error classification paths

## Implementation Notes

Files to create or modify:
- `.github/scripts/error_classifier.js` - Error category detection
- `.github/scripts/github_api_retry.js` - Retry wrapper with backoff
- `.github/workflows/reusable-codex-run.yml` - Failure handling steps

Branch: `codex/issue-144`
PR title: `[Agents] Add error classification and recovery for keepalive loop`
```

---

## Example: Verifier Follow-Up Issue

```markdown
## Source

- Original PR: #145
- Parent issue: #144
- Verifier verdict: FAIL

## Why

<!-- Preserved from parent issue -->
The keepalive loop doesn't properly handle transient API failures.

## Scope

Address unmet acceptance criteria from PR #145 implementation.

## Non-Goals

<!-- Preserved from parent issue -->
- Changing the keepalive iteration limits

## Tasks

<!-- New tasks based on verifier findings -->
- [ ] Add missing test for rate limit header parsing
- [ ] Fix edge case in backoff calculation for very long delays

## Acceptance Criteria

<!-- Unmet criteria copied from original -->
- [ ] Tests cover all error classification paths

## Implementation Notes

The verifier found that the rate limit header parsing path in 
`github_api_retry.js` lacks test coverage. Add test cases for:
- `Retry-After` header with integer value
- `X-RateLimit-Reset` header with Unix timestamp
- Both headers missing (should use default backoff)
```

---

## Parsing Notes

The automation uses flexible parsing that accepts:
- Markdown headers (`## Section`) or plain text (`Section:`)
- Various aliases for section names (see table above)
- Nested checkboxes for sub-tasks
- Mixed formatting within the same issue

For maximum compatibility, use `## Section` format with exact names from the "Required Sections" table.
