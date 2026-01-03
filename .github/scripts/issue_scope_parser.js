'use strict';

const normalizeNewlines = (value) => String(value || '').replace(/\r\n/g, '\n');
const stripBlockquotePrefixes = (value) =>
  String(value || '').replace(/^[ \t]*>+[ \t]?/gm, '');
const LIST_ITEM_REGEX = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

const SECTION_DEFS = [
  { key: 'scope', label: 'Scope', aliases: ['Scope', 'Issue Scope', 'Why', 'Background', 'Context', 'Overview'], optional: true },
  {
    key: 'tasks',
    label: 'Tasks',
    aliases: ['Tasks', 'Task', 'Task List', 'Implementation', 'Implementation notes', 'To Do', 'Todo', 'To-Do'],
    optional: false,
  },
  {
    key: 'acceptance',
    label: 'Acceptance Criteria',
    aliases: ['Acceptance Criteria', 'Acceptance', 'Acceptance criteria', 'Definition of Done', 'Done Criteria'],
    optional: false,
  },
];

const PLACEHOLDERS = {
  scope: '_No scope information provided_',
  tasks: '- [ ] _No tasks defined_',
  acceptance: '- [ ] _No acceptance criteria defined_',
};

// Fallback placeholders used by PR meta manager when source issue lacks sections
// Note: scope uses plain text (not checkbox) since it's informational, not actionable
const PR_META_FALLBACK_PLACEHOLDERS = {
  scope: '_Scope section missing from source issue._',
  tasks: '- [ ] Tasks section missing from source issue.',
  acceptance: '- [ ] Acceptance criteria section missing from source issue.',
};

const CHECKBOX_SECTIONS = new Set(['tasks', 'acceptance']);

function normaliseSectionContent(sectionKey, content) {
  const trimmed = String(content || '').trim();
  if (!trimmed) {
    return '';
  }
  if (CHECKBOX_SECTIONS.has(sectionKey)) {
    return normaliseChecklist(trimmed).trim();
  }
  return trimmed;
}

function isPlaceholderContent(sectionKey, content) {
  const normalized = normaliseSectionContent(sectionKey, content);
  if (!normalized) {
    return false;
  }

  // Check against standard placeholders
  const placeholder = PLACEHOLDERS[sectionKey];
  if (placeholder) {
    const placeholderNormalized = normaliseSectionContent(sectionKey, placeholder);
    if (normalized === placeholderNormalized) {
      return true;
    }
  }

  // Check against PR meta manager fallback placeholders
  const fallbackPlaceholder = PR_META_FALLBACK_PLACEHOLDERS[sectionKey];
  if (fallbackPlaceholder) {
    const fallbackNormalized = normaliseSectionContent(sectionKey, fallbackPlaceholder);
    if (normalized === fallbackNormalized) {
      return true;
    }
  }

  return false;
}

function normaliseChecklist(content) {
  const raw = String(content || '');
  if (!raw.trim()) {
    return raw;
  }

  const lines = raw.split('\n');
  let mutated = false;
  const updated = lines.map((line) => {
    const match = line.match(LIST_ITEM_REGEX);
    if (!match) {
      return line;
    }
    const [, indent, bullet, remainderRaw] = match;
    const remainder = remainderRaw.trim();
    if (!remainder) {
      return line;
    }
    if (/^\[[ xX]\]/.test(remainder)) {
      return `${indent}${bullet} ${remainder}`;
    }
    
    mutated = true;
    return `${indent}${bullet} [ ] ${remainder}`;
  });

  return mutated ? updated.join('\n') : raw;
}

