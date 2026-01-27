# GitHub API Call Pattern Guide

> **Purpose**: Ensure all GitHub API calls use token-aware retry to handle rate limits gracefully and distribute load across available tokens.

## Quick Reference

```javascript
// ❌ WRONG - Unprotected API call
const { data } = await github.rest.issues.get({ owner, repo, issue_number });

// ✅ CORRECT - Token-aware retry pattern
const { createTokenAwareRetry } = require('./github-api-with-retry.js');
const { withRetry } = await createTokenAwareRetry({ github, core });
const { data } = await withRetry((client) => client.rest.issues.get({ owner, repo, issue_number }));
```

## Why This Matters

Our automation fleet makes thousands of API calls per hour. Without token rotation:
- A single exhausted token causes workflow failures
- All 25,000 requests/hour capacity goes unused (5,000 per token × 5 tokens)
- Rate limit errors cascade into PR delays

With token-aware retry:
- Automatic switch to fresh token when rate limited
- Exponential backoff prevents hammering the API
- Transparent to calling code - just wrap and forget

## Full Setup Pattern

### For Scripts (`.github/scripts/*.js`)

```javascript
'use strict';

const { createTokenAwareRetry } = require('./github-api-with-retry.js');

async function myFunction({ github, core, context }) {
  // Initialize token-aware retry at the START of your function
  const { withRetry, paginateWithRetry } = await createTokenAwareRetry({
    github,
    core,
    env: process.env,
  });

  // All API calls now use withRetry
  const { data: issue } = await withRetry((client) =>
    client.rest.issues.get({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: 123,
    })
  );

  // For paginated calls, use paginateWithRetry
  const allComments = await paginateWithRetry(
    github.rest.issues.listComments,
    { owner: context.repo.owner, repo: context.repo.repo, issue_number: 123 }
  );

  // The `client` in the callback is the current Octokit instance
  // If a rate limit is hit, it automatically switches to a fresh token
  const { data: pr } = await withRetry((client) =>
    client.rest.pulls.get({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: 456,
    })
  );

  return { issue, pr, comments: allComments };
}

module.exports = { myFunction };
```

### For Workflow Inline Scripts

When you have inline JavaScript in YAML workflows:

```yaml
- name: Do API work
  uses: actions/github-script@v7
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    script: |
      const { createTokenAwareRetry } = require('./.github/scripts/github-api-with-retry.js');
      const { withRetry } = await createTokenAwareRetry({ github, core });
      
      const { data } = await withRetry((client) =>
        client.rest.issues.get({
          owner: context.repo.owner,
          repo: context.repo.repo,
          issue_number: ${{ github.event.issue.number }},
        })
      );
      console.log(data.title);
```

## API Reference

### `createTokenAwareRetry(options)`

Initializes the token registry and returns wrapped API helpers.

**Options:**
- `github` (required): Octokit instance from `actions/github-script`
- `core` (optional): GitHub Actions core for logging
- `env` (optional): Environment variables (defaults to `process.env`)
- `capabilities` (optional): Required token capabilities (e.g., `['issues:write']`)
- `preferredType` (optional): `'APP'` or `'PAT'`
- `task` (optional): Task name for specialization matching
- `minRemaining` (optional): Minimum remaining calls needed (default: 100)

**Returns:** `{ github, withRetry, paginateWithRetry, tokenRegistry, getTokenSource }`

### `withRetry(fn, overrideOptions)`

Wraps an API call with retry logic and token switching.

**Parameters:**
- `fn(client)`: Function receiving the current Octokit client
- `overrideOptions`: Override default retry behavior

**Example:**
```javascript
const { data } = await withRetry((client) =>
  client.rest.repos.get({ owner, repo })
);
```

### `paginateWithRetry(method, params, overrideOptions)`

Wraps a paginated API call.

**Example:**
```javascript
const allWorkflows = await paginateWithRetry(
  github.rest.actions.listRepoWorkflows,
  { owner, repo }
);
```

## Migration Checklist

When converting a script to use token-aware retry:

1. **Add import** at the top of the file:
   ```javascript
   const { createTokenAwareRetry } = require('./github-api-with-retry.js');
   ```

2. **Initialize at entry point** (usually the main exported function):
   ```javascript
   const { withRetry, paginateWithRetry } = await createTokenAwareRetry({
     github,
     core,
     env: process.env,
   });
   ```

3. **Wrap each API call**:
   - `github.rest.*` → `withRetry((client) => client.rest.*)`
   - `github.graphql(...)` → `withRetry((client) => client.graphql(...))`
   - `github.paginate(...)` → `paginateWithRetry(...)`

4. **Test locally** to ensure the wrapped calls work correctly.

5. **Run the guard script** to verify all calls are protected:
   ```bash
   node .github/scripts/__checks__/api-call-guard.js
   ```

## Common Patterns

### Conditional logic with API results

```javascript
const { withRetry } = await createTokenAwareRetry({ github, core });

// The result is the same as before - just wrapped
const { data: pr } = await withRetry((client) =>
  client.rest.pulls.get({ owner, repo, pull_number })
);

if (pr.mergeable_state === 'clean') {
  await withRetry((client) =>
    client.rest.pulls.merge({ owner, repo, pull_number })
  );
}
```

### Error handling

```javascript
try {
  const { data } = await withRetry((client) =>
    client.rest.issues.get({ owner, repo, issue_number })
  );
} catch (error) {
  if (error.status === 404) {
    console.log('Issue not found');
  } else {
    // Rate limit errors are handled internally - this is a real error
    throw error;
  }
}
```

### Multiple parallel calls

```javascript
// These calls can run in parallel
const [issueResult, prResult] = await Promise.all([
  withRetry((client) => client.rest.issues.get({ owner, repo, issue_number })),
  withRetry((client) => client.rest.pulls.get({ owner, repo, pull_number })),
]);
```

## CI Enforcement

The `api-call-guard.js` script runs in CI to catch unprotected API calls:

```bash
node .github/scripts/__checks__/api-call-guard.js
```

This will fail if any script has `github.rest.*` calls that aren't wrapped with `withRetry`.

## Exempt Files

The following files are exempt from the API call guard:
- `github-api-with-retry.js` - The retry wrapper itself
- `rate-limit-aware-client.js` - Low-level rate limit client
- `token_load_balancer.js` - Token management
- Files in `__tests__/` - Test files
- Files in `__checks__/` - CI guard scripts
