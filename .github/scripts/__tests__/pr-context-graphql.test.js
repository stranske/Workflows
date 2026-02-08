'use strict';

const { describe, it, mock } = require('node:test');
const assert = require('node:assert');

const {
  fetchPRContext,
  fetchPRBasic,
  serializeForOutput,
  deserializeFromOutput,
  createPRContextCache
} = require('../pr-context-graphql');

// Mock GraphQL response for full PR context
const mockPRContextResponse = {
  repository: {
    pullRequest: {
      id: 'PR_123',
      number: 42,
      title: 'Test PR',
      body: 'PR description',
      state: 'OPEN',
      isDraft: false,
      mergeable: 'MERGEABLE',
      merged: false,
      mergedAt: null,
      headRefName: 'feature/test',
      baseRefName: 'main',
      headRefOid: 'abc123',
      author: { login: 'testuser' },
      labels: {
        nodes: [
          { name: 'bug', color: 'red' },
          { name: 'priority:high', color: 'orange' }
        ]
      },
      files: {
        totalCount: 3,
        nodes: [
          { path: 'src/index.js', additions: 10, deletions: 5, changeType: 'MODIFIED' },
          { path: 'tests/test.js', additions: 20, deletions: 0, changeType: 'ADDED' },
          { path: 'README.md', additions: 2, deletions: 1, changeType: 'MODIFIED' }
        ]
      },
      reviews: {
        nodes: [
          { state: 'APPROVED', author: { login: 'reviewer1' }, body: 'LGTM', submittedAt: '2026-01-13T00:00:00Z' }
        ]
      },
      comments: {
        totalCount: 5,
        nodes: [
          { author: { login: 'commenter1' }, body: 'Nice work!', createdAt: '2026-01-13T00:00:00Z', isMinimized: false },
          { author: { login: 'bot' }, body: 'CI passed', createdAt: '2026-01-13T00:01:00Z', isMinimized: true }
        ]
      },
      commits: {
        nodes: [
          {
            commit: {
              oid: 'abc123',
              message: 'feat: add feature',
              statusCheckRollup: {
                state: 'SUCCESS',
                contexts: {
                  nodes: [
                    { name: 'CI', conclusion: 'SUCCESS', status: 'COMPLETED' },
                    { name: 'lint', conclusion: 'SUCCESS', status: 'COMPLETED' }
                  ]
                }
              }
            }
          }
        ]
      }
    }
  }
};

// Mock GraphQL response for basic PR info
const mockPRBasicResponse = {
  repository: {
    pullRequest: {
      number: 42,
      title: 'Test PR',
      body: 'PR description',
      state: 'OPEN',
      isDraft: false,
      merged: false,
      headRefName: 'feature/test',
      baseRefName: 'main',
      headRefOid: 'abc123',
      author: { login: 'testuser' },
      labels: {
        nodes: [{ name: 'bug' }, { name: 'priority:high' }]
      }
    }
  }
};

const mockPRContextResponseWithAgents = {
  repository: {
    pullRequest: {
      ...mockPRContextResponse.repository.pullRequest,
      files: {
        totalCount: 4,
        nodes: [
          { path: 'src/index.js', additions: 10, deletions: 5, changeType: 'MODIFIED' },
          { path: 'tests/test.js', additions: 20, deletions: 0, changeType: 'ADDED' },
          { path: 'README.md', additions: 2, deletions: 1, changeType: 'MODIFIED' },
          { path: '.agents/issue-1234-ledger.yml', additions: 3, deletions: 1, changeType: 'MODIFIED' }
        ]
      }
    }
  }
};

const mockPRContextResponseWithDocs = {
  repository: {
    pullRequest: {
      ...mockPRContextResponse.repository.pullRequest,
      files: {
        totalCount: 4,
        nodes: [
          { path: 'src/index.js', additions: 10, deletions: 5, changeType: 'MODIFIED' },
          { path: 'docs/guide/intro.md', additions: 4, deletions: 0, changeType: 'ADDED' },
          { path: 'README.md', additions: 2, deletions: 1, changeType: 'MODIFIED' },
          { path: '.agents/issue-1234-ledger.yml', additions: 3, deletions: 1, changeType: 'MODIFIED' }
        ]
      }
    }
  }
};

