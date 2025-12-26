# Agent Issue Format Guide

This document defines the canonical structure for issues that feed into the Codex keepalive automation pipeline. Follow this format when creating issues for automated agent processing.

## Quick Reference Template

```markdown
## Why

<!-- Brief explanation of the problem or opportunity -->

## Scope

<!-- What this issue covers and its boundaries -->

## Non-Goals

<!-- What is explicitly out of scope -->

## Tasks

- [ ] First task description
- [ ] Second task description
- [ ] Third task description

## Acceptance Criteria

- [ ] First verifiable criterion
- [ ] Second verifiable criterion

## Implementation Notes

<!-- Optional: Technical details, file paths, constraints -->
```

---

## Section Details

### Required Sections

| Section | Purpose | Aliases |
|---------|---------|---------|
| **Tasks** | Work items with checkboxes | `Task List`, `Implementation` |
| **Acceptance Criteria** | Verifiable completion conditions | `Acceptance`, `Definition of Done` |

### Recommended Sections

| Section | Purpose | Aliases |
|---------|---------|---------|
| **Why** | Context and rationale | `Goals`, `Summary`, `Motivation` |
| **Scope** | What the issue covers | `Background`, `Context`, `Overview` |
| **Non-Goals** | Explicit exclusions | `Out of Scope`, `Constraints` |
| **Implementation Notes** | Technical guidance | — |

---

## Writing Good Tasks

Each task should be:
- **Specific** — Clear enough to verify completion
- **Small** — Completable in one iteration
- **Actionable** — Starts with a verb

✅ Good:
```markdown
- [ ] Add input validation for email field in UserForm component
- [ ] Write unit tests for calculateDiscount function
- [ ] Update README with new API endpoints
```

❌ Bad:
```markdown
- [ ] Fix bugs
- [ ] Improve code
- [ ] Update things
```

---

## Writing Good Acceptance Criteria

Criteria should be:
- **Verifiable** — Can be objectively checked
- **Specific** — No ambiguity about pass/fail
- **Independent** — Each criterion stands alone

✅ Good:
```markdown
- [ ] All unit tests pass
- [ ] API returns 400 status for invalid input
- [ ] Documentation includes usage examples
```

❌ Bad:
```markdown
- [ ] Code is good
- [ ] Works correctly
- [ ] Meets requirements
```

---

## Complete Example

```markdown
## Why

The user registration flow doesn't validate email format before submission,
leading to invalid data in the database and failed notification emails.

## Scope

Add client-side and server-side email validation to the registration form.

## Non-Goals

- Changing the email verification flow
- Adding additional registration fields
- Modifying the password requirements

## Tasks

- [ ] Add email format validation to RegisterForm component
- [ ] Add server-side email validation in /api/register endpoint
- [ ] Display user-friendly error message for invalid emails
- [ ] Write tests for email validation logic

## Acceptance Criteria

- [ ] Invalid email formats are rejected with clear error message
- [ ] Valid emails pass validation and registration proceeds
- [ ] Server returns 400 status with error details for invalid email
- [ ] Unit tests cover common invalid email patterns

## Implementation Notes

Files to modify:
- `src/components/RegisterForm.tsx` - Client validation
- `src/api/register.ts` - Server validation
- `src/utils/validation.ts` - Shared validation logic

Use existing validation utility pattern from `src/utils/validation.ts`.
```

---

## Tips for LLMs Creating Issues

1. **Be specific about file paths** — Include exact paths in Implementation Notes
2. **Keep tasks atomic** — One checkbox = one discrete change
3. **Make criteria testable** — If you can't write a test for it, rephrase it
4. **Include context** — The Why section helps agents understand intent
5. **Set boundaries** — Non-Goals prevent scope creep

---

## Using the GitHub Issue Form

This repository includes an issue template at `.github/ISSUE_TEMPLATE/agent_task.yml` that enforces this structure. When creating issues through GitHub's UI, use the "Agent Task" template for proper formatting.

For programmatic issue creation, follow this format directly in the issue body.
