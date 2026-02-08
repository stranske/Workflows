'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

/**
 * post_completion_comment.js
 * 
 * Extracts completed checkboxes from codex-prompt.md and posts them as a PR comment.
 * This bridges the gap between Codex updating the prompt file and the status summary
 * which reads checkbox states from PR comments.
 * 
 * The posted comment will be picked up by fetchConnectorCheckboxStates in
 * agents_pr_meta_update_body.js and merged into the Automated Status Summary.
 */

const fs = require('fs');
const path = require('path');

const COMPLETION_COMMENT_MARKER = '<!-- codex-completion-checkpoint -->';

function isCodeFenceLine(line) {
  return /^\s*(```|~~~)/.test(String(line || ''));
}

/**
 * Extract checked checkboxes from markdown content.
 * @param {string} content - Markdown content
 * @returns {string[]} Array of checked item texts (without the checkbox prefix)
 */
function extractCheckedItems(content) {
  const items = [];
  const lines = String(content || '').split(/\r?\n/);
  let inCodeBlock = false;
  
  for (const line of lines) {
    if (isCodeFenceLine(line)) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) {
      continue;
    }
    // Match checked checkboxes: - [x] or - [X] or * [x] etc.
    const match = line.match(/^\s*[-*+]\s*\[[xX]\]\s*(.+)$/);
    if (match && match[1]) {
      const text = match[1].trim();
      // Skip placeholder items
      if (text && text !== '—' && !text.startsWith('_(')) {
        items.push(text);
      }
    }
  }
  
  return items;
}

/**
 * Extract section content between headers.
 * @param {string} content - Full markdown content
 * @param {string} sectionName - Name of the section to extract (can be a regex pattern)
 * @returns {string} Section content
 */
function extractSection(content, sectionName) {
  // Match ### Tasks or ## Tasks style headers
  const pattern = new RegExp(
    `^(#{2,3})\\s*${sectionName}\\s*$`,
    'im'
  );
  const match = content.match(pattern);
  if (!match) return '';
  
  const headerLevel = match[1].length;
  const headerIndex = match.index + match[0].length;
  
  // Find the next header of same or higher level
  const rest = content.slice(headerIndex);
  const nextHeaderPattern = new RegExp(`^#{1,${headerLevel}}\\s+\\S`, 'm');
  const nextMatch = rest.match(nextHeaderPattern);
  
  if (nextMatch) {
    return rest.slice(0, nextMatch.index).trim();
  }
  return rest.trim();
}

/**
 * Build the completion comment body.
 * @param {string[]} tasks - Completed task items
 * @param {string[]} acceptance - Completed acceptance criteria items
 * @param {object} metadata - Additional metadata (iteration, commit, etc.)
 * @returns {string} Comment body
 */
function buildCompletionComment(tasks, acceptance, metadata = {}) {
  const lines = [COMPLETION_COMMENT_MARKER];
  
  lines.push('## ✅ Codex Completion Checkpoint');
  lines.push('');
  
  if (metadata.iteration) {
    lines.push(`**Iteration:** ${metadata.iteration}`);
  }
  if (metadata.commitSha) {
    lines.push(`**Commit:** \`${metadata.commitSha.slice(0, 7)}\``);
  }
  lines.push(`**Recorded:** ${new Date().toISOString()}`);
  lines.push('');
  
  if (tasks.length > 0) {
    lines.push('### Tasks Completed');
    for (const task of tasks) {
      lines.push(`- [x] ${task}`);
    }
    lines.push('');
  }
  
  if (acceptance.length > 0) {
    lines.push('### Acceptance Criteria Met');
    for (const criterion of acceptance) {
      lines.push(`- [x] ${criterion}`);
    }
    lines.push('');
  }
  
  lines.push('<details>');
  lines.push('<summary>About this comment</summary>');
  lines.push('');
  lines.push('This comment is automatically generated to track task completions.');
  lines.push('The Automated Status Summary reads these checkboxes to update PR progress.');
  lines.push('Do not edit this comment manually.');
  lines.push('</details>');
  
  return lines.join('\n');
}

/**
 * Find existing completion checkpoint comment.
 * @param {Array} comments - PR comments
 * @returns {object|null} Existing comment or null
 */
function findExistingComment(comments) {
  if (!Array.isArray(comments)) return null;
  
  return comments.find(c => 
    c.body && c.body.includes(COMPLETION_COMMENT_MARKER)
  ) || null;
}

/**
 * Main function to post completion comment.
 * @param {object} params - Parameters
 * @param {object} params.github - GitHub API client
 * @param {object} params.context - GitHub Actions context
 * @param {object} params.core - GitHub Actions core
 * @param {object} params.inputs - Input parameters
 */
async function postCompletionComment({ github, context, core, inputs }) {
  const prNumber = Number(inputs.pr_number || inputs.prNumber || 0);
  if (!prNumber || prNumber <= 0) {
    core.info('No PR number provided, skipping completion comment.');
    return { posted: false, reason: 'no-pr-number' };
  }
  
  // Support PR-specific prompt files to avoid merge conflicts
  // Try PR-specific file first, fall back to generic name
  const basePromptFile = inputs.prompt_file || inputs.promptFile || 'codex-prompt.md';
  let promptFile = basePromptFile;
  const prSpecificFile = `codex-prompt-${prNumber}.md`;
  const prSpecificPath = path.resolve(process.cwd(), prSpecificFile);
  if (fs.existsSync(prSpecificPath)) {
    promptFile = prSpecificFile;
    core.info(`Using PR-specific prompt file: ${prSpecificFile}`);
  }
  const commitSha = inputs.commit_sha || inputs.commitSha || '';
  const iteration = inputs.iteration || '';
  
  // Read the prompt file
  let content;
  try {
    const filePath = path.resolve(process.cwd(), promptFile);
    if (!fs.existsSync(filePath)) {
      core.info(`Prompt file not found: ${filePath}`);
      return { posted: false, reason: 'file-not-found' };
    }
    content = fs.readFileSync(filePath, 'utf8');
  } catch (error) {
    core.warning(`Failed to read prompt file: ${error.message}`);
    return { posted: false, reason: 'read-error', error: error.message };
  }
  
  // Extract checked items from Tasks and Acceptance Criteria sections
  const tasksSection = extractSection(content, 'Tasks');
  const acceptanceSection = extractSection(content, 'Acceptance [Cc]riteria');
  
  const completedTasks = extractCheckedItems(tasksSection);
  const completedAcceptance = extractCheckedItems(acceptanceSection);
  
  core.info(`Found ${completedTasks.length} completed task(s) and ${completedAcceptance.length} acceptance criteria`);

  if (completedTasks.length === 0 && completedAcceptance.length === 0) {
    core.info('No new completions detected, skipping completion comment.');
    return { posted: false, reason: 'no-completions' };
  }
  
  // Build the comment
  const commentBody = buildCompletionComment(completedTasks, completedAcceptance, {
    iteration,
    commitSha,
  });
  
  const { owner, repo } = context.repo;
  
  try {
    // Check for existing completion comment
    const { data: comments } = await github.rest.issues.listComments({
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });
    
    const existingComment = findExistingComment(comments);
    
    if (existingComment) {
      // Update existing comment
      await github.rest.issues.updateComment({
        owner,
        repo,
        comment_id: existingComment.id,
        body: commentBody,
      });
      core.info(`Updated completion checkpoint comment (id: ${existingComment.id})`);
      return { 
        posted: true, 
        updated: true, 
        commentId: existingComment.id,
        tasks: completedTasks.length,
        acceptance: completedAcceptance.length,
      };
    } else {
      // Create new comment
      const { data: newComment } = await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: prNumber,
        body: commentBody,
      });
      core.info(`Created completion checkpoint comment (id: ${newComment.id})`);
      return { 
        posted: true, 
        created: true, 
        commentId: newComment.id,
        tasks: completedTasks.length,
        acceptance: completedAcceptance.length,
      };
    }
  } catch (error) {
    core.warning(`Failed to post completion comment: ${error.message}`);
    return { posted: false, reason: 'api-error', error: error.message };
  }
}

module.exports = {
  COMPLETION_COMMENT_MARKER,
  extractCheckedItems,
  extractSection,
  buildCompletionComment,
  findExistingComment,
  postCompletionComment: async function ({ github: rawGithub, context, core, inputs }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return postCompletionComment({ github, context, core, inputs });
  },
};
