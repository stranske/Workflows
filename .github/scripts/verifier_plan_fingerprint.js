'use strict';

const { createHash } = require('crypto');
const { parseScopeTasksAcceptanceSections } = require('./issue_scope_parser.js');
const { resolvePrSourceContext } = require('./source_context.js');

const CLOSING_ISSUES_QUERY = `
  query($owner: String!, $repo: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $prNumber) {
        closingIssuesReferences(first: 20) {
          totalCount
          pageInfo { hasNextPage }
          nodes { number title body repository { nameWithOwner } }
        }
        repository { nameWithOwner }
      }
    }
  }
`;

function planSourceRow(sourceType, repository, number, title, body) {
  if (typeof repository !== 'string' || !/^[^/]+\/[^/]+$/.test(repository)) {
    throw new Error('Verifier plan-source fingerprint received an invalid source repository.');
  }
  const sections = parseScopeTasksAcceptanceSections(body || '');
  return {
    source_type: sourceType,
    repository,
    number,
    title: String(title || ''),
    sections: {
      scope: String(sections.scope || ''),
      tasks: String(sections.tasks || ''),
      acceptance: String(sections.acceptance || ''),
    },
  };
}

async function fetchClosingIssueSources({ github, withRetry, owner, repo, pullNumber }) {
  // github/withRetry are supplied by the workflow's createTokenAwareRetry
  // wrapper so GraphQL and REST reads share the existing credential controls.
  const response = await withRetry((client) =>
    client.graphql(CLOSING_ISSUES_QUERY, { owner, repo, prNumber: pullNumber })
  );
  const connection = response?.repository?.pullRequest?.closingIssuesReferences;
  if (!Array.isArray(connection?.nodes)) {
    throw new Error('Verifier plan-source fingerprint could not read linked issue sources.');
  }
  const rows = connection.nodes.filter(Boolean).map((issue) => {
    if (!Number.isSafeInteger(issue.number) || issue.number <= 0 ||
        typeof issue.repository?.nameWithOwner !== 'string') {
      throw new Error('Verifier plan-source fingerprint received an invalid linked issue.');
    }
    return planSourceRow(
      'github_issue', issue.repository.nameWithOwner, issue.number, issue.title, issue.body,
    );
  });
  const totalCount = Number(connection.totalCount);
  const hasNextPage = connection.pageInfo?.hasNextPage === true;
  if (!Number.isSafeInteger(totalCount) || totalCount < rows.length) {
    throw new Error('Verifier plan-source fingerprint received invalid linked issue coverage.');
  }
  if (hasNextPage || totalCount > rows.length) {
    throw new Error('Verifier plan-source fingerprint cannot prove complete linked-issue coverage.');
  }
  return {
    rows,
    totalCount,
    hasNextPage,
    status: 'included',
    repository: response?.repository?.pullRequest?.repository?.nameWithOwner,
  };
}

async function verifierPlanSourceFingerprint({ github, withRetry, owner, repo, pull }) {
  if (typeof withRetry !== 'function') {
    throw new Error('Verifier plan-source fingerprint requires the token-aware API wrapper.');
  }
  const pullNumber = Number(pull?.number);
  if (
    !Number.isSafeInteger(pullNumber) || pullNumber <= 0 ||
    !(typeof pull?.body === 'string' || pull?.body === null)
  ) {
    throw new Error('Verifier plan-source fingerprint requires a fresh pull request body.');
  }

  // GitHub's REST API represents an absent PR description as null. Normalize
  // that documented value to the empty body while still rejecting omitted or
  // malformed body fields, which can indicate a stale/incomplete API response.
  const pullBody = pull.body === null ? '' : pull.body;
  const sourceContext = resolvePrSourceContext({ ...pull, body: pullBody });
  const repository = `${owner}/${repo}`;
  const pullSource = planSourceRow('pull_request', repository, pullNumber, pull.title, pullBody);
  const discovery = await fetchClosingIssueSources({ github, withRetry, owner, repo, pullNumber });
  if (discovery.repository !== repository) {
    throw new Error('Verifier plan-source fingerprint repository binding changed.');
  }
  const issues = discovery.rows;
  const issueKey = (issue) => `${issue.repository}#${issue.number}`;
  if (
    sourceContext.sourceType === 'github_issue' &&
    Number.isSafeInteger(sourceContext.issueNumber) &&
    sourceContext.issueNumber > 0 &&
    !issues.some((issue) => issue.repository === repository && issue.number === sourceContext.issueNumber)
  ) {
    const { data: issue } = await withRetry((client) => client.rest.issues.get({
      owner,
      repo,
      issue_number: sourceContext.issueNumber,
    }));
    if (
      !issue || issue.number !== sourceContext.issueNumber || issue.pull_request ||
      typeof issue.title !== 'string' || !(typeof issue.body === 'string' || issue.body === null)
    ) {
      throw new Error('Verifier plan-source fingerprint could not validate its linked source issue.');
    }
    issues.push(planSourceRow('github_issue', repository, issue.number, issue.title, issue.body));
  }
  issues.sort((left, right) => issueKey(left).localeCompare(issueKey(right)));

  const payload = {
    schema: 'verifier-plan-source-inputs/v1',
    repository,
    pull_request: pullSource,
    source_context: {
      source_type: sourceContext.sourceType,
      issue_number: sourceContext.issueNumber || null,
      source_ref: sourceContext.sourceRef || '',
      lifecycle: sourceContext.lifecycle || '',
      automation: sourceContext.automation || '',
      requires_issue: sourceContext.requiresIssue === true,
      ambiguous_issue_source: sourceContext.hasAmbiguousIssueSource === true,
    },
    linked_issues: {
      status: discovery.status,
      total_count: discovery.totalCount,
      has_next_page: discovery.hasNextPage,
      sources: issues,
    },
  };
  return createHash('sha256').update(JSON.stringify(payload), 'utf8').digest('hex');
}

module.exports = { verifierPlanSourceFingerprint };