describe('fetchPRContext', () => {
  it('fetches and transforms PR context correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(context.number, 42);
    assert.strictEqual(context.title, 'Test PR');
    assert.strictEqual(context.body, 'PR description');
    assert.strictEqual(context.state, 'OPEN');
    assert.strictEqual(context.isDraft, false);
    assert.strictEqual(context.author, 'testuser');
    assert.strictEqual(context.headRef, 'feature/test');
    assert.strictEqual(context.headSha, 'abc123');
  });
  
  it('extracts labels correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.deepStrictEqual(context.labels, ['bug', 'priority:high']);
    assert.strictEqual(context.hasLabel('bug'), true);
    assert.strictEqual(context.hasLabel('feature'), false);
    assert.strictEqual(context.hasAnyLabel(['feature', 'bug']), true);
    assert.strictEqual(context.hasAllLabels(['bug', 'priority:high']), true);
    assert.strictEqual(context.hasAllLabels(['bug', 'missing']), false);
  });
  
  it('extracts files correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(context.files.total, 3);
    assert.deepStrictEqual(context.files.paths, ['src/index.js', 'tests/test.js', 'README.md']);
    assert.strictEqual(context.files.detailed.length, 3);
  });

  it('filters ignored .agents ledger files by default', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponseWithAgents)
    };

    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);

    assert.strictEqual(context.files.total, 3);
    assert.strictEqual(context.files.ignored, 1);
    assert.strictEqual(context.files.unfilteredTotal, 4);
    assert.deepStrictEqual(context.files.ignoredPaths, ['.agents/issue-1234-ledger.yml']);
    assert.deepStrictEqual(context.files.paths, ['src/index.js', 'tests/test.js', 'README.md']);
  });

  it('respects custom ignored path patterns from env', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponseWithDocs)
    };
    const originalPaths = process.env.PR_CONTEXT_IGNORED_PATHS;
    const originalPatterns = process.env.PR_CONTEXT_IGNORED_PATTERNS;

    process.env.PR_CONTEXT_IGNORED_PATHS = 'docs/';
    process.env.PR_CONTEXT_IGNORED_PATTERNS = '.agents/issue-*-ledger.yml,docs/**/*.md';

    try {
      const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);

      assert.strictEqual(context.files.total, 2);
      assert.strictEqual(context.files.ignored, 2);
      assert.strictEqual(context.files.unfilteredTotal, 4);
      assert.deepStrictEqual(context.files.ignoredPaths, [
        'docs/guide/intro.md',
        '.agents/issue-1234-ledger.yml'
      ]);
      assert.deepStrictEqual(context.files.paths, ['src/index.js', 'README.md']);
    } finally {
      if (originalPaths === undefined) {
        delete process.env.PR_CONTEXT_IGNORED_PATHS;
      } else {
        process.env.PR_CONTEXT_IGNORED_PATHS = originalPaths;
      }
      if (originalPatterns === undefined) {
        delete process.env.PR_CONTEXT_IGNORED_PATTERNS;
      } else {
        process.env.PR_CONTEXT_IGNORED_PATTERNS = originalPatterns;
      }
    }
  });

  it('supports glob entries in PR_CONTEXT_IGNORED_PATHS', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponseWithAgents)
    };
    const originalPaths = process.env.PR_CONTEXT_IGNORED_PATHS;
    const originalPatterns = process.env.PR_CONTEXT_IGNORED_PATTERNS;

    process.env.PR_CONTEXT_IGNORED_PATHS = '.agents/**';
    delete process.env.PR_CONTEXT_IGNORED_PATTERNS;

    try {
      const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);

      assert.strictEqual(context.files.total, 3);
      assert.strictEqual(context.files.ignored, 1);
      assert.strictEqual(context.files.unfilteredTotal, 4);
      assert.deepStrictEqual(context.files.ignoredPaths, ['.agents/issue-1234-ledger.yml']);
      assert.deepStrictEqual(context.files.paths, ['src/index.js', 'tests/test.js', 'README.md']);
    } finally {
      if (originalPaths === undefined) {
        delete process.env.PR_CONTEXT_IGNORED_PATHS;
      } else {
        process.env.PR_CONTEXT_IGNORED_PATHS = originalPaths;
      }
      if (originalPatterns === undefined) {
        delete process.env.PR_CONTEXT_IGNORED_PATTERNS;
      } else {
        process.env.PR_CONTEXT_IGNORED_PATTERNS = originalPatterns;
      }
    }
  });

  it('extracts reviews correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(context.reviews.length, 1);
    assert.strictEqual(context.reviews[0].state, 'APPROVED');
    assert.strictEqual(context.reviews[0].author, 'reviewer1');
  });
  
  it('extracts comments correctly (filters minimized)', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(context.comments.total, 5);
    assert.strictEqual(context.comments.recent.length, 1); // Minimized comment filtered
    assert.strictEqual(context.comments.recent[0].body, 'Nice work!');
  });
  
  it('extracts last commit status correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(context.lastCommit.sha, 'abc123');
    assert.strictEqual(context.lastCommit.status, 'SUCCESS');
    assert.strictEqual(context.lastCommit.checks.length, 2);
  });
  
  it('throws enhanced error when PR not found', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => ({ repository: { pullRequest: null } }))
    };
    
    await assert.rejects(
      () => fetchPRContext(mockGithub, 'owner', 'repo', 999),
      /PR #999 not found in owner\/repo/
    );
  });
  
  it('handles missing optional fields gracefully', async () => {
    const minimalResponse = {
      repository: {
        pullRequest: {
          id: 'PR_123',
          number: 42,
          title: 'Test',
          body: null, // null body
          state: 'OPEN',
          isDraft: false,
          mergeable: null,
          merged: false,
          mergedAt: null,
          headRefName: 'test',
          baseRefName: 'main',
          headRefOid: 'abc',
          author: null, // null author
          labels: null, // null labels
          files: null,
          reviews: null,
          comments: null,
          commits: null
        }
      }
    };
    
    const mockGithub = {
      graphql: mock.fn(async () => minimalResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(context.body, '');
    assert.strictEqual(context.author, 'unknown');
    assert.deepStrictEqual(context.labels, []);
    assert.strictEqual(context.files.total, 0);
    assert.deepStrictEqual(context.files.ignoredPaths, []);
    assert.strictEqual(context.lastCommit, null);
  });
});

