// @ts-check
// The agents guard acts as a safety net for automation workflows. It protects
// critical agent entry points from unauthorized changes and now also asserts
// that pull_request_target executions never checkout untrusted refs or echo
// repository secrets.

const fs = require('fs');
const path = require('path');

const DEFAULT_MARKER = '<!-- agents-guard-marker -->';

const DEFAULT_PROTECTED_PATHS = ['.github/workflows/agents-*.yml'];
const ALLOW_REMOVED_PATHS = new Set(
  [
    // Keepalive consolidation retired the standalone keepalive sweeps.
    '.github/workflows/agents-75-keepalive-on-gate.yml',
    '.github/workflows/agents-keepalive-pr.yml',
    // Issue intake now serves as the sole public entry point; the
    // ChatGPT wrapper was intentionally removed.
    '.github/workflows/agents-63-chatgpt-issue-sync.yml',
    // Clean up retired agent workflows from .github/workflows to reduce noise.
    '.github/workflows/agents-64-pr-comment-commands.yml',
    '.github/workflows/agents-74-pr-body-writer.yml',
    // Legacy pr-meta workflows superseded by agents-pr-meta-v4.yml.
    // v1 had corrupted workflow ID, v2/v3 were still running and failing.
    // Archived to archives/github-actions/2025-12-02-pr-meta-legacy/
    '.github/workflows/agents-pr-meta.yml',
    '.github/workflows/agents-pr-meta-v2.yml',
    '.github/workflows/agents-pr-meta-v3.yml',
  ].map((entry) => entry.toLowerCase()),
);

const PULL_REQUEST_TARGET_EVENT = 'pull_request_target';
const HEAD_SHA_REF_REGEX = /\bref:\s*\$\{\{\s*github\.event\.pull_request\.head\.sha\s*\}\}/i;
const SECRETS_EXPRESSION_REGEX = /\$\{\{\s*secrets\.[^}]+\}\}/i;

function escapeRegex(text) {
  return text.replace(/[.+^${}()|[\]\\]/g, '\\$&');
}

function globToRegExp(glob) {
  let result = '';
  let i = 0;
  while (i < glob.length) {
    const char = glob[i];
    if (char === '*') {
      const nextChar = glob[i + 1];
      if (nextChar === '*') {
        result += '.*';
        i += 2;
      } else {
        result += '[^/]*';
        i += 1;
      }
    } else if (char === '?') {
      result += '[^/]';
      i += 1;
    } else {
      result += escapeRegex(char);
      i += 1;
    }
  }
  return new RegExp(`^${result}$`);
}

function normalizePattern(pattern) {
  return pattern.replace(/^\/+/, '');
}

function detectPullRequestTargetViolations(source) {
  const lines = String(source || '').split(/\r?\n/);
  const violations = [];

  let checkoutState = null;
  let runBlockState = null;

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const indent = (rawLine.match(/^\s*/) || [''])[0].length;
    const trimmed = rawLine.trim();
    const isComment = /^\s*#/.test(rawLine);

    if (checkoutState && (indent < checkoutState.indent || (indent === checkoutState.indent && /^-\s+/.test(trimmed)))) {
      checkoutState = null;
    }

    if (runBlockState && indent <= runBlockState.indent && trimmed !== '') {
      runBlockState = null;
    }

    if (runBlockState) {
      if (!isComment && SECRETS_EXPRESSION_REGEX.test(rawLine)) {
        violations.push({
          type: 'secrets-run',
          line: index + 1,
          snippet: trimmed || rawLine.trim(),
        });
      }
      continue;
    }

    if (isComment) {
      continue;
    }

    if (checkoutState && HEAD_SHA_REF_REGEX.test(trimmed)) {
      violations.push({
        type: 'checkout-head-sha',
        line: index + 1,
        snippet: trimmed,
        anchor: checkoutState.line,
      });
      checkoutState = null;
      continue;
    }

    let usesMatch = rawLine.match(/^(\s*)-\s+uses:\s*actions\/checkout\b/i);
    if (!usesMatch) {
      usesMatch = rawLine.match(/^(\s*)uses:\s*actions\/checkout\b/i);
    }
    if (usesMatch) {
      checkoutState = { indent: usesMatch[1].length, line: index + 1 };
      continue;
    }

    let runMatch = rawLine.match(/^(\s*)-\s+run:\s*([|>])?\s*(.*)$/);
    if (!runMatch) {
      runMatch = rawLine.match(/^(\s*)run:\s*([|>])?\s*(.*)$/);
    }
    if (runMatch) {
      const inlineCommand = runMatch[3] || '';
      if (inlineCommand && SECRETS_EXPRESSION_REGEX.test(inlineCommand)) {
        violations.push({
          type: 'secrets-run',
          line: index + 1,
          snippet: inlineCommand.trim(),
        });
      }

      if (runMatch[2]) {
        runBlockState = { indent: runMatch[1].length, line: index + 1 };
      }
    }
  }

  return violations;
}

