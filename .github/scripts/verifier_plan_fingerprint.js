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
          nodes { number title body }
        }
      }
    }
  }
`;

function planSourceRow(sourceType, number, title, body) {
  const sections = parseScopeTasksAcceptanceSections(body || '');
  return {
    source_type: sourceType,
    number,
    title: String(title || ''),
    sections: {
      scope: String(sections.scope || ''),
      tasks: String(sections.tasks || ''),
      acceptance: String(sections.acceptance || ''),
    },
  };
}

async function fetchClosingIssueSources({ github, owner, repo, pullNumber }) {
  const response = await github.graphql(CLOSING_ISSUES_QUERY, { owner, repo, prNumber: pullNumber });
  const connection = response?.repository?.pullRequest?.closingIssuesReferences;
  if (!Array.isArray(connection?.nodes)) {
    throw new Error('Verifier plan-source fingerprint could not read linked issue sources.');
  }
  const rows = connection.nodes.filter(Boolean).map((issue) => {
    if (!Number.isSafeInteger(issue.number) || issue.number <= 0) {
      throw new Error('Verifier plan-source fingerprint received an invalid linked issue.');
    }
    return planSourceRow('github_issue', issue.number, issue.title, issue.body);
  });
  const totalCount = Number(connection.totalCount);
  const hasNextPage = connection.pageInfo?.hasNextPage === true;
  if (!Number.isSafeInteger(totalCount) || totalCount < rows.length) {
    throw new Error('Verifier plan-source fingerprint received invalid linked issue coverage.');
  }
  return {
    rows,
    totalCount,
    hasNextPage,
    status: hasNextPage || totalCount > rows.length ? 'truncated' : 'included',
  };
}

async function verifierPlanSourceFingerprint({ github, owner, repo, pull }) {
  const pullNumber = Number(pull?.number);
  if (!Number.isSafeInteger(pullNumber) || pullNumber <= 0 || typeof pull?.body !== 'string') {
    throw new Error('Verifier plan-source fingerprint requires a fresh pull request body.');
  }

  const sourceContext = resolvePrSourceContext(pull);
  const pullSource = planSourceRow('pull_request', pullNumber, pull.title, pull.body);
  const discovery = await fetchClosingIssueSources({ github, owner, repo, pullNumber });
  const issues = discovery.rows;
  if (
    sourceContext.sourceType === 'github_issue' &&
    Number.isSafeInteger(sourceContext.issueNumber) &&
    sourceContext.issueNumber > 0 &&
    !issues.some((issue) => issue.number === sourceContext.issueNumber)
  ) {
    const { data: issue } = await github.rest.issues.get({
      owner,
      repo,
      issue_number: sourceContext.issueNumber,
    });
    if (
      !issue || issue.number !== sourceContext.issueNumber || issue.pull_request ||
      typeof issue.title !== 'string' || !(typeof issue.body === 'string' || issue.body === null)
    ) {
      throw new Error('Verifier plan-source fingerprint could not validate its linked source issue.');
    }
    issues.push(planSourceRow('github_issue', issue.number, issue.title, issue.body));
  }
  issues.sort((left, right) => left.number - right.number);

  const payload = {
    schema: 'verifier-plan-source-inputs/v1',
    repository: `${owner}/${repo}`,
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
