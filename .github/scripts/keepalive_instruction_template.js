'use strict';

const fs = require('fs');
const path = require('path');
const { resolvePromptMode } = require('./keepalive_prompt_routing');

/**
 * Path to the fallback keepalive instruction template.
 * Edit .github/templates/keepalive-instruction.md to change the fallback text.
 */
const TEMPLATE_PATH = path.resolve(__dirname, '../templates/keepalive-instruction.md');
const NEXT_TASK_TEMPLATE_PATH = path.resolve(__dirname, '../codex/prompts/keepalive_next_task.md');
const FIX_TEMPLATE_PATH = path.resolve(__dirname, '../codex/prompts/fix_ci_failures.md');
const VERIFY_TEMPLATE_PATH = path.resolve(__dirname, '../codex/prompts/verifier_acceptance_check.md');

const TEMPLATE_PATHS = {
  normal: NEXT_TASK_TEMPLATE_PATH,
  fix_ci: FIX_TEMPLATE_PATH,
  verify: VERIFY_TEMPLATE_PATH,
};

/**
 * Cached instruction text (loaded once per process).
 * @type {Map<string,string>}
 */
const instructionCache = new Map();

function normalise(value) {
  return String(value ?? '').trim();
}

function resolveTemplatePath({ templatePath, mode, action, reason, scenario } = {}) {
  const explicit = normalise(templatePath);
  if (explicit) {
    return { mode: 'custom', path: explicit };
  }
  const resolvedMode = resolvePromptMode({ mode, action, reason, scenario });
  return { mode: resolvedMode, path: TEMPLATE_PATHS[resolvedMode] || TEMPLATE_PATH };
}

function getFallbackInstruction() {
  return [
    'Your objective is to satisfy the **Acceptance Criteria** by completing each **Task** within the defined **Scope**.',
    '',
    '**This round you MUST:**',
    '1. Implement actual code or test changes that advance at least one incomplete task toward acceptance.',
    '2. Commit meaningful source code (.py, .yml, .js, etc.)—not just status/docs updates.',
    '3. **UPDATE THE CHECKBOXES** in the Tasks and Acceptance Criteria sections below to mark completed items.',
    '4. Change `- [ ]` to `- [x]` for items you have completed and verified.',
    '',
    '**CRITICAL - Checkbox Updates:**',
    'When you complete a task or acceptance criterion, update its checkbox directly in this prompt file.',
    'Change the `[ ]` to `[x]` for completed items. The automation will read these checkboxes and update the PR status summary.',
    '',
    '**Example:**',
    'Before: `- [ ] Add validation for user input`',
    'After:  `- [x] Add validation for user input`',
    '',
    '**DO NOT:**',
    '- Commit only status files, markdown summaries, or documentation when tasks require code.',
    '- Mark checkboxes complete without actually implementing and verifying the work.',
    '- Close the round without source-code changes when acceptance criteria require them.',
    '- Change the text of checkboxes—only change `[ ]` to `[x]`.',
    '',
    'Review the Scope/Tasks/Acceptance below, identify the next incomplete task that requires code, implement it, then **update the checkboxes** to mark completed items.',
  ].join('\n');
}

function loadInstruction(templatePath, { allowDefaultFallback = true } = {}) {
  const resolvedPath = templatePath || TEMPLATE_PATH;
  if (instructionCache.has(resolvedPath)) {
    return instructionCache.get(resolvedPath);
  }

  let content = '';
  try {
    content = fs.readFileSync(resolvedPath, 'utf8').trim();
  } catch (err) {
    if (allowDefaultFallback && resolvedPath !== TEMPLATE_PATH) {
      try {
        content = fs.readFileSync(TEMPLATE_PATH, 'utf8').trim();
      } catch (fallbackError) {
        console.warn(
          `Warning: Could not load keepalive instruction template from ${resolvedPath}: ${fallbackError.message}`
        );
        content = getFallbackInstruction();
      }
    } else {
      console.warn(`Warning: Could not load keepalive instruction template from ${resolvedPath}: ${err.message}`);
      content = getFallbackInstruction();
    }
  }

  instructionCache.set(resolvedPath, content);
  return content;
}

/**
 * Returns the canonical keepalive instruction directive text.
 * The text is loaded from .github/templates/keepalive-instruction.md.
 * 
 * @returns {string} The instruction directive (without @agent prefix)
 */
function getKeepaliveInstruction(options = {}) {
  const params = options && typeof options === 'object' ? options : {};
  const resolved = resolveTemplatePath(params);
  return loadInstruction(resolved.path, { allowDefaultFallback: true });
}

/**
 * Returns the full keepalive instruction with @agent prefix.
 * 
 * @param {string} [agent='codex'] - The agent alias to mention
 * @returns {string} The full instruction with @agent prefix
 */
function getKeepaliveInstructionWithMention(agent = 'codex', options = {}) {
  let resolvedAgent = agent;
  let params = options;

  if (agent && typeof agent === 'object') {
    params = agent;
    resolvedAgent = params.agent;
  }

  const alias = String(resolvedAgent || '').trim() || 'codex';
  return `@${alias} ${getKeepaliveInstruction(params)}`;
}

/**
 * Clears the cached instruction (useful for testing).
 */
function clearCache() {
  instructionCache.clear();
}

module.exports = {
  TEMPLATE_PATH,
  NEXT_TASK_TEMPLATE_PATH,
  FIX_TEMPLATE_PATH,
  VERIFY_TEMPLATE_PATH,
  getKeepaliveInstruction,
  getKeepaliveInstructionWithMention,
  clearCache,
};