function formatPullRequestTargetViolation(violation) {
  if (!violation || typeof violation !== 'object') {
    return '• Unsafe workflow pattern detected.';
  }

  const line = violation.line ? `Line ${violation.line}` : 'Unspecified line';
  switch (violation.type) {
    case 'checkout-head-sha':
      return `${line}: actions/checkout must not target github.event.pull_request.head.sha in pull_request_target workflows.`;
    case 'secrets-run':
      return `${line}: run command references the secrets context (${violation.snippet || '${{ secrets.* }}'}).`;
    default:
      return `${line}: Unsafe workflow pattern detected.`;
  }
}

function validatePullRequestTargetSafety({
  eventName = process.env.GITHUB_EVENT_NAME || '',
  workflowPath = '.github/workflows/agents-guard.yml',
  workspaceRoot = process.env.GITHUB_WORKSPACE || process.cwd(),
  fsModule = fs,
} = {}) {
  const normalizedEvent = String(eventName || '').toLowerCase();
  if (normalizedEvent !== PULL_REQUEST_TARGET_EVENT) {
    return { checked: false, violations: [] };
  }

  const resolvedPath = path.resolve(workspaceRoot, workflowPath);

  let source;
  try {
    source = fsModule.readFileSync(resolvedPath, { encoding: 'utf-8' });
  } catch (error) {
    throw new Error(`Failed to read ${workflowPath}: ${error.message}`);
  }

  const violations = detectPullRequestTargetViolations(source);
  if (violations.length > 0) {
    const bulletList = violations.map((violation) => formatPullRequestTargetViolation(violation)).join('\n');
    throw new Error(
      `Unsafe pull_request_target usage detected in ${workflowPath}:\n${bulletList}`,
    );
  }

  return { checked: true, violations: [] };
}

function parseCodeowners(content) {
  if (!content) {
    return [];
  }

  const entries = [];
  const lines = content.split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const parts = line.split(/\s+/).filter(Boolean);
    if (parts.length < 2) {
      continue;
    }

    const pattern = parts[0];
    const normalized = normalizePattern(pattern);
    const owners = parts.slice(1);
    entries.push({
      pattern,
      owners,
      regex: globToRegExp(normalized),
    });
  }

  return entries;
}

function findCodeowners(entries, filePath) {
  const normalizedPath = filePath.replace(/^\/+/, '');
  let owners = [];
  for (const entry of entries) {
    if (entry.regex.test(normalizedPath)) {
      owners = entry.owners;
    }
  }
  return owners;
}

function listRelevantFiles(files) {
  return files.filter((file) => {
    if (!file || typeof file !== 'object') {
      return false;
    }

    const current = file.filename || '';
    const previous = file.previous_filename || '';

    // Treat most agents-* workflows as relevant, but allow a small
    // unprotected exceptions list for utility workflows (e.g. agents-64).
    if (current.startsWith('.github/workflows/agents-')) {
      // agents-64-verify-agent-assignment.yml is intentionally excluded from guard protection
      // because it is a utility workflow used to verify agent assignment and does not affect
      // agent logic or security. This policy is documented in .github/README.md under
      // "Workflow Guard Exceptions". If you need to change this policy, update both this file
      // and the documentation accordingly.
      if (current.endsWith('agents-64-verify-agent-assignment.yml')) {
        return false;
      }
      return true;
    }
    if (previous && previous.startsWith('.github/workflows/agents-')) {
      return true;
    }
    return false;
  });
}

function summarizeTouchedFiles(files) {
  if (!files.length) {
    return '- (no files in scope detected)';
  }

  return files
    .map((file) => {
      const current = file.filename || '';
      const previous = file.previous_filename || '';
      const status = file.status || '';

      if (status === 'renamed' && previous) {
        return `- ${previous} → ${current} (${status})`;
      }

      return `- ${current} (${status})`;
    })
    .join('\n');
}

