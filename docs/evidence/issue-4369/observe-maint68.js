'use strict';

// Read-only replay of bounded REST /actions/runs pages. This collects leads;
// workflow_dispatch, actor names and run titles never authenticate the caller.
const fs = require('node:fs');

function observe({ start, end, pages }) {
  const lower = Date.parse(start), upper = Date.parse(end);
  if (!Number.isFinite(lower) || !Number.isFinite(upper) || lower > upper) {
    throw new Error('invalid observation bounds');
  }
  if (!Array.isArray(pages) || !pages.length) throw new Error('missing inventory pages');
  const total = pages[0].body.total_count;
  if (!Number.isSafeInteger(total) || total < 0 || total >= 1000) {
    throw new Error('inventory count is invalid or reaches the REST search limit');
  }
  const runs = [], ids = new Set();
  for (const [index, page] of pages.entries()) {
    const url = new URL(page.url);
    if (url.origin !== 'https://api.github.com'
      || url.pathname !== '/repos/stranske/Workflows/actions/runs'
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
      const created = Date.parse(run.created_at);
      if (!Number.isSafeInteger(run.id) || run.id <= 0 || ids.has(run.id)
        || !Number.isFinite(created) || created < lower || created > upper
        || typeof run.path !== 'string' || typeof run.event !== 'string') {
        throw new Error('invalid, duplicate or out-of-bounds run');
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
  const producers = runs.filter(run => run.path === '.github/workflows/maint-68-sync-consumer-repos.yml')
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || a.id - b.id);
  return { start, end, total_count: total, pagination_complete: true,
    producers: producers.map(run => ({ id: run.id, created_at: run.created_at,
      event: run.event, automation_origin: run.event === 'schedule' ? 'schedule' : 'UNKNOWN' })),
    chain_acceptance: false };
}

if (require.main === module) {
  try {
    const result = observe(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`Observation refused: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { observe };
