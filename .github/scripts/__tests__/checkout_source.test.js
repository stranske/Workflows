'use strict';

const assert = require('assert');
const { describe, it } = require('node:test');
const { resolveCheckoutSource } = require('../checkout_source.js');

const baseContext = {
  repo: { owner: 'base', repo: 'project' },
  sha: 'base-sha',
  payload: {},
};

describe('resolveCheckoutSource', () => {
  it('prefers pull_request head metadata when available', () => {
    const context = {
      ...baseContext,
      payload: {
        pull_request: {
          head: {
            sha: 'pr-head',
            repo: { full_name: 'fork/project' },
          },
        },
      },
    };

    const result = resolveCheckoutSource({
      core: { warning: () => {} },
      context,
      fallbackRepo: 'base/project',
      fallbackRef: 'fallback',
    });

    assert.strictEqual(result.repository, 'fork/project');
    assert.strictEqual(result.ref, 'pr-head');
    assert.deepStrictEqual(result.warnings, []);
  });

  it('pulls workflow_run head metadata when pull_request is absent', () => {
    const context = {
      ...baseContext,
      payload: {
        workflow_run: {
          head_sha: 'run-head',
          head_repository: { full_name: 'run/repo' },
          pull_requests: [
            {
              head: {
                sha: 'run-pr-head',
                repo: { full_name: 'run/pr-repo' },
              },
            },
          ],
        },
      },
    };

    const result = resolveCheckoutSource({
      core: { warning: () => {} },
      context,
      fallbackRepo: 'base/project',
      fallbackRef: 'fallback',
    });

    assert.strictEqual(result.repository, 'run/pr-repo');
    assert.strictEqual(result.ref, 'run-pr-head');
    assert.deepStrictEqual(result.warnings, []);
  });

  it('falls back and warns when workflow_run lacks head metadata', () => {
    const context = {
      ...baseContext,
      payload: {
        workflow_run: {
          head_sha: '',
          head_repository: {},
          pull_requests: [],
        },
      },
    };

    const result = resolveCheckoutSource({
      core: { warning: () => {} },
      context,
      fallbackRepo: 'base/project',
      fallbackRef: 'fallback',
    });

    assert.strictEqual(result.repository, 'base/project');
    assert.strictEqual(result.ref, 'fallback');
    assert.ok(result.warnings.some((warning) => warning.includes('head repository missing')));
    assert.ok(result.warnings.some((warning) => warning.includes('head SHA missing')));
  });
});
