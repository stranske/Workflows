// Health 83 source-only collector. A filtered Actions query exposes at most
// 1,000 runs, so dense intervals must be subdivided before pagination.
async function collectRunWindow({ start, end, listPage }) {
  const lo = Math.floor(new Date(start).getTime() / 1000) * 1000;
  const hi = Math.ceil(new Date(end).getTime() / 1000) * 1000;
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi < lo) {
    throw new Error('invalid workflow-run reporting window');
  }
  const runs = new Map();
  async function collect(left, right) {
    const created = `${new Date(left).toISOString()}..${new Date(right).toISOString()}`;
    const first = await listPage({ created, per_page: 100, page: 1 });
    const total = first?.data?.total_count;
    if (!Number.isSafeInteger(total) || total < 0 || !Array.isArray(first?.data?.workflow_runs)) {
      throw new Error('incomplete workflow-run response');
    }
    // Split even at exactly 1,000: the server may cap its reported count.
    if (total >= 1000) {
      if (right - left <= 1000) {
        throw new Error(`cannot completely collect dense workflow-run interval ${created}`);
      }
      const middle = Math.floor((left + right) / 2000) * 1000;
      await collect(left, middle);
      await collect(middle, right);
      return;
    }
    const pages = Math.max(1, Math.ceil(total / 100));
    const observed = new Set();
    for (let page = 1; page <= pages; page += 1) {
      const response = page === 1 ? first : await listPage({ created, per_page: 100, page });
      const rows = response?.data?.workflow_runs;
      if (!Array.isArray(rows) || response.data.total_count !== total) {
        throw new Error(`workflow-run window changed or is incomplete: ${created}`);
      }
      for (const run of rows) {
        const at = Date.parse(run.created_at);
        if (!Number.isSafeInteger(run.id) || !Number.isFinite(at) || at < left || at > right) {
          throw new Error('invalid workflow-run identity or interval binding');
        }
        observed.add(run.id);
        if (at >= +new Date(start) && at <= +new Date(end)) runs.set(run.id, run);
      }
    }
    if (observed.size !== total) throw new Error(`incomplete workflow-run pages: ${created}`);
  }
  await collect(lo, hi);
  return [...runs.values()];
}

module.exports = { collectRunWindow };
