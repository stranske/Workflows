'use strict';

const DEFAULT_PER_PAGE = 100;
const MAX_COMMENT_PAGES = 10;

/**
 * List PR/issue comments with a hard pagination upper bound.
 *
 * Callers should pass a `listFn` obtained via createTokenAwareRetry
 * (from github-api-with-retry.js) so that every page request gets
 * automatic token rotation and rate-limit back-off.
 *
 * @param {object} options
 * @param {string} options.owner - Repository owner.
 * @param {string} options.repo  - Repository name.
 * @param {number} options.issueNumber - PR or issue number.
 * @param {function} options.listFn - Paginated list function (required).
 * @param {number} [options.perPage=100]  - Items per page.
 * @param {number} [options.maxPages=10]  - Hard upper bound on pages fetched.
 * @returns {Promise<object[]>} Collected comments.
 */
async function listCommentsWithLimit(options = {}) {
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
  const listFn = options.listFn;

  if (!listFn) {
    throw new Error('listFn is required (use createTokenAwareRetry to wrap the API client)');
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
