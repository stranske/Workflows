'use strict';

const fs = require('fs');
const path = require('path');

function readFile(pathname) {
  return fs.readFileSync(pathname, 'utf8');
}

function safeParseJSON(text) {
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

function parseCoverageXml(xmlText) {
  if (typeof xmlText !== 'string') {
    return null;
  }
  const match = xmlText.match(/line-rate="([0-9]*\.?[0-9]+)"/i);
  if (!match) {
    return null;
  }
  const rate = Number.parseFloat(match[1]);
  return Number.isFinite(rate) ? rate * 100 : null;
}

function parseCoverageJson(jsonData) {
  if (!jsonData || typeof jsonData !== 'object') {
    return null;
  }
  const totals = jsonData.totals;
  if (!totals || typeof totals !== 'object') {
    return null;
  }
  if (typeof totals.percent_covered === 'number') {
    return totals.percent_covered;
  }
  if (typeof totals.percent_covered_display === 'string') {
    const parsed = Number.parseFloat(totals.percent_covered_display);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  const coveredCandidates = [totals.covered_lines, totals.covered_statements, totals.covered];
  const totalCandidates = [totals.num_statements, totals.num_lines, totals.statements];
  const covered = coveredCandidates.find(value => typeof value === 'number');
  const total = totalCandidates.find(value => typeof value === 'number');
  if (typeof covered === 'number' && typeof total === 'number' && total !== 0) {
    return (covered / total) * 100;
  }
  return null;
}

function* walkFiles(base) {
  const entries = fs.readdirSync(base, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(base, entry.name);
    if (entry.isDirectory()) {
      yield* walkFiles(fullPath);
    } else if (entry.isFile()) {
      yield fullPath;
    }
  }
}

function discoverCoverageDirectories(coverageRoot) {
  if (!fs.existsSync(coverageRoot)) {
    return [];
  }
  const discovered = [];
  const seen = new Set();
  for (const filePath of walkFiles(coverageRoot)) {
    const basename = path.basename(filePath).toLowerCase();
    if (basename !== 'coverage.xml' && basename !== 'coverage.json') {
      continue;
    }
    const directory = path.dirname(filePath);
    if (seen.has(directory)) {
      continue;
    }
    seen.add(directory);
    discovered.push(directory);
  }
  return discovered;
}

function basenameParts(directory) {
  return directory.split(path.sep).filter(Boolean);
}

function labelForDirectory(directory) {
  const parts = basenameParts(directory);
  for (let index = 0; index < parts.length; index += 1) {
    if (parts[index] === 'runtimes' && index + 1 < parts.length) {
      return `coverage-${parts[index + 1]}`;
    }
  }
  for (let index = parts.length - 1; index >= 0; index -= 1) {
    const part = parts[index];
    if (part.startsWith('coverage-')) {
      return part;
    }
  }
  if (parts.length) {
    return `coverage-${parts[parts.length - 1]}`;
  }
  return null;
}

function readCoverage(directory) {
  const xmlPath = path.join(directory, 'coverage.xml');
  if (fs.existsSync(xmlPath)) {
    const value = parseCoverageXml(readFile(xmlPath));
    if (value !== null) {
      return value;
    }
  }
  const jsonPath = path.join(directory, 'coverage.json');
  if (fs.existsSync(jsonPath)) {
    const value = parseCoverageJson(safeParseJSON(readFile(jsonPath)));
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function runtimeFrom(label) {
  const prefix = 'coverage-';
  return label.startsWith(prefix) ? label.slice(prefix.length) : label;
}

function naturalSortKey(name) {
  const runtime = runtimeFrom(name);
  const parts = runtime.split(/(\d+)/);
  return parts
    .filter(Boolean)
    .map(part => (part.match(/^\d+$/) ? [0, Number.parseInt(part, 10)] : [1, part]));
}

function sortJobs(jobCoverages) {
  const entries = Array.from(jobCoverages.entries());
  if (!entries.length) {
    return entries;
  }
  let preferred = null;
  if (jobCoverages.has('coverage-3.11')) {
    preferred = 'coverage-3.11';
  } else {
    preferred = entries
      .map(([name]) => name)
      .sort((a, b) => {
        const aKey = naturalSortKey(a);
        const bKey = naturalSortKey(b);
        for (let i = 0; i < Math.max(aKey.length, bKey.length); i += 1) {
          const aPart = aKey[i] || [2, ''];
          const bPart = bKey[i] || [2, ''];
          if (aPart[0] !== bPart[0]) {
            return aPart[0] - bPart[0];
          }
          if (aPart[1] < bPart[1]) {
            return -1;
          }
          if (aPart[1] > bPart[1]) {
            return 1;
          }
        }
        return 0;
      })[0];
  }
  return entries.sort((a, b) => {
    if (preferred && a[0] === preferred) {
      return -1;
    }
    if (preferred && b[0] === preferred) {
      return 1;
    }
    const aKey = naturalSortKey(a[0]);
    const bKey = naturalSortKey(b[0]);
    for (let i = 0; i < Math.max(aKey.length, bKey.length); i += 1) {
      const aPart = aKey[i] || [2, ''];
      const bPart = bKey[i] || [2, ''];
      if (aPart[0] !== bPart[0]) {
        return aPart[0] - bPart[0];
      }
      if (aPart[1] < bPart[1]) {
        return -1;
      }
      if (aPart[1] > bPart[1]) {
        return 1;
      }
    }
    return 0;
  });
}

function delta(latest, previous) {
  if (latest === null || latest === undefined) {
    return null;
  }
  if (previous === null || previous === undefined) {
    return null;
  }
  const value = Number.parseFloat(latest) - Number.parseFloat(previous);
  if (!Number.isFinite(value)) {
    return null;
  }
  return Number(Math.round(value * 100) / 100);
}

function loadHistoryRecord(pathname) {
  if (!pathname || !fs.existsSync(pathname)) {
    return null;
  }
  const data = safeParseJSON(readFile(pathname));
  return data && typeof data === 'object' ? data : null;
}

function readHistoryEntries(pathname) {
  if (!pathname || !fs.existsSync(pathname)) {
    return [];
  }
  const lines = readFile(pathname).split(/\r?\n/);
  const entries = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const parsed = safeParseJSON(trimmed);
    if (parsed && typeof parsed === 'object') {
      entries.push(parsed);
    }
  }
  return entries;
}

function findFirst(root, predicate) {
  if (!fs.existsSync(root)) {
    return null;
  }
  for (const filePath of walkFiles(root)) {
    if (predicate(filePath)) {
      return filePath;
    }
  }
  return null;
}

/**
 * Writes a JSON value to a file. Throws if writing fails.
 * @param {string} pathname
 * @param {any} value
 */
function writeJson(pathname, value) {
  try {
    fs.writeFileSync(pathname, JSON.stringify(value), 'utf8');
  } catch (error) {
    console.error(`Failed to write JSON to ${pathname}:`, error);
    throw error;
  }
}

async function computeCoverageStats({
  rootDir = path.join(process.cwd(), 'summary_artifacts'),
  coverageRoot = path.join(process.cwd(), 'summary_artifacts', 'artifacts', 'coverage', 'runtimes'),
  core,
  writeFiles = true,
} = {}) {
  let resolvedCoverageRoot = coverageRoot;
  if (!fs.existsSync(resolvedCoverageRoot)) {
    const legacyRoot = path.join(rootDir, 'coverage-runtimes');
    if (fs.existsSync(legacyRoot)) {
      resolvedCoverageRoot = legacyRoot;
    }
  }
  const jobCoverages = new Map();
  for (const directory of discoverCoverageDirectories(resolvedCoverageRoot)) {
    const label = labelForDirectory(directory);
    if (!label) {
      continue;
    }
    const value = readCoverage(directory);
    if (value === null) {
      continue;
    }
    jobCoverages.set(label, Number(Math.round(value * 100) / 100));
  }

  const sortedJobs = sortJobs(jobCoverages);
  const jobRows = [];
  const tableLines = [];
  let diffReference = null;
  let referenceValue = null;

  if (sortedJobs.length) {
    const [referenceKey, refValue] = sortedJobs[0];
    diffReference = runtimeFrom(referenceKey);
    referenceValue = refValue;
    tableLines.push(`| Runtime | Coverage | Δ vs ${diffReference} |`);
    tableLines.push('| --- | --- | --- |');
    sortedJobs.forEach(([name, value], index) => {
      const label = runtimeFrom(name);
      let deltaDisplay = '—';
      let deltaValue = null;
      if (index > 0 && referenceValue !== null) {
        deltaValue = Number(Math.round((value - referenceValue) * 100) / 100);
        deltaDisplay = `${deltaValue >= 0 ? '+' : ''}${deltaValue.toFixed(2)} pp`;
      }
      jobRows.push({
        name,
        label,
        coverage: Number(Math.round(value * 100) / 100),
        delta_vs_reference: deltaValue,
      });
      tableLines.push(`| ${label} | ${value.toFixed(2)}% | ${deltaDisplay} |`);
    });
  }

  let avg = null;
  let worst = null;
  if (sortedJobs.length) {
    const values = sortedJobs.map(([, value]) => value);
    const sum = values.reduce((acc, value) => acc + value, 0);
    avg = Number(Math.round((sum / values.length) * 100) / 100);
    worst = Number(Math.round(Math.min(...values) * 100) / 100);
  }

  const findPredicate = suffix => filePath => filePath.endsWith(suffix);
  const recordPath = findFirst(rootDir, findPredicate(`${path.sep}coverage-trend.json`));
  const historyPath = findFirst(rootDir, findPredicate(`${path.sep}coverage-trend-history.ndjson`));
  const deltaPath = findFirst(rootDir, findPredicate(`${path.sep}coverage-delta.json`));

  const latestRecord = loadHistoryRecord(recordPath);
  const history = readHistoryEntries(historyPath);

  let latest = latestRecord;
  let previousRecord = null;
  const latestId = record => (record && typeof record === 'object') ? [record.run_id, record.run_number] : [null, null];
  let latestIdentifier = latest ? latestId(latest) : [null, null];
  if (!latest && history.length) {
    latest = history[history.length - 1];
    latestIdentifier = latestId(latest);
  }

  if (history.length) {
    for (let index = history.length - 1; index >= 0; index -= 1) {
      const candidate = history[index];
      if (!candidate) {
        continue;
      }
      const id = latestId(candidate);
      if (id[0] === latestIdentifier[0] && id[1] === latestIdentifier[1]) {
        continue;
      }
      previousRecord = candidate;
      break;
    }
    if (!previousRecord && history.length > 1) {
      previousRecord = history[history.length - 2];
    }
  }

  const extract = (record, key) => {
    if (!record || typeof record !== 'object') {
      return null;
    }
    const value = record[key];
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const historyAvgLatest = extract(latest, 'avg_coverage');
  const historyWorstLatest = extract(latest, 'worst_job_coverage');
  const avgPrev = extract(previousRecord, 'avg_coverage');
  const worstPrev = extract(previousRecord, 'worst_job_coverage');

  const avgLatestValue = avg !== null ? avg : historyAvgLatest;
  const worstLatestValue = worst !== null ? worst : historyWorstLatest;

  const stats = {
    avg_latest: avgLatestValue,
    avg_previous: avgPrev,
    avg_delta: delta(avgLatestValue, avgPrev),
    worst_latest: worstLatestValue,
    worst_previous: worstPrev,
    worst_delta: delta(worstLatestValue, worstPrev),
    history_len: history.length,
  };

  if (jobRows.length) {
    stats.job_coverages = jobRows;
    stats.job_count = jobRows.length;
  }
  if (tableLines.length) {
    stats.coverage_table_markdown = tableLines.join('\n');
  }
  if (diffReference) {
    stats.diff_reference = diffReference;
  }

  let deltaPayload = null;
  if (deltaPath && fs.existsSync(deltaPath)) {
    const parsed = loadHistoryRecord(deltaPath);
    if (parsed) {
      deltaPayload = parsed;
    }
  }

  if (writeFiles) {
    writeJson(path.join(process.cwd(), 'coverage-stats.json'), stats);
    if (deltaPayload) {
      writeJson(path.join(process.cwd(), 'coverage-delta-output.json'), deltaPayload);
    }
  }

  if (core && typeof core.info === 'function') {
    core.info(`Computed coverage stats for ${sortedJobs.length} job(s).`);
  }

  console.log(JSON.stringify(stats));

  return {
    stats,
    deltaPayload,
  };
}

module.exports = {
  parseCoverageXml,
  parseCoverageJson,
  discoverCoverageDirectories,
  labelForDirectory,
  computeCoverageStats,
};
