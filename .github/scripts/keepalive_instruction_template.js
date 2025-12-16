'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Path to the canonical keepalive instruction template.
 * Edit .github/templates/keepalive-instruction.md to change the instruction text.
 */
const TEMPLATE_PATH = path.resolve(__dirname, '../templates/keepalive-instruction.md');

/**
 * Cached instruction text (loaded once per process).
 * @type {string|null}
 */
let cachedInstruction = null;

/**
 * Returns the canonical keepalive instruction directive text.
 * The text is loaded from .github/templates/keepalive-instruction.md.
 * 
 * @returns {string} The instruction directive (without @agent prefix)
 */
function getKeepaliveInstruction() {
  if (cachedInstruction !== null) {
    return cachedInstruction;
  }

  try {
    cachedInstruction = fs.readFileSync(TEMPLATE_PATH, 'utf8').trim();
  } catch (err) {
    // Fallback if template file is missing
    console.warn(`Warning: Could not load keepalive instruction template from ${TEMPLATE_PATH}: ${err.message}`);
    cachedInstruction = [
      'Your objective is to satisfy the **Acceptance Criteria** by completing each **Task** within the defined **Scope**.',
      '',
      '**This round you MUST:**',
      '1. Implement actual code or test changes that advance at least one incomplete task toward acceptance.',
      '2. Commit meaningful source code (.py, .yml, .js, etc.)—not just status/docs updates.',
      '3. Mark a task checkbox complete ONLY after verifying the implementation works.',
      '4. **POST A REPLY COMMENT** with completed checkboxes using the **EXACT TEXT** from the lists below.',
      '',
      '**CRITICAL - Checkbox Format:**',
      'When posting your reply, copy the **exact checkbox text** from the Tasks and Acceptance Criteria sections. Do NOT paraphrase or summarize. The automation matches text exactly.',
      '',
      '**Example reply format:**',
      '```',
      '- [x] Implemented volatility-adjusted trend analysis for Fund A',
      '- [x] Updated config/demo.yml with new parameters',
      '- [ ] Add multi-period analysis for Fund B',
      '',
      'Acceptance Criteria:',
      '- [x] Fund A analysis produces correct CAGR and Sharpe ratio',
      '- [ ] Fund B analysis includes multi-period metrics',
      '```',
      '',
      '**DO NOT:**',
      '- Commit only status files, markdown summaries, or documentation when tasks require code.',
      '- Re-post checklists without making implementation progress.',
      '- Close the round without source-code changes when acceptance criteria require them.',
      '- Paraphrase or shorten checkbox text—copy it exactly for tracking to work.',
      '',
      'Review the Scope/Tasks/Acceptance below, identify the next incomplete task that requires code, implement it, then **post a reply comment** with the completed items using their **exact original text**.',
    ].join('\n');
  }

  return cachedInstruction;
}

/**
 * Returns the full keepalive instruction with @agent prefix.
 * 
 * @param {string} [agent='codex'] - The agent alias to mention
 * @returns {string} The full instruction with @agent prefix
 */
function getKeepaliveInstructionWithMention(agent = 'codex') {
  const alias = String(agent || '').trim() || 'codex';
  return `@${alias} ${getKeepaliveInstruction()}`;
}

/**
 * Clears the cached instruction (useful for testing).
 */
function clearCache() {
  cachedInstruction = null;
}

module.exports = {
  TEMPLATE_PATH,
  getKeepaliveInstruction,
  getKeepaliveInstructionWithMention,
  clearCache,
};
