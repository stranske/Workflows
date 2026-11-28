'use strict';

// Preserve the agent-control cases found by bare `node --test`, which skips
// the hidden .github directory. Gate and Selftest run the canonical files directly.
require('../../../.github/scripts/__tests__/bot-comment-dismiss-contract.test.js');
require('../../../.github/scripts/__tests__/bot-comment-dismiss-glob-timestamp.test.js');
require('../../../.github/scripts/__tests__/bot-comment-handler.test.js');
require('../../../.github/scripts/__tests__/keepalive-cascade.test.js');
require('../../../.github/scripts/__tests__/fixtures/keepalive-gate-counter-cases.js');
require('../../../.github/scripts/__tests__/keepalive-state.test.js');
require('../../../.github/scripts/__tests__/should-post-review.test.js');
