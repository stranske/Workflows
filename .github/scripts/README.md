# Workflow helper scripts

This directory contains small helper utilities used by the GitHub Actions
workflows in this repository.  Long or stateful snippets that previously lived
inline inside workflow YAML files are extracted here so that they can be shared
between jobs and covered by lightweight unit tests.

## Layout

- JavaScript helpers power `actions/github-script` steps.  They export a single
  async function that accepts the `{ github, context, core }` trio provided by
  the action.  The functions may also read from `process.env` when the workflow
  passes additional parameters via environment variables.
- Python helpers are regular modules with a small command-line interface.  They
  default to reading configuration from environment variables so that workflow
  steps can invoke them with a simple `python .github/scripts/<name>.py`
  command.

## Retry Logic for GitHub API Calls

To handle transient failures (rate limits, timeouts, network issues), use the retry helpers from `api-helpers.js`:

```javascript
const { withBackoff, paginateWithBackoff } = require('./api-helpers');

// For single API calls
const result = await withBackoff(
  () => github.rest.pulls.get({ owner, repo, pull_number: 123 }),
  { core, maxRetries: 3 }
);

// For paginated calls
const items = await paginateWithBackoff(
  github,
  github.rest.issues.listComments,
  { owner, repo, issue_number: 123 },
  { core, maxRetries: 3 }
);
```

These helpers automatically retry transient errors (503, 504, rate limits, timeouts) with exponential backoff and jitter.

## Token-Aware Retry (Load Balanced)

For workflows that hit API rate limits, use the token-aware retry wrapper. It
initializes the token load balancer from environment secrets and switches to a
fresh token on rate limit errors:

```javascript
const { createTokenAwareRetry } = require('./github-api-with-retry');

module.exports = async ({ github, core }) => {
  const { withRetry } = await createTokenAwareRetry({ github, core });

  const response = await withRetry((client) =>
    client.rest.issues.get({ owner, repo, issue_number: 123 })
  );

  core.info(`Fetched issue: ${response.data.title}`);
};
```

Ensure the workflow passes the available tokens as environment variables (for
example: `GITHUB_TOKEN`, `SERVICE_BOT_PAT`, `ACTIONS_BOT_PAT`, `OWNER_PR_PAT`,
`WORKFLOWS_APP_ID`/`WORKFLOWS_APP_PRIVATE_KEY`, `KEEPALIVE_APP_ID`/
`KEEPALIVE_APP_PRIVATE_KEY`, `GH_APP_ID`/`GH_APP_PRIVATE_KEY`). The wrapper
handles selecting and switching between them when rate limits are exhausted.

For consistent configuration across workflows, use the composite action:

```yaml
- name: Export load balancer tokens
  uses: ./.github/actions/export-load-balancer-tokens
  with:
    github_token: ${{ github.token }}
    actions_bot_pat: ${{ secrets.ACTIONS_BOT_PAT }}
    workflows_app_id: ${{ secrets.WORKFLOWS_APP_ID }}
    workflows_app_private_key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}
    token_rotation_json: ${{ secrets.TOKEN_ROTATION_JSON }}
    token_rotation_env_keys: ${{ vars.TOKEN_ROTATION_ENV_KEYS }}
```

To allow custom tokens/apps without editing workflows, set one secret in the
repo/org:

- `TOKEN_ROTATION_JSON`: JSON payload with `pats` and `apps` arrays, each entry
  specifying `id`, `token` (PATs), or `appId`/`privateKey` (apps).
- `TOKEN_ROTATION_ENV_KEYS`: comma-separated list of additional secret names to
  load from the environment.

## Tests

Minimal Node and Python unit tests live alongside the scripts under
`.github/scripts/__tests__` and `tests/github_scripts/`.  The CI pipeline runs
these tests through a dedicated "github scripts" job to ensure that the helper
logic keeps working as workflows evolve.

## Proactive Rate Limit Management

For workflows making many API calls, use `rate-limit-aware-client.js` to proactively monitor and switch tokens before hitting limits:

```javascript
const { createProactiveRateLimitClient, fetchPRDataBatched } = require('./rate-limit-aware-client');
const { Octokit } = require('@octokit/rest');

// Create clients for primary and fallback tokens
const primaryOctokit = new Octokit({ auth: process.env.PRIMARY_TOKEN });
const fallbackOctokit = new Octokit({ auth: process.env.FALLBACK_TOKEN });

// Create proactive client that switches when rate limit < 100
const client = createProactiveRateLimitClient(primaryOctokit, {
  fallbackOctokit,
  threshold: 100,
  core,  // GitHub Actions core for logging
});

// Pre-flight check before batch operations
const safe = await client.preflight(50);  // Need ~50 API calls
if (!safe) {
  core.warning('Insufficient rate limit, consider waiting');
}

// Use withRateLimitTracking for automatic switching on 403/429
const result = await client.withRateLimitTracking(
  (octokit) => octokit.rest.pulls.get({ owner, repo, pull_number: 123 }),
  'fetch PR'
);
```

### GraphQL Batching

Reduce API calls by using GraphQL to fetch multiple fields at once:

```javascript
// Instead of 4+ REST calls (PR, labels, files, reviews)
// Use one GraphQL call:
const prData = await fetchPRDataBatched(octokit, owner, repo, prNumber);
// Returns: { number, title, body, labels, files, reviews, commits }
```
