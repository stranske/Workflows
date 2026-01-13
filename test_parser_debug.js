const parser = require('./.github/scripts/issue_scope_parser.js');

const testIssue = `## Why

LLMs will comply with malicious or nonsensical instructions unless explicitly constrained. Security is not optional:
- Prompt injection can leak system prompts or execute unintended operations
- Unbounded config changes can break the analysis or produce misleading results
- File access must be strictly controlled

## Scope

Implement comprehensive security guardrails for the NL layer.

## Tasks

### Input Sanitization
- [ ] Strip potential injection patterns
- [ ] Limit instruction length (e.g., 1000 chars)

### File Access Control
- [ ] Allowlist directories
- [ ] No symlink following

## Acceptance Criteria

- [ ] Adversarial test suite blocks all known injection patterns
- [ ] Path traversal is blocked
`;

if (require.main === module) {
  const result = parser.parseScopeTasksAcceptanceSections(testIssue);
  console.log('=== PARSED SECTIONS ===');
  console.log('Scope:', result.scope);
  console.log('\nTasks:', result.tasks);
  console.log('\nAcceptance:', result.acceptance);
}
