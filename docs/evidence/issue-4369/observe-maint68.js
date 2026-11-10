'use strict';

// Read-only collection and replay of bounded REST /actions/runs pages. These are leads;
// workflow_dispatch, actor names and run titles never authenticate the caller.
const fs = require('node:fs');
const childProcess = require('node:child_process');
const MAINT68 = '.github/workflows/maint-68-sync-consumer-repos.yml';
const MAINT71 = '.github/workflows/maint-71-merge-sync-prs.yml';

// Date.parse accepts local times and silently rolls invalid calendar dates
// forward. Neither can establish an explicit UTC observation boundary. Limit
// precision to what JavaScript can compare without losing interval gaps.
function utcTimestamp(value) {
  const match = typeof value === 'string'
    && /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?(?:Z|\+00:00)$/.exec(value);
  const parsed = match ? Date.parse(value) : NaN;
  if (!Number.isFinite(parsed)
    || new Date(parsed).toISOString() !== `${match[1]}.${(match[2] || '').padEnd(3, '0')}Z`) {
    throw new Error('invalid UTC observation timestamp');
  }
  return parsed;
}

function inventoryTotal(body) {
  const total = body?.total_count;
  if (!Number.isSafeInteger(total) || total < 0 || total >= 1000) {
    throw new Error('inventory count is invalid or reaches the REST search limit');
  }
  return total;
}

function readInventoryPage(url) {
  return JSON.parse(childProcess.execFileSync('gh', ['api', '--method', 'GET', url], {
    encoding: 'utf8', timeout: 30000, killSignal: 'SIGKILL', maxBuffer: 16 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  }));
}

// Collect only GET run pages. Validate the query before invoking transport and
// cap pagination below the REST search limit. Never emit a partial inventory.
function collect({ start, end, workflow_id, workflow_path }, request = readInventoryPage) {
  const inventory = { start, end,
    ...(workflow_id === undefined ? {} : { workflow_id }),
    ...(workflow_path === undefined ? {} : { workflow_path }), pages: [] };
  const endpoint = workflow_id === undefined
    ? 'https://api.github.com/repos/stranske/Workflows/actions/runs'
    : `https://api.github.com/repos/stranske/Workflows/actions/workflows/${workflow_id}/runs`;
  // Preserve explicit +00:00 UTC offsets; an unescaped plus becomes a space
  // when the query is decoded, invalidating the requested observation bounds.
  const created = encodeURIComponent(`${start}..${end}`);
  const urlFor = page => `${endpoint}?per_page=100&page=${page}&created=${created}`;
  observe({ ...inventory,
    pages: [{ url: urlFor(1), body: { total_count: 0, workflow_runs: [] } }] });
  let total, last = 1;
  for (let page = 1; page <= last; page++) {
    const url = urlFor(page), body = request(url), count = inventoryTotal(body);
    if (page === 1) {
      total = count;
      last = Math.floor(total / 100) + 1;
    }
    if (count !== total || !Array.isArray(body.workflow_runs)
      || body.workflow_runs.length !== Math.min(100, Math.max(0, total - (page - 1) * 100))) {
      throw new Error('incomplete or changing inventory');
    }
    inventory.pages.push({ url, body });
  }
  return { inventory, observation: observe(inventory) };
}