function stripHeadingMarkers(rawLine) {
  if (!rawLine) {
    return '';
  }
  let text = String(rawLine).trim();
  if (!text) {
    return '';
  }
  text = text.replace(/^#{1,6}\s+/, '');
  text = text.replace(/\s*:\s*$/, '');

  const boldMatch = text.match(/^(?:\*\*|__)(.+)(?:\*\*|__)$/);
  if (boldMatch) {
    text = boldMatch[1].trim();
  }

  text = text.replace(/\s*:\s*$/, '');
  return text.trim();
}

function extractHeadingLabel(rawLine) {
  const cleaned = stripHeadingMarkers(rawLine);
  if (!cleaned) {
    return '';
  }
  return cleaned;
}

function extractListBlocks(lines) {
  const blocks = [];
  let current = [];

  const flush = () => {
    if (current.length) {
      const block = current.join('\n').trim();
      if (block) {
        blocks.push(block);
      }
      current = [];
    }
  };

  for (const line of lines) {
    if (LIST_ITEM_REGEX.test(line)) {
      current.push(line);
      continue;
    }
    if (current.length) {
      if (!line.trim()) {
        current.push(line);
        continue;
      }
      flush();
    }
  }
  flush();

  return blocks;
}

function inferSectionsFromLists(segment) {
  const sections = { scope: '', tasks: '', acceptance: '' };
  const lines = String(segment || '').split('\n');
  const firstListIndex = lines.findIndex((line) => LIST_ITEM_REGEX.test(line));
  if (firstListIndex === -1) {
    return sections;
  }

  const preListText = lines.slice(0, firstListIndex).join('\n').trim();
  if (preListText) {
    sections.scope = preListText;
  }

  const listBlocks = extractListBlocks(lines.slice(firstListIndex));
  if (listBlocks.length > 0) {
    sections.tasks = listBlocks[0];
  }
  if (listBlocks.length > 1) {
    sections.acceptance = listBlocks[1];
  }

  return sections;
}

function collectSections(source) {
  const normalized = stripBlockquotePrefixes(normalizeNewlines(source));
  if (!normalized.trim()) {
    return { segment: '', sections: {}, labels: {} };
  }

  const startMarker = '<!-- auto-status-summary:start -->';
  const endMarker = '<!-- auto-status-summary:end -->';
  const startIndex = normalized.indexOf(startMarker);
  const endIndex = normalized.indexOf(endMarker);

  let segment = normalized;
  if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
    segment = normalized.slice(startIndex + startMarker.length, endIndex);
  }

  const aliasLookup = SECTION_DEFS.reduce((acc, section) => {
    section.aliases.forEach((alias) => {
      acc[alias.toLowerCase()] = section;
    });
    return acc;
  }, {});

  const headings = [];
  const lines = segment.split('\n');
  let offset = 0;
  for (const line of lines) {
    const matchedLabel = extractHeadingLabel(line);
    if (matchedLabel) {
      const title = matchedLabel.toLowerCase();
      if (aliasLookup[title]) {
        const section = aliasLookup[title];
        headings.push({
          title: section.key,
          label: section.label,
          index: offset,
          length: line.length,
          matchedLabel,
        });
      }
    }
    offset += line.length + 1;
  }

  const extracted = SECTION_DEFS.reduce((acc, section) => {
    acc[section.key] = '';
    return acc;
  }, {});
  const labels = SECTION_DEFS.reduce((acc, section) => {
    acc[section.key] = section.label;
    return acc;
  }, {});

  if (headings.length === 0) {
    const inferred = inferSectionsFromLists(segment);
    const merged = {
      ...extracted,
      ...Object.fromEntries(
        Object.entries(inferred).filter(([, value]) => String(value || '').trim())
      ),
    };
    return { segment, sections: merged, labels };
  }

  for (const section of SECTION_DEFS) {
    const canonicalTitle = section.label;
    const header = headings.find((entry) => entry.title === section.key);
    if (!header) {
      continue; // Skip missing sections instead of failing
    }
    const nextHeader = headings
      .filter((entry) => entry.index > header.index)
      .sort((a, b) => a.index - b.index)[0];
    const contentStart = (() => {
      const start = header.index + header.length;
      if (segment[start] === '\n') {
        return start + 1;
      }
      return start;
    })();
    const contentEnd = nextHeader ? nextHeader.index : segment.length;
    const content = normalizeNewlines(segment.slice(contentStart, contentEnd)).trim();
    extracted[section.key] = content;
    labels[section.key] = header.matchedLabel?.trim() || canonicalTitle;
  }

  return { segment, sections: extracted, labels };
}

