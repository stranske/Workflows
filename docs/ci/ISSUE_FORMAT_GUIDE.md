# Issue Format Guide

This guide describes the required format for GitHub issues and ChatGPT topic files to work smoothly with the Agents automation workflows.

## Table of Contents

1. [Issue Bridge Format (Codex Bootstrap)](#issue-bridge-format-codex-bootstrap)
2. [ChatGPT Topic File Format](#chatgpt-topic-file-format)
3. [Common Section Headers](#common-section-headers)
4. [Examples](#examples)

---

## Issue Bridge Format (Codex Bootstrap)

The **Agents 63 Issue Bridge** workflow reads GitHub issues and creates bootstrap pull requests for Codex to work on. Issues should follow this structure:

### Required Labels

- **Exactly one** agent assignment label: `agent:codex` or `agent:chatgpt`
- Process labels like `agents:keepalive` are optional and don't interfere

### Required Sections

Issues should include these sections (headings can be with or without `##` markdown markers):

#### 1. **Why** (or Summary)
Explains the motivation or problem being solved.

```markdown
## Why
Describes the rationale for this work.
```

#### 2. **Scope**
Defines what is included in the work.

```markdown
## Scope
One workflow handling commands and body updates in separate jobs.
```

Or without markdown header:
```markdown
Scope
One workflow handling commands and body updates in separate jobs.
```

#### 3. **Non-Goals** (optional)
What is explicitly out of scope.

```markdown
Non-Goals
Changing command syntax or markers.
```

#### 4. **Tasks**
Checklist of work items. Can be with or without checkboxes.

```markdown
## Tasks
- Create agents-pr-meta.yml with jobs
- Add listen_commands on issue_comment events
- Use a common concurrency group keyed by PR number
- Remove/retire the old two workflows
```

#### 5. **Acceptance criteria**
Conditions that must be met for the work to be complete.

```markdown
## Acceptance criteria
- Commands and body updates never run concurrently for the same PR
- Marker updates do not overwrite unrelated PR text
```

Alternative header names: `Success criteria`, `Definition of done`

#### 6. **Implementation notes** (optional)
Technical details, file paths, branch names.

```markdown
## Implementation notes
Files: .github/workflows/agents-64-pr-comment-command-listener.yml
Branch: codex/issue--merge-pr-meta
PR title prefix: [Agents] Merge PR meta workflows
```

### Section Flexibility

The Agents PR meta workflow now supports:
- Headers **with** `##` markdown markers: `## Scope`
- Headers **without** markers (plain text): `Scope`
- Mixed formats within the same issue

This ensures backward compatibility with both old and new issue formats.

---

## ChatGPT Topic File Format

The **Agents 63 Issue Intake** workflow processes topic files and creates/updates GitHub issues when dispatched in ChatGPT sync mode.

### File Format

Topics are separated by blank lines. Each topic block contains:

1. **Topic line** (required): Short title prefixed with emoji or marker
2. **Agent label** (required): `agent:codex` or `agent:chatgpt`
3. **Additional labels** (optional): priority, category, etc.
4. **Body content** (optional): Multi-line description

### Example Topic File

```
🔧 Fix the build system timeout issues
agent:codex
priority: high
devops
ci

The build occasionally times out when installing dependencies.
Need to add retry logic and increase timeout threshold.

---

📝 Document the new API endpoints
agent:codex
priority: medium
documentation

Add comprehensive API documentation for the /api/v2 endpoints
introduced in the last release.

---

🎨 Improve dashboard responsiveness
agent:chatgpt
priority: low
enhancement
ui

Make the dashboard work better on mobile devices.
Current layout breaks on screens smaller than 768px.
```

### Topic File Rules

1. **Separation**: Topics are separated by blank lines or `---` dividers
2. **Order**: Title first, then labels (starting with `agent:`), then body
3. **Agent Label**: Must be present and must be exactly one base agent label
4. **File Location**: Can be provided via:
   - `repo_file`: Path in the repository (preferred for large lists)
   - `raw_input`: Small pasted text (may truncate around 1KB)
   - `source_url`: URL to raw text file (e.g., raw.githubusercontent.com, Gist)

### Invalid Examples

❌ **No agent label**:
```
Fix the thing
priority: high
```

❌ **Multiple agent labels**:
```
Fix the thing  
agent:codex
agent:chatgpt
```

❌ **Missing title**:
```
agent:codex
Just some body text
```

---

## Common Section Headers

The automation recognizes these section headers (case-insensitive, with or without `##`):

### Issue Structure
- **Why** / **Summary** / **Description** / **Overview**
- **Goal**
- **Scope**
- **Non-Goals**
- **Tasks**
- **Acceptance criteria** / **Success criteria** / **Definition of done**
- **Testing** / **Test Plan** / **Validation**
- **Implementation notes** / **Technical notes**
- **CI readiness**

### Content Extraction

The automation extracts sections using flexible matching:
- Matches both `## Heading` and plain `Heading` on its own line
- Stops at the next recognized section header
- Preserves all content including lists, code blocks, and formatting

---

## Examples

### Example 1: Minimal Issue

```markdown
## Why
Need to consolidate duplicate workflows.

Scope
One workflow handling both commands and body updates.

## Tasks
- Create new workflow
- Retire old workflows

## Acceptance criteria
- No duplicate runs
- All commands work
```

**Labels**: `agent:codex`, `workflows`, `refactor`

### Example 2: Detailed Issue

```markdown
## Why
The current setup runs two separate workflows that can race when updating PR bodies.

## Scope
Create a unified `agents-pr-meta.yml` workflow with:
- Command listener job
- Body update job
- Shared concurrency group

Non-Goals
We are NOT changing the command syntax or marker format.

## Tasks
- [ ] Create agents-pr-meta.yml with two jobs
- [ ] Add concurrency group keyed by PR number
- [ ] Retire agents-64-pr-comment-commands.yml
- [ ] Retire agents-74-pr-body-writer.yml
- [ ] Update documentation

## Acceptance criteria
- Commands and body updates never run concurrently for the same PR
- Marker updates do not overwrite unrelated PR text
- All existing commands continue to work

## Implementation notes
Branch: codex/issue-3056
Files: .github/workflows/agents-pr-meta.yml
```

**Labels**: `agent:codex`, `priority: medium`, `workflows`, `refactor`

### Example 3: ChatGPT Topic

```
🚀 Implement rate limiting for API endpoints
agent:codex
priority: high
enhancement
api
security

Current API has no rate limiting which makes it vulnerable to abuse.
Need to implement token bucket algorithm with configurable limits
per endpoint and per user.

Technical requirements:
- Redis for rate limit storage
- Configurable limits in environment variables
- Return 429 status with Retry-After header
- Log rate limit violations for monitoring
```

---

## Tips

1. **Start Simple**: Begin with Why, Scope, Tasks, and Acceptance criteria
2. **Be Specific**: Clear acceptance criteria help the automation track progress
3. **Use Checklists**: Tasks and acceptance criteria work well as checkbox lists
4. **Add Context**: Implementation notes help when specific files or patterns are needed
5. **Consistent Labels**: Always include exactly one `agent:*` label
6. **Test First**: Validate your topic file format with a small test run before bulk processing

---

## Related Documentation

- [ISSUE_SYNC.md](./ISSUE_SYNC.md) - Label policy and sync behavior
- [AGENTS_POLICY.md](./AGENTS_POLICY.md) - Overall agents automation guardrails
- [WORKFLOW_SYSTEM.md](./WORKFLOW_SYSTEM.md) - Workflow architecture and triggers

---

**Last Updated**: October 26, 2025
