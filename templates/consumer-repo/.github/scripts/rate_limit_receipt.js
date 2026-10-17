'use strict';

const { RATE_LIMIT_RECEIPT_TTL_HOURS } = require('./rate_limit_receipt.json');

function rateLimitExpired(record, now = Date.now()) {
  const completed = Date.parse(record?.completed_at);
  return record?.completion?.reason === 'rate_limited' && Number.isFinite(completed) &&
    now - completed >= RATE_LIMIT_RECEIPT_TTL_HOURS * 60 * 60 * 1000;
}

module.exports = { RATE_LIMIT_RECEIPT_TTL_HOURS, rateLimitExpired };
