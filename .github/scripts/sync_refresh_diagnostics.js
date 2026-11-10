'use strict';

const { createHash } = require('node:crypto');
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const RUN_FIELDS = new Set(['id', 'run_attempt', 'head_sha', 'head_branch', 'path', 'event',
  'display_title', 'status', 'conclusion', 'created_at', 'updated_at', 'run_started_at',
  'html_url', 'source_commit', 'delivery_digest']);

// Diagnostic serialization only: decisions use the complete live state first.
// Native plan bodies remain in their original digest-bound producer artifacts.
function compactCanaryRefresh(value) {
  const histories = {};
  function compact(row) {
    if (Array.isArray(row)) return row.map(compact);
    if (!row || typeof row !== 'object') return row;
    if (row.schema === 'workflows.consumer-sync-plan/v1') {
      return { schema: 'workflows.consumer-sync-plan-reference/v1', plan_id: row.plan_id,
        manifest_sha256: row.manifest_sha256, sha256: digest(row),
        entries: row.entries.length, removals: row.removals.length };
    }
    const result = {};
    for (const [key, item] of Object.entries(row)) {
      if (key === 'runs' && Array.isArray(item) && item.length) {
        const runs = item.map(run => compact(Object.fromEntries(Object.entries(run)
          .filter(([field]) => RUN_FIELDS.has(field) || field.startsWith('refresh_')))));
        const id = digest(runs);
        histories[id] = runs;
        result.runs_ref = { sha256: id, count: runs.length };
      } else result[key] = compact(item);
    }
    return result;
  }
  const result = compact(value);
  return Object.keys(histories).length
    ? { ...result, diagnostics_schema: 'workflows.sync-refresh-diagnostics/v1', histories }
    : result;
}

module.exports = { compactCanaryRefresh };