function observe({ start, end, pages, workflow_id, workflow_path = MAINT68 }) {
  if (workflow_path !== MAINT68 && workflow_path !== MAINT71) {
    throw new Error('unsupported observation workflow path');
  }
  const role = workflow_path === MAINT68 ? 'producer' : 'merger';
  const lower = utcTimestamp(start), upper = utcTimestamp(end);
  if (lower > upper) {
    throw new Error('invalid observation bounds');
  }
  if (!Array.isArray(pages) || !pages.length) throw new Error('missing inventory pages');
  if (workflow_id !== undefined
    && (!Number.isSafeInteger(workflow_id) || workflow_id <= 0)) {
    throw new Error(`invalid ${role} workflow identity`);
  }
  // A workflow-specific inventory avoids the repository-wide search cap. Bind
  // every page and row to the same explicit workflow identity; filters that
  // could hide a producer or merger event remain forbidden.
  const endpoint = workflow_id === undefined
    ? '/repos/stranske/Workflows/actions/runs'
    : `/repos/stranske/Workflows/actions/workflows/${workflow_id}/runs`;
  const total = inventoryTotal(pages[0].body);
  const runs = [], ids = new Set();
  for (const [index, page] of pages.entries()) {
    const url = new URL(page.url);
    if (url.origin !== 'https://api.github.com'
      || url.pathname !== endpoint
      || url.searchParams.size !== 3
      || url.searchParams.get('created') !== `${start}..${end}`
      || url.searchParams.get('per_page') !== '100'
      || url.searchParams.get('page') !== String(index + 1)) {
      throw new Error('inventory endpoint or page binding changed');
    }
    const rows = page.body.workflow_runs;
    if (page.body.total_count !== total || !Array.isArray(rows)
      || rows.length !== Math.min(100, Math.max(0, total - index * 100))) {
      throw new Error('incomplete or changing inventory');
    }
    for (const run of rows) {
      const created = utcTimestamp(run.created_at);
      if (!Number.isSafeInteger(run.id) || run.id <= 0 || ids.has(run.id)
        || !Number.isFinite(created) || created < lower || created > upper
        || typeof run.path !== 'string' || typeof run.event !== 'string') {
        throw new Error('invalid, duplicate or out-of-bounds run');
      }
      if (workflow_id !== undefined
        && (run.workflow_id !== workflow_id || run.path !== workflow_path)) {
        throw new Error(`${role} workflow identity changed`);
      }
      ids.add(run.id);
      runs.push(run);
    }
  }
  // Require an explicit empty terminal page even when the total is a multiple
  // of the page size, including an empty inventory.
  if (runs.length !== total || pages.length !== Math.floor(total / 100) + 1) {
    throw new Error('inventory pagination is incomplete');
  }
  const selected = runs.filter(run => run.path === workflow_path)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || a.id - b.id);
  return { start, end, total_count: total, pagination_complete: true,
    workflow_path,
    inventory_scope: workflow_id === undefined ? 'repository' : role,
    ...(workflow_id === undefined ? {} : { workflow_id }),
    [`${role}s`]: selected.map(run => ({ id: run.id, created_at: run.created_at,
      event: run.event, automation_origin: run.event === 'schedule' ? 'schedule' : 'UNKNOWN' })),
    chain_acceptance: false };
}

// Inclusive REST intervals share their boundary. A sequence proves continuous
// observation only when every window is complete and boundary rows agree.
function observeSequence(inventories) {
  if (!Array.isArray(inventories) || !inventories.length) {
    throw new Error('missing observation inventories');
  }
  const observations = inventories.map(observe);
  const first = observations[0], seen = new Map();
  const role = first.workflow_path === MAINT68 ? 'producers' : 'mergers';
  const selected = [];
  const identity = run => JSON.stringify([run.id, run.created_at, run.path, run.event, run.workflow_id]);
  let previousRows = [];
  for (const [index, observation] of observations.entries()) {
    if (observation.workflow_path !== first.workflow_path
      || observation.inventory_scope !== first.inventory_scope
      || observation.workflow_id !== first.workflow_id) {
      throw new Error('observation workflow or inventory scope changed');
    }
    if (index && Date.parse(observation.start) !== Date.parse(observations[index - 1].end)) {
      throw new Error('observation windows have a gap, overlap or reversed order');
    }
    const rows = inventories[index].pages.flatMap(page => page.body.workflow_runs);
    const boundary = candidates => JSON.stringify(candidates
      .filter(run => Date.parse(run.created_at) === Date.parse(observation.start))
      .map(identity).sort());
    if (index && boundary(previousRows) !== boundary(rows)) {
      throw new Error('observation boundary inventory changed');
    }
    const leads = new Map(observation[role].map(run => [run.id, run]));
    for (const run of rows) {
      if (seen.has(run.id)) {
        if (seen.get(run.id) !== identity(run)
          || Date.parse(run.created_at) !== Date.parse(observation.start)) {
          throw new Error('conflicting observation boundary run');
        }
      } else {
        seen.set(run.id, identity(run));
        if (leads.has(run.id)) selected.push(leads.get(run.id));
      }
    }
    previousRows = rows;
  }
  return { ...first, end: observations.at(-1).end, total_count: seen.size,
    observation_count: observations.length, continuous: true,
    [role]: selected.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || a.id - b.id) };
}

if (require.main === module) {
  try {
    const collecting = process.argv[2] === '--collect';
    const input = JSON.parse(fs.readFileSync(process.argv[collecting ? 3 : 2], 'utf8'));
    const result = collecting ? collect(input)
      : Array.isArray(input) ? observeSequence(input) : observe(input);
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`Observation refused: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { collect, observe, observeSequence };
