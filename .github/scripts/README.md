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

## Tests

Minimal Node and Python unit tests live alongside the scripts under
`.github/scripts/__tests__` and `tests/github_scripts/`.  The CI pipeline runs
these tests through a dedicated "github scripts" job to ensure that the helper
logic keeps working as workflows evolve.
