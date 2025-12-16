'use strict';

function normaliseNewlines(value) {
  return String(value || '').replace(/\r\n/g, '\n');
}

function findInstructionStart(body) {
  const markers = [
    /<!--\s*codex-keepalive-round[^>]*-->/i,
    /<!--\s*keepalive-round[^>]*-->/i,
    /<!--\s*keepalive-attempt[^>]*-->/i,
    /<!--\s*codex-keepalive-marker\s*-->/i,
  ];
  for (const marker of markers) {
    const index = body.search(marker);
    if (index >= 0) {
      return index;
    }
  }
  return 0;
}

const EXCLUSION_PATTERNS = [
  /\n\*\*\s*Head\s*SHA[^:]*:/i,
  /\n\*\*\s*Latest\s+Runs?[^:]*:/i,
  /\n\*\*\s*Required\s+Status\s+Checks[^:]*:/i,
  /\n\*\*\s*Workflow\s*\/\s*Job[^:]*:/i,
  /\n\*\*\s*Workflow\s*\/\s*Job\s*Result\s*Logs[^:]*:/i,
  /\n\*\*\s*Coverage[^:]*:/i,
  /\n\|\s*Workflow\s*\/\s*Job\s*\|/i,
];

function trimAfterExclusions(text) {
  let end = text.length;
  for (const pattern of EXCLUSION_PATTERNS) {
    const index = text.search(pattern);
    if (index >= 0 && index < end) {
      end = index;
    }
  }
  if (end < text.length) {
    return text.slice(0, end);
  }
  return text;
}

function extractInstructionSegment(body) {
  if (!body) {
    return '';
  }
  const normalised = normaliseNewlines(body).trimStart();
  if (!normalised) {
    return '';
  }
  const startIndex = findInstructionStart(normalised);
  const sliced = normalised.slice(startIndex);
  if (!sliced.trim()) {
    return '';
  }
  return trimAfterExclusions(sliced).trimEnd();
}

function computeInstructionByteLength(text) {
  return Buffer.byteLength(String(text || ''), 'utf8');
}

module.exports = {
  extractInstructionSegment,
  computeInstructionByteLength,
};