describe('fetchPRBasic', () => {
  it('fetches basic PR info correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRBasicResponse)
    };
    
    const pr = await fetchPRBasic(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(pr.number, 42);
    assert.strictEqual(pr.title, 'Test PR');
    assert.deepStrictEqual(pr.labels, ['bug', 'priority:high']);
    assert.strictEqual(pr.hasLabel('bug'), true);
  });

  it('throws enhanced error when PR not found', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => ({
        repository: { pullRequest: null }
      }))
    };
    
    await assert.rejects(
      async () => fetchPRBasic(mockGithub, 'owner', 'repo', 9999),
      { message: /PR #9999 not found in owner\/repo/ }
    );
  });

  it('throws on GraphQL error', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => {
        throw new Error('GraphQL error');
      })
    };
    
    await assert.rejects(
      async () => fetchPRBasic(mockGithub, 'owner', 'repo', 42),
      { message: /GraphQL error/ }
    );
  });
});

describe('serialization', () => {
  it('serializes and deserializes PR context correctly', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const original = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    const serialized = serializeForOutput(original);
    const restored = deserializeFromOutput(serialized);
    
    assert.strictEqual(restored.number, original.number);
    assert.strictEqual(restored.title, original.title);
    assert.deepStrictEqual(restored.labels, original.labels);
    assert.deepStrictEqual(restored.files.paths, original.files.paths);
    
    // Helper methods should work after deserialization
    assert.strictEqual(restored.hasLabel('bug'), true);
    assert.strictEqual(restored.hasAnyLabel(['feature', 'bug']), true);
  });
  
  it('produces valid JSON for GitHub Actions outputs', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const context = await fetchPRContext(mockGithub, 'owner', 'repo', 42);
    const serialized = serializeForOutput(context);
    
    // Should be valid JSON
    assert.doesNotThrow(() => JSON.parse(serialized));
    
    // Should not contain newlines that break outputs
    assert.strictEqual(serialized.includes('\n'), false);
  });
});

describe('createPRContextCache', () => {
  it('caches PR context and returns cached version', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const cache = createPRContextCache();
    
    // First call - should fetch
    const first = await cache.get(mockGithub, 'owner', 'repo', 42);
    assert.strictEqual(mockGithub.graphql.mock.callCount(), 1);
    
    // Second call - should return cached
    const second = await cache.get(mockGithub, 'owner', 'repo', 42);
    assert.strictEqual(mockGithub.graphql.mock.callCount(), 1); // No new call
    
    assert.strictEqual(first, second); // Same object
  });
  
  it('has() returns correct status', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const cache = createPRContextCache();
    
    assert.strictEqual(cache.has('owner', 'repo', 42), false);
    
    await cache.get(mockGithub, 'owner', 'repo', 42);
    
    assert.strictEqual(cache.has('owner', 'repo', 42), true);
    assert.strictEqual(cache.has('owner', 'repo', 99), false);
  });
  
  it('clear() removes all cached entries', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };
    
    const cache = createPRContextCache();
    
    await cache.get(mockGithub, 'owner', 'repo', 42);
    assert.strictEqual(cache.has('owner', 'repo', 42), true);
    
    cache.clear();
    assert.strictEqual(cache.has('owner', 'repo', 42), false);
  });

  it('invalidates cached entries for webhook payloads', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };

    const cache = createPRContextCache();

    await cache.get(mockGithub, 'owner', 'repo', 42);
    assert.strictEqual(cache.has('owner', 'repo', 42), true);

    cache.invalidateForWebhook({
      eventName: 'pull_request',
      payload: { pull_request: { number: 42 } },
      owner: 'owner',
      repo: 'repo'
    });

    assert.strictEqual(cache.has('owner', 'repo', 42), false);
  });

  it('emits cache metrics for hits and misses', async () => {
    const mockGithub = {
      graphql: mock.fn(async () => mockPRContextResponse)
    };

    const cache = createPRContextCache({ core: { info: mock.fn() } });

    await cache.get(mockGithub, 'owner', 'repo', 42);
    await cache.get(mockGithub, 'owner', 'repo', 42);

    const metrics = cache.emitMetrics('pr-context');
    assert.strictEqual(metrics.hits, 1);
    assert.strictEqual(metrics.misses, 1);
  });
});
