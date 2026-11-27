const { createHash } = require('node:crypto');
const { createTokenAwareRetry } = require('./github-api-with-retry.js');

const BRANCH = 'maintenance/maint72-pr-body';
const BASE = 'main';
const TITLE = 'chore: clean up tracked PR body';
const MARKER = '<!-- workflows-maint72-pr-body/v1 -->';
const SOURCE_MARKER = '<!-- workflow-source:automation_run -->';
const SOURCE_LABEL = 'workflow:source-automation';

function cleanupPullBody(baseSha) {
  return `${MARKER}\n${SOURCE_MARKER}\n\nThis PR applies the Maint 72 cleanup plan from \`${baseSha}\`. ` +
    'It removes tracked PR-body content and adds the ignore rule when missing. ' +
    'Review the exact diff and required checks before merging.';
}

function treeEntries(entries) {
  return JSON.stringify(entries.map(({ path, mode, type, sha }) => [path, mode, type, sha]).sort());
}

async function openCleanupPullRequest({ github, core, owner, repo, baseSha, prBodySha,
  gitignoreSha, newIgnore }) {
  // Keep protected receipt reads and write reconciliation on this installation.
  const { withRetry, paginateWithRetry } = await createTokenAwareRetry({
    github, core, env: {}, tokenRegistry: { isInitialized: () => false },
    task: 'maint72-protected-apply',
  });
  const writeOnce = (fn) => withRetry(fn, { maxRetries: 0 });
  const target = { owner, repo };
  const headRef = `heads/${BRANCH}`;
  const getCommit = async (sha) => (await withRetry((client) => client.rest.git.getCommit({
    ...target, commit_sha: sha,
  }))).data;
  const getTree = async (sha) => {
    const { data } = await withRetry((client) => client.rest.git.getTree({ ...target, tree_sha: sha }));
    if (data.truncated) throw new Error('cannot verify a truncated cleanup tree');
    return data.tree;
  };
  const getHead = async () => {
    try {
      const { data } = await withRetry((client) => client.rest.git.getRef({ ...target, ref: headRef }));
      if (data.ref !== `refs/${headRef}` || !data.object.sha) {
        throw new Error('unexpected cleanup branch reference');
      }
      return data.object.sha;
    } catch (error) {
      if (error.status === 404) return null;
      throw error;
    }
  };
  const getPull = async (sha) => {
    const matches = (await paginateWithRetry(github.rest.pulls.list, {
      ...target, state: 'all', head: `${owner}:${BRANCH}`, per_page: 100,
    })).filter((pull) => pull.state === 'open' || pull.head.sha === sha);
    if (matches.length > 1) throw new Error('multiple cleanup PRs found; reconcile their branches');
    return matches[0];
  };

  const assertBase = async () => {
    const { data } = await withRetry((client) => client.rest.repos.getBranch({ ...target, branch: BASE }));
    if (data.commit.sha !== baseSha || data.protected !== true) {
      throw new Error('default head or protection changed; preview the current default again');
    }
  };
  const baseCommit = await getCommit(baseSha);
  const baseEntries = await getTree(baseCommit.tree.sha);
  const byPath = new Map(baseEntries.map((entry) => [entry.path, entry]));
  const observe = (path, sha) => {
    const entry = byPath.get(path);
    if (!sha && !entry) return undefined;
    if (!entry || entry.sha !== sha || entry.type !== 'blob' ||
        !['100644', '100755'].includes(entry.mode)) {
      throw new Error(`planned ${path} does not match the pinned regular-file snapshot`);
    }
    return entry;
  };
  const prBody = observe('pr_body.md', prBodySha);
  const ignore = observe('.gitignore', gitignoreSha);
  const changes = [];
  if (prBody) {
    changes.push({ path: prBody.path, mode: prBody.mode, type: 'blob', sha: null });
    byPath.delete(prBody.path);
  }
  if (newIgnore !== null) {
    const mode = ignore?.mode ?? '100644';
    changes.push({ path: '.gitignore', mode, type: 'blob', content: newIgnore });
    const content = Buffer.from(newIgnore);
    const sha = createHash('sha1').update(`blob ${content.length}\0`).update(content).digest('hex');
    byPath.set('.gitignore', { path: '.gitignore', mode, type: 'blob', sha });
  }

  const expected = treeEntries([...byPath.values()]);
  const message = `${TITLE}\n\n${MARKER}\nBase: ${baseSha}`;
  const mismatched = () => new Error('cleanup branch has another head; reconcile its existing PR or branch');
  const verifyHead = async (sha) => {
    if (!sha) throw mismatched();
    const commit = await getCommit(sha);
    if (commit.message !== message || commit.parents.length !== 1 ||
        commit.parents[0].sha !== baseSha || treeEntries(await getTree(commit.tree.sha)) !== expected) {
      throw mismatched();
    }
  };
  const verifyOwnedPull = (pull, sha) => {
    if (pull?.state !== 'open' || pull.draft !== false ||
        pull.base.ref !== BASE || pull.head.repo?.full_name !== `${owner}/${repo}` ||
        pull.head.ref !== BRANCH || pull.head.sha !== sha || !pull.body?.includes(MARKER)) {
      throw new Error('cleanup PR is closed or differs from this plan; reconcile it in normal review');
    }
    return pull;
  };
  const hasSourceLabel = (pull) => (pull.labels || []).some((label) =>
    String(label?.name || label).toLowerCase() === SOURCE_LABEL,
  );
  const repairProvenance = async (pull, sha) => {
    verifyOwnedPull(pull, sha);
    if (!pull.body.includes(SOURCE_MARKER)) {
      const body = pull.body.replace(MARKER, `${MARKER}\n${SOURCE_MARKER}`);
      await writeOnce((client) => client.rest.pulls.update({
        ...target, pull_number: pull.number, body,
      }));
    }
    if (!hasSourceLabel(pull)) {
      await writeOnce((client) => client.rest.issues.addLabels({
        ...target, issue_number: pull.number, labels: [SOURCE_LABEL],
      }));
    }
    const refreshed = await getPull(sha);
    verifyOwnedPull(refreshed, sha);
    if (!refreshed.body.includes(SOURCE_MARKER) || !hasSourceLabel(refreshed)) {
      throw new Error('cleanup PR provenance did not persist; reconcile it in normal review');
    }
    return refreshed.html_url;
  };

  let head = await getHead();
  const priorPull = await getPull(head);
  if (priorPull) {
    await verifyHead(head);
    return repairProvenance(priorPull, head);
  }
  await assertBase();
  if (head) {
    await verifyHead(head);
  } else {
    const { data: tree } = await writeOnce((client) => client.rest.git.createTree({
      ...target, base_tree: baseCommit.tree.sha, tree: changes,
    }));
    if (treeEntries(await getTree(tree.sha)) !== expected) {
      throw new Error('created cleanup tree differs from the pinned plan; no ref was published');
    }
    const { data: commit } = await writeOnce((client) => client.rest.git.createCommit({
      ...target, message, tree: tree.sha, parents: [baseSha],
    }));
    await assertBase();
    try {
      await writeOnce((client) => client.rest.git.createRef({
        ...target, ref: `refs/${headRef}`, sha: commit.sha,
      }));
    } catch (error) {
      // A competing exact run or a lost response may already have published the ref.
      if (!(await getHead())) throw error;
    }
    head = await getHead();
    await verifyHead(head);
  }

  await assertBase();
  if (await getHead() !== head) throw mismatched();
  const existing = await getPull(head);
  if (existing) return repairProvenance(existing, head);
  let pull;
  try {
    ({ data: pull } = await writeOnce((client) => client.rest.pulls.create({
      ...target, title: TITLE, head: BRANCH, base: BASE, draft: false,
      body: cleanupPullBody(baseSha),
    })));
  } catch (error) {
    // Reconcile an ambiguous create response by the bound head, never by making another PR.
    pull = await getPull(head);
    if (!pull) throw error;
  }
  if (await getHead() !== head) throw mismatched();
  return repairProvenance(pull, head);
}

module.exports = { openCleanupPullRequest, cleanupPullBody };