function collectLatestApprovals(reviews) {
  const latestReviewStates = new Map();
  for (const review of reviews || []) {
    if (!review || typeof review !== 'object') {
      continue;
    }

    const login = review.user && review.user.login
      ? String(review.user.login).toLowerCase()
      : '';
    if (!login) {
      continue;
    }

    const state = review.state ? String(review.state).toUpperCase() : '';
    if (!state) {
      continue;
    }

    latestReviewStates.set(login, state);
  }

  return new Set(
    [...latestReviewStates.entries()]
      .filter(([, state]) => state === 'APPROVED')
      .map(([login]) => login),
  );
}

function extractLabelNames(labels) {
  return new Set(
    (labels || [])
      .map((label) => (label && label.name ? String(label.name).toLowerCase() : ''))
      .filter(Boolean),
  );
}

function evaluateGuard({
  files = [],
  labels = [],
  reviews = [],
  codeownersContent = '',
  protectedPaths = DEFAULT_PROTECTED_PATHS,
  labelName = 'agents:allow-change',
  authorLogin = '',
  marker = DEFAULT_MARKER,
} = {}) {
  const normalizedLabelName = String(labelName).toLowerCase();

  const protectedEntries = (protectedPaths || [])
    .map((pattern) => {
      const normalized = normalizePattern(pattern || '');
      const isGlob = /[*?]/.test(normalized);
      return {
        pattern: pattern || normalized,
        normalized,
        isGlob,
        regex: isGlob ? globToRegExp(normalized) : null,
      };
    })
    .filter((entry) => entry.normalized);

  const exactProtected = new Map(
    protectedEntries
      .filter((entry) => !entry.isGlob)
      .map((entry) => [entry.normalized, entry.pattern])
  );
  const globProtected = protectedEntries.filter((entry) => entry.isGlob);

  const matchProtectedPath = (filePath) => {
    if (!filePath) {
      return null;
    }
    const normalized = normalizePattern(filePath);
    if (!normalized) {
      return null;
    }
    if (exactProtected.has(normalized)) {
      return filePath;
    }
    for (const entry of globProtected) {
      if (entry.regex && entry.regex.test(normalized)) {
        return filePath;
      }
    }
    return null;
  };

  const relevantFiles = listRelevantFiles(files);
  const fatalViolations = [];
  const modifiedProtectedPaths = new Set();
  const touchedProtectedPaths = new Set();

  for (const file of relevantFiles) {
    const current = file.filename || '';
    const previous = file.previous_filename || '';
    const status = file.status || '';

    const protectedPath = matchProtectedPath(current) || (previous ? matchProtectedPath(previous) : null);

    const normalizedCurrent = normalizePattern(current).toLowerCase();
    const normalizedPrevious = normalizePattern(previous).toLowerCase();
    const removalAllowed =
      (normalizedCurrent && ALLOW_REMOVED_PATHS.has(normalizedCurrent)) ||
      (normalizedPrevious && ALLOW_REMOVED_PATHS.has(normalizedPrevious));

    if (protectedPath) {
      touchedProtectedPaths.add(protectedPath);
      if (status === 'removed') {
        if (removalAllowed) {
          continue;
        }
        fatalViolations.push(`• ${current} was deleted.`);
        continue;
      }

      if (status === 'renamed' && previous) {
        // Allow renames/moves of files in the ALLOW_REMOVED_PATHS list
        if (removalAllowed) {
          continue;
        }
        fatalViolations.push(`• ${previous} was renamed to ${current}.`);
        continue;
      }

      if (status === 'modified') {
        modifiedProtectedPaths.add(protectedPath);
      }
    }
  }

  const labelNames = extractLabelNames(labels);
  const hasAllowLabel = labelNames.has(normalizedLabelName);

  const approvedLogins = collectLatestApprovals(reviews);

  const codeownerEntries = parseCodeowners(codeownersContent);
  const codeownerLogins = new Set();
  const relevantCodeownerPaths = touchedProtectedPaths.size > 0
    ? [...touchedProtectedPaths]
    : protectedEntries.map((entry) => entry.pattern);

  for (const path of relevantCodeownerPaths) {
    const owners = findCodeowners(codeownerEntries, path);
    for (const ownerSlug of owners) {
      if (!ownerSlug || !ownerSlug.startsWith('@')) {
        continue;
      }
      const name = ownerSlug.slice(1).trim();
      if (!name || name.includes('/')) {
        // Team owners cannot be expanded without additional permissions.
        continue;
      }
      codeownerLogins.add(name.toLowerCase());
    }
  }

  const normalizedAuthor = authorLogin ? String(authorLogin).toLowerCase() : '';
  const authorIsCodeowner = normalizedAuthor && codeownerLogins.has(normalizedAuthor);
  const hasExternalApproval = [...codeownerLogins].some((login) => approvedLogins.has(login));
  const hasCodeownerApproval = hasExternalApproval || authorIsCodeowner;

  const hasProtectedChanges = modifiedProtectedPaths.size > 0;
  const needsApproval = hasProtectedChanges && !hasCodeownerApproval;
  const needsLabel = hasProtectedChanges && !hasAllowLabel && !hasCodeownerApproval;

  const failureReasons = [];
  if (fatalViolations.length > 0) {
    failureReasons.push(...fatalViolations);
  }

  if (modifiedProtectedPaths.size > 0 && (needsLabel || needsApproval)) {
    const modifiedList = [...modifiedProtectedPaths].map((path) => `• ${path}`).join('\n');
    failureReasons.push(`Protected workflows modified:\n${modifiedList}`);
    if (needsLabel) {
      failureReasons.push('Missing `agents:allow-change` label.');
    }
    if (needsApproval) {
      const codeownerHint = codeownerLogins.size > 0
        ? `Request approval from a CODEOWNER (${[...codeownerLogins].map((login) => `@${login}`).join(', ')}).`
        : 'Request approval from a CODEOWNER.';
      failureReasons.push(codeownerHint);
    }
  }

  const blocked = failureReasons.length > 0;
  const plainFirstReason = blocked
    ? failureReasons[0].replace(/^[\s•*-]+/, '').trim()
    : '';
  const summary = blocked
    ? (plainFirstReason
      ? `Health 45 Agents Guard blocked this PR: ${plainFirstReason}`
      : 'Health 45 Agents Guard blocked this PR.')
    : 'Health 45 Agents Guard passed.';

  let commentBody = null;
  let instructions = [];
  const touchedFilesText = summarizeTouchedFiles(relevantFiles);
  if (blocked) {
    instructions = [];
    if (fatalViolations.length > 0) {
      instructions.push('Restore the deleted or renamed workflows. These files cannot be moved or removed.');
    }
    if (needsLabel) {
      instructions.push('Apply the `agents:allow-change` label to this pull request once the change is justified.');
    }
    if (needsApproval) {
      if (codeownerLogins.size > 0) {
        const ownersList = [...codeownerLogins].map((login) => `@${login}`).join(', ');
        instructions.push(`Ask a CODEOWNER (${ownersList}) to review and approve the change.`);
      } else {
        instructions.push('Ask a CODEOWNER to review and approve the change.');
      }
    }
    instructions.push('Push an update or re-run this workflow after addressing the issues.');

    commentBody = [
      marker,
  '**Health 45 Agents Guard** stopped this pull request.',
      '',
      '**What we found**',
      ...failureReasons.map((reason) => `- ${reason}`),
      '',
      '**Next steps**',
      ...instructions.map((step) => `- ${step}`),
      '',
      '**Files seen in this run**',
      touchedFilesText,
    ].join('\n');
  }

  const warnings = [];
  if (blocked && fatalViolations.length === 0 && modifiedProtectedPaths.size === 0) {
    warnings.push('Guard triggered but no protected file changes were found.');
  }

  return {
    blocked,
    summary,
    marker,
    failureReasons,
    instructions,
    commentBody,
    touchedFilesText,
    warnings,
    hasAllowLabel,
    hasCodeownerApproval,
  authorIsCodeowner,
    needsLabel,
    needsApproval,
    modifiedProtectedPaths: [...modifiedProtectedPaths],
    touchedProtectedPaths: [...touchedProtectedPaths],
    fatalViolations,
    codeownerLogins: [...codeownerLogins],
    relevantFiles,
  };
}

module.exports = {
  DEFAULT_MARKER,
  DEFAULT_PROTECTED_PATHS,
  evaluateGuard,
  parseCodeowners,
  globToRegExp,
  validatePullRequestTargetSafety,
  detectPullRequestTargetViolations,
};

