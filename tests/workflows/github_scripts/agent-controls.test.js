'use strict';

// Expose the hosted agent-control suites to Node's default test discovery.
require('../../../.github/scripts/__tests__/bot-comment-handler.test.js');
require('../../../.github/scripts/__tests__/keepalive-cascade.test.js');
require('../../../.github/scripts/__tests__/fixtures/keepalive-gate-counter-cases.js');
require('../../../.github/scripts/__tests__/keepalive-state.test.js');
require('../../../.github/scripts/__tests__/should-post-review.test.js');
