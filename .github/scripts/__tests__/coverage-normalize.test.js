'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  parseCoverageXml,
  parseCoverageJson,
  computeCoverageStats,
} = require('../coverage-normalize');

test('parses coverage xml and json payloads', () => {
  assert.equal(parseCoverageXml('<coverage line-rate="0.9"/>'), 90);
  assert.ok(Math.abs(parseCoverageXml('<coverage line-rate="0.55"/>') - 55) < 1e-9);
  assert.equal(parseCoverageJson({ totals: { percent_covered: 75.5 } }), 75.5);
  assert.equal(parseCoverageJson({ totals: { percent_covered_display: '88.2' } }), 88.2);
  assert.equal(parseCoverageJson({ totals: { covered_lines: 50, num_lines: 100 } }), 50);
  assert.equal(parseCoverageJson({ totals: {} }), null);
});

test('computes coverage stats and writes files', async () => {
  const cwd = process.cwd();
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-test-'));
  process.chdir(tempDir);
  try {
    const summaryDir = path.join(tempDir, 'summary_artifacts', 'coverage-runtimes', 'coverage-3.11');
    fs.mkdirSync(summaryDir, { recursive: true });
    fs.writeFileSync(path.join(summaryDir, 'coverage.json'), JSON.stringify({ totals: { percent_covered: 91.234 } }));

    const secondDir = path.join(tempDir, 'summary_artifacts', 'coverage-runtimes', 'runtimes', '3.12');
    fs.mkdirSync(secondDir, { recursive: true });
    fs.writeFileSync(path.join(secondDir, 'coverage.xml'), '<coverage line-rate="0.845"/>');

    const historyPath = path.join(tempDir, 'summary_artifacts', 'coverage-trend-history.ndjson');
    fs.mkdirSync(path.dirname(historyPath), { recursive: true });
    fs.writeFileSync(historyPath, JSON.stringify({ run_id: 1, run_number: 1, avg_coverage: 88, worst_job_coverage: 70 }) + '\n');
    fs.appendFileSync(historyPath, JSON.stringify({ run_id: 2, run_number: 2, avg_coverage: 89, worst_job_coverage: 71 }) + '\n');

    const deltaPath = path.join(tempDir, 'summary_artifacts', 'coverage-delta.json');
    fs.writeFileSync(deltaPath, JSON.stringify({ delta: 1 }));

    const result = await computeCoverageStats({ core: null });
    assert.ok(result.stats.avg_latest >= 0);
    assert.equal(result.stats.job_coverages.length, 2);
    assert.ok(fs.existsSync(path.join(tempDir, 'coverage-stats.json')));
    assert.ok(fs.existsSync(path.join(tempDir, 'coverage-delta-output.json')));
  } finally {
    process.chdir(cwd);
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});
