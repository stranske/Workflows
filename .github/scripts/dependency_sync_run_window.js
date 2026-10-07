// Health 83 source-only collector. A filtered Actions query exposes at most
// 1,000 runs, so dense intervals must be subdivided before pagination.
// Capped counts: https://github.blog/changelog/2026-09-25-changes-to-query-results-in-the-github-actions-api-and-ui/
async function collectRunWindow({ start, end, listPage }) {
  const lo = Math.floor(new Date(start).getTime() / 1000) * 1000;
  const hi = Math.ceil(new Date(end).getTime() / 1000) * 1000;
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi < lo) {
    throw new Error('invalid workflow-run reporting window');
  }
  function validate(run, left, right) {
    const at = Date.parse(run.created_at);
    if (!Number.isSafeInteger(run.id) || !Number.isFinite(at) || at < left || at > right) {
      throw new Error('invalid workflow-run identity or interval binding');
    }
  }
  async function collect(left, right) {
    const created = `${new Date(left).toISOString()}..${new Date(right).toISOString()}`;
    const first = await listPage({ created, per_page: 100, page: 1 });
    const total = first?.data?.total_count;
    // GitHub's September 2026 capped total is a lower bound, not an exact
    // cardinality. Recognized capped representations authorize subdivision.
    const cappedPlus = total === '2,500+' || total === '2500+';
    // Authenticated API recovery showed integer 2500 also represents a cap.
    // Its exact-vs-capped ambiguity is settled by complete child collection,
    // not by treating the parent as an exact cardinality.
    const capped = cappedPlus || total === 2500;
    if ((!capped && (!Number.isSafeInteger(total) || total < 0)) || !Array.isArray(first?.data?.workflow_runs)) {
      throw new Error('incomplete workflow-run response');
    }
    // Split even at exactly 1,000: the server may cap its reported count.
    if (capped || total >= 1000) {
      if (right - left <= 1000) {
        throw new Error(`cannot completely collect dense workflow-run interval ${created}`);
      }
      const middle = Math.floor((left + right) / 2000) * 1000;
      const rows = await collect(left, middle);
      for (const [id, run] of await collect(middle, right)) {
        if (rows.has(id) && rows.get(id).created_at !== run.created_at) {
          throw new Error('workflow-run window changed during subdivision');
        }
        rows.set(id, run);
      }
      for (const run of first.data.workflow_runs) validate(run, left, right);
      const countMatches = cappedPlus ? rows.size > 2500
        : total === 2500 ? rows.size >= 2500 : rows.size === total;
      if (!countMatches || first.data.workflow_runs.some((run) => rows.get(run.id)?.created_at !== run.created_at)) {
        throw new Error(`subdivision is incomplete or window changed: ${created}; parent=${total}, children=${rows.size}`);
      }
      return rows;
    }
    const pages = Math.max(1, Math.ceil(total / 100));
    const observed = new Map();
    for (let page = 1; page <= pages; page += 1) {
      const response = page === 1 ? first : await listPage({ created, per_page: 100, page });
      const rows = response?.data?.workflow_runs;
      if (!Array.isArray(rows) || response.data.total_count !== total) {
        throw new Error(`workflow-run window changed or is incomplete: ${created}`);
      }
      for (const run of rows) {
        validate(run, left, right);
        observed.set(run.id, run);
      }
    }
    if (observed.size !== total) throw new Error(`incomplete workflow-run pages: ${created}`);
    return observed;
  }
  const runs = await collect(lo, hi);
  return [...runs.values()].filter((run) => Date.parse(run.created_at) >= +new Date(start) && Date.parse(run.created_at) <= +new Date(end));
}

module.exports = { collectRunWindow };
