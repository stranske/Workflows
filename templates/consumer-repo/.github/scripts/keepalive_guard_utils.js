'use strict';

const SKIP_MARKER = '<!-- keepalive-skip -->';
const SKIP_COUNT_REGEX = /<!--\s*keepalive-skip-count:\s*(\d+)\s*-->/i;
const SKIP_REASON_REGEX = /Keepalive\s+\d+\s+\S+\s+skipped:\s*([^\n\r]+)/i;

/**
 * Returns true when the provided skip reason represents a Gate-related guard outcome.
 * These failures should clear automatically once the Gate workflow completes.
 *
 * @param {string} reason
 * @returns {boolean}
 */
function isGateReason(reason) {
  const value = String(reason || '').trim().toLowerCase();
  if (!value) {
    return false;
  }
  if (value === 'gate-not-green') {
    return true;
  }
  return value.startsWith('gate');
}

/**
 * Analyse keepalive skip comments to determine retry history.
 *
 * @param {Array<{ body?: string }>} comments
 * @returns {{
 *   total: number,
 *   highestCount: number,
 *   gateCount: number,
 *   nonGateCount: number,
 *   reasons: string[],
 *   nonGateReasons: string[],
 * }}
 */
function analyseSkipComments(comments) {
  const result = {
    total: 0,
    highestCount: 0,
    gateCount: 0,
    nonGateCount: 0,
    reasons: [],
    nonGateReasons: [],
  };

  if (!Array.isArray(comments) || comments.length === 0) {
    return result;
  }

  for (const entry of comments) {
    if (!entry) {
      continue;
    }
    const body = String(entry.body || entry || '').trim();
    if (!body) {
      continue;
    }

    const hasMarker = body.includes(SKIP_MARKER);
    const reasonMatch = body.match(SKIP_REASON_REGEX);

    if (!hasMarker && !reasonMatch) {
      continue;
    }

    result.total += 1;

    const countMatch = body.match(SKIP_COUNT_REGEX);
    if (countMatch) {
      const parsed = Number.parseInt(countMatch[1], 10);
      if (Number.isFinite(parsed) && parsed > result.highestCount) {
        result.highestCount = parsed;
      }
    }

    if (reasonMatch) {
      const reason = reasonMatch[1]?.trim();
      if (reason) {
        result.reasons.push(reason);
        if (isGateReason(reason)) {
          result.gateCount += 1;
        } else {
          result.nonGateCount += 1;
          result.nonGateReasons.push(reason);
        }
      }
    }
  }

  if (result.highestCount === 0) {
    result.highestCount = result.total;
  }

  return result;
}

module.exports = {
  SKIP_MARKER,
  SKIP_COUNT_REGEX,
  SKIP_REASON_REGEX,
  analyseSkipComments,
  isGateReason,
};
