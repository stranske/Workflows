'use strict';

const DEFAULT_PER_PAGE = 100;
const MAX_COMMENT_PAGES = 10;

async function listCommentsWithLimit(options = {}) {
  const github = options.github;
  const owner = options.owner;
  const repo = options.repo;
  const issueNumber = options.issueNumber;
  const perPage =
    typeof options.perPage === 'number' && Number.isFinite(options.perPage)
      ? options.perPage
      : DEFAULT_PER_PAGE;
  const maxPages =
    typeof options.maxPages === 'number' && Number.isFinite(options.maxPages)
      ? options.maxPages
      : MAX_COMMENT_PAGES;
  const listFn =
    options.listFn ||
    (github?.rest?.issues?.listComments
      ? (params) => github.rest.issues.listComments(params)
      : null);

  if (!listFn) {
    throw new Error('github client missing rest.issues.listComments');
  }
  if (!owner || !repo) {
    throw new Error('owner and repo are required');
  }
  if (!issueNumber) {
    throw new Error('issueNumber is required');
  }

  const comments = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const response = await listFn({
      owner,
      repo,
      issue_number: issueNumber,
      per_page: perPage,
      page,
    });
    const pageData = Array.isArray(response?.data) ? response.data : response || [];
    comments.push(...pageData);
    if (pageData.length < perPage) {
      break;
    }
  }

  return comments;
}

module.exports = {
  DEFAULT_PER_PAGE,
  MAX_COMMENT_PAGES,
  listCommentsWithLimit,
};
