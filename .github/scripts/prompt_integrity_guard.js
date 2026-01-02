/**
 * prompt_integrity_guard.js - Validates Codex prompt template files for integrity
 * 
 * Ensures base prompt templates don't contain embedded task content that could
 * cause stale checkpoints. Task content must be dynamically injected via appendix.
 * 
 * Usage:
 *   node prompt_integrity_guard.js <prompt_file> [--strict]
 * 
 * Exit codes:
 *   0 - Clean template (no embedded task content detected)
 *   1 - Embedded task content detected (integrity violation)
 *   2 - File not found or usage error
 */

const fs = require('fs');
const path = require('path');

// Patterns that indicate embedded task content (should not be in base templates)
const TASK_CONTENT_PATTERNS = [
  {
    pattern: /^##\s+PR\s+Tasks\s+and\s+Acceptance\s+Criteria/m,
    description: 'PR Tasks header section'
  },
  {
    pattern: /^\*\*Progress:\*\*\s*\d+\/\d+/m,
    description: 'Progress counter (e.g., "Progress: 4/7")'
  },
  {
    pattern: /^###\s+Scope\n[\s\S]*?(?=^###|^$)/m,
    description: 'Scope section with content'
  },
  {
    pattern: /^###\s+Tasks\n[\s\S]*?-\s*\[[xX ]\]/m,
    description: 'Tasks section with checkboxes'
  },
  {
    pattern: /^###\s+Acceptance\s+Criteria\n[\s\S]*?-\s*\[[xX ]\]/m,
    description: 'Acceptance Criteria section with checkboxes'
  },
  {
    pattern: /-\s*\[[xX]\]\s+(?!Example|Template)/m,
    description: 'Checked checkbox (completed task)'
  },
  {
    pattern: /-\s*\[\s\]\s+(?:Extend|Add|Update|Create|Implement|Fix|Refactor|Test|Document)\s/m,
    description: 'Unchecked task with action verb'
  }
];

// Strict mode adds more aggressive patterns
const STRICT_PATTERNS = [
  {
    pattern: /issue[-_]?\d{3,}/i,
    description: 'Issue number reference (e.g., issue-453)'
  },
  {
    pattern: /PR\s*#?\d{3,}/i,
    description: 'PR number reference'
  },
  {
    pattern: /`[a-z_]+\.py`\s*(script|file)?/i,
    description: 'Specific Python file reference'
  }
];

/**
 * Check a prompt file for embedded task content
 * @param {string} filePath - Path to the prompt file
 * @param {boolean} strict - Enable strict mode with additional patterns
 * @returns {{clean: boolean, violations: Array<{line: number, match: string, description: string}>}}
 */
function checkPromptIntegrity(filePath, strict = false) {
  if (!fs.existsSync(filePath)) {
    console.error(`Error: File not found: ${filePath}`);
    process.exit(2);
  }

  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const violations = [];

  // Find the guard marker and check for content after the closing comment
  const guardMarkerIndex = content.indexOf('DO NOT ADD TASK CONTENT BELOW THIS LINE');
  
  if (guardMarkerIndex >= 0) {
    // Find the closing --> after the guard marker
    const afterMarker = content.substring(guardMarkerIndex);
    const closingCommentIndex = afterMarker.indexOf('-->');
    
    if (closingCommentIndex >= 0) {
      // Get content after the closing comment
      const contentAfterComment = afterMarker.substring(closingCommentIndex + 3).trim();
      
      if (contentAfterComment.length > 0) {
        violations.push({
          line: findLineNumber(lines, contentAfterComment.substring(0, 50)),
          match: contentAfterComment.substring(0, 100) + (contentAfterComment.length > 100 ? '...' : ''),
          description: 'Content found after guard marker (should be empty or comments only)'
        });
      }
    }
  }

  // Check content BEFORE the guard marker for task patterns
  const contentToCheck = guardMarkerIndex >= 0 
    ? content.substring(0, guardMarkerIndex)
    : content;
  // Check the relevant content section for task patterns
  const patternsToCheck = strict 
    ? [...TASK_CONTENT_PATTERNS, ...STRICT_PATTERNS] 
    : TASK_CONTENT_PATTERNS;

  for (const { pattern, description } of patternsToCheck) {
    const match = contentToCheck.match(pattern);
    if (match) {
      const lineNum = findLineNumber(lines, match[0]);
      violations.push({
        line: lineNum,
        match: match[0].substring(0, 80) + (match[0].length > 80 ? '...' : ''),
        description
      });
    }
  }

  return {
    clean: violations.length === 0,
    violations
  };
}

/**
 * Find the line number of a match in the content
 */
function findLineNumber(lines, searchStr) {
  const needle = searchStr.split('\n')[0].trim();
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(needle)) {
      return i + 1;
    }
  }
  return -1;
}

/**
 * Format violations for output
 */
function formatViolations(violations, filePath) {
  const header = `\n❌ PROMPT INTEGRITY VIOLATION: ${filePath}\n`;
  const divider = '─'.repeat(60);
  
  let output = header + divider + '\n\n';
  output += 'The base prompt template contains embedded task content.\n';
  output += 'This causes stale checkpoints when the template is used for different issues.\n\n';
  output += 'Violations found:\n\n';

  for (const v of violations) {
    output += `  Line ${v.line}: ${v.description}\n`;
    output += `    Match: "${v.match}"\n\n`;
  }

  output += divider + '\n';
  output += 'Fix: Remove all task-specific content from the template.\n';
  output += 'Task content should only come from the dynamically-injected appendix.\n';
  
  return output;
}

// Main execution
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(`
Usage: node prompt_integrity_guard.js <prompt_file> [--strict]

Validates that Codex prompt template files don't contain embedded task content.

Options:
  --strict    Enable strict mode (check for issue numbers, specific file refs)
  --help, -h  Show this help message

Exit codes:
  0 - Template is clean
  1 - Embedded task content detected
  2 - File not found or usage error
`);
    process.exit(args.includes('--help') || args.includes('-h') ? 0 : 2);
  }

  const filePath = args.find(a => !a.startsWith('--'));
  const strict = args.includes('--strict');

  if (!filePath) {
    console.error('Error: No prompt file specified');
    process.exit(2);
  }

  const result = checkPromptIntegrity(filePath, strict);

  if (result.clean) {
    console.log(`✅ Prompt template is clean: ${filePath}`);
    process.exit(0);
  } else {
    console.error(formatViolations(result.violations, filePath));
    process.exit(1);
  }
}

module.exports = { checkPromptIntegrity, TASK_CONTENT_PATTERNS };
