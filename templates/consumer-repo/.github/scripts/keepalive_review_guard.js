'use strict';

const fs = require('node:fs');

const EMPTY_REVIEW_REASON = 'empty review result';
const REQUIRED_FIELDS = ['score', 'feedback', 'suggestions'];

const isBlank = (value) => {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  return false;
};

const hasAllBlankRequiredFields = (payload) =>
  REQUIRED_FIELDS.every((field) => isBlank(payload?.[field]));

const isEmptyReviewResult = (payload) => {
  if (payload === null || payload === undefined) return true;
  if (typeof payload === 'string') return payload.trim() === '';
  if (typeof payload !== 'object') return false;

  if ('review' in payload && isBlank(payload.review)) return true;

  if ('review' in payload) {
    if (isBlank(payload.review)) return true;
    if (payload.review && typeof payload.review === 'object') {
      return hasAllBlankRequiredFields(payload.review);
    }
    return false;
  }

  const hasRequiredField = REQUIRED_FIELDS.some((field) => field in payload);
  if (hasRequiredField) {
    return hasAllBlankRequiredFields(payload);
  }

  return true;
};

const evaluateReviewResult = (payload) => {
  if (isEmptyReviewResult(payload)) {
    return { shouldPost: false, reason: EMPTY_REVIEW_REASON };
  }

  return { shouldPost: true, reason: '' };
};

const loadReviewResult = (path) => {
  if (!path || !fs.existsSync(path)) {
    return { payload: null, readError: 'missing-file' };
  }

  try {
    const raw = fs.readFileSync(path, 'utf8');
    if (raw.trim() === '') {
      return { payload: '', readError: null };
    }

    return { payload: JSON.parse(raw), readError: null };
  } catch (error) {
    return { payload: null, readError: error?.message || 'invalid-json' };
  }
};

const main = () => {
  const filePath = process.argv[2];
  const { payload, readError } = loadReviewResult(filePath);
  const result = evaluateReviewResult(payload);

  const output = {
    ...result,
    readError,
  };

  process.stdout.write(`${JSON.stringify(output)}\n`);
};

if (require.main === module) {
  main();
}

module.exports = {
  EMPTY_REVIEW_REASON,
  evaluateReviewResult,
  isEmptyReviewResult,
  loadReviewResult,
};