/**
 * Extracts Scope, Tasks/Task List, and Acceptance Criteria sections from issue text.
 *
 * The parser is intentionally tolerant:
 * - Accepts headings written as markdown headers (# Title), bold (**Title**), or plain text
 *   with or without a trailing colon (e.g., "Tasks:").
 * - Searches within auto-status-summary markers when present, falling back to the full body.
 *
 * @param {string} source - The issue body text to parse.
 * @returns {string} Formatted sections with #### headings, or an empty string if none were found.
 */
function resolveHeadingLabel(sectionKey, matchedLabel, canonicalTitle) {
  if (sectionKey !== 'tasks') {
    return canonicalTitle;
  }

  const raw = String(matchedLabel || '').trim();
  if (!raw) {
    return canonicalTitle;
  }

  const stripped = raw.replace(/:+$/, '').trim();
  if (!stripped) {
    return canonicalTitle;
  }

  const lowered = stripped.toLowerCase();
  if (lowered === 'tasks') {
    return 'Tasks';
  }
  if (lowered === 'task list') {
    return 'Task List';
  }

  return canonicalTitle;
}

const extractScopeTasksAcceptanceSections = (source, options = {}) => {
  const { sections, labels } = collectSections(source);
  const includePlaceholders = Boolean(options.includePlaceholders);

  const extracted = [];
  let started = false;
  for (const section of SECTION_DEFS) {
    const canonicalTitle = section.label;
    const headingLabel = resolveHeadingLabel(section.key, labels?.[section.key], canonicalTitle);
    const content = (sections[section.key] || '').trim();
    let body = content;
    if (!body && includePlaceholders) {
      body = PLACEHOLDERS[section.key] || '';
    }
    if (body && CHECKBOX_SECTIONS.has(section.key)) {
      body = normaliseChecklist(body);
    }
    if (!body) {
      if (!started && section.key === 'scope') {
        continue;
      }
      continue;
    }
    const headerLine = `#### ${headingLabel}`;
    extracted.push(`${headerLine}\n${body}`);
    started = true;
  }

  return extracted.join('\n\n').trim();
};

const parseScopeTasksAcceptanceSections = (source) => {
  const { sections } = collectSections(source);
  return sections;
};

const hasNonPlaceholderScopeTasksAcceptanceContent = (source) => {
  const { sections } = collectSections(source);
  if (!sections || typeof sections !== 'object') {
    return false;
  }
  return Object.entries(sections).some(([key, value]) => {
    const content = String(value || '').trim();
    if (!content) {
      return false;
    }
    return !isPlaceholderContent(key, content);
  });
};

const analyzeSectionPresence = (source) => {
  const { sections } = collectSections(source);
  const entries = SECTION_DEFS.map((section) => {
    const content = (sections[section.key] || '').trim();
    return {
      key: section.key,
      label: section.label,
      present: Boolean(content),
      optional: Boolean(section.optional),
    };
  });
  // Only report non-optional sections as missing
  const missing = entries
    .filter((entry) => !entry.present && !entry.optional)
    .map((entry) => entry.label);
  // Check if we have at least one actionable section (tasks or acceptance)
  const hasActionableContent = entries.some(
    (entry) => entry.present && (entry.key === 'tasks' || entry.key === 'acceptance')
  );
  return {
    entries,
    missing,
    hasAllRequired: missing.length === 0,
    hasActionableContent,
  };
};

module.exports = {
  extractScopeTasksAcceptanceSections,
  parseScopeTasksAcceptanceSections,
  hasNonPlaceholderScopeTasksAcceptanceContent,
  analyzeSectionPresence,
};
