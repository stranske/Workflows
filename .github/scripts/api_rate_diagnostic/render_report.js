'use strict';

const fs = require('node:fs');
const {
  parsePct,
  parseSummary,
  renderUtilizationAnalysis,
} = require('./detect_thresholds.js');

function formatGenerated(date = new Date()) {
  return date.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
}

function appendSummary(lines, outputPath = process.env.GITHUB_STEP_SUMMARY) {
  const body = `${lines.join('\n')}\n`;
  if (outputPath) {
    fs.appendFileSync(outputPath, body);
  } else {
    process.stdout.write(body);
  }
  return body;
}

function tokenCell(token, resource) {
  return `${token?.[resource]?.used}/${token?.[resource]?.limit} (${token?.[resource]?.pct}%)`;
}

function tokenRows(summary) {
  const rows = [];
  const specs = [
    ['github_token', 'GITHUB_TOKEN'],
    ['owner_pr_pat', 'OWNER_PR_PAT'],
    ['workflows_app', 'WORKFLOWS_APP'],
  ];
  for (const [tokenKey, label] of specs) {
    const token = summary?.tokens?.[tokenKey];
    if (token && token.source) {
      rows.push(
        `| ${label} | ${tokenCell(token, 'core')} | ${tokenCell(token, 'graphql')} | ${tokenCell(token, 'search')} | ${token.reset || 'N/A'} |`,
      );
    }
  }
  return rows;
}

function parseJson(input, fallback) {
  if (!input) {
    return fallback;
  }
  try {
    return JSON.parse(input);
  } catch (_error) {
    return fallback;
  }
}

function buildConsumerActivityLines(activityInput) {
  const activity = Array.isArray(activityInput) ? activityInput : parseJson(activityInput, []);
  if (!Array.isArray(activity) || activity.length === 0) {
    return [];
  }
  const lines = [
    '## 📦 Consumer Repository Activity (Last Hour)',
    '',
    '| Repository | Runs | In Progress | Queued | Top Workflow |',
    '|------------|------|-------------|--------|--------------|',
  ];
  for (const repo of activity) {
    const topWorkflow = repo.top_workflows?.[0] || {};
    lines.push(
      `| ${repo.repo} | ${repo.runs_last_hour} | ${repo.in_progress} | ${repo.queued} | ${topWorkflow.name || 'N/A'} (${topWorkflow.count || 0}) |`,
    );
  }
  const totalRuns = activity.reduce((total, repo) => total + (repo.runs_last_hour || 0), 0);
  const totalInProgress = activity.reduce((total, repo) => total + (repo.in_progress || 0), 0);
  const totalQueued = activity.reduce((total, repo) => total + (repo.queued || 0), 0);
  lines.push(
    '',
    '**Total across all repos:**',
    `- Runs: ${totalRuns}`,
    `- In progress: ${totalInProgress}`,
    `- Queued: ${totalQueued}`,
  );
  return lines;
}

function buildLoadBalancingLines(summary) {
  const gt = summary?.tokens?.github_token || {};
  const pat = summary?.tokens?.owner_pr_pat || {};
  const app = summary?.tokens?.workflows_app || {};
  const availableTokens = [gt, pat, app].filter((token) => token.source).length;
  const lines = [
    '## ⚖️ Load Balancing',
    '',
    `**Available auth methods:** ${availableTokens}`,
    '',
  ];

  if (availableTokens >= 2) {
    lines.push('✅ Multiple authentication methods are configured');
    const pctPairs = [gt, pat, app].map((token) => {
      const text = String(token.core?.pct ?? '0').replace(/[^0-9.]/g, '') || '0';
      return { text, value: parsePct(text) };
    });
    const sorted = pctPairs.sort((a, b) => b.value - a.value);
    const maxPct = sorted[0]?.value;
    const minPct = sorted[sorted.length - 1]?.value;
    if (Number.isFinite(maxPct) && Number.isFinite(minPct)) {
      const hasDecimal = sorted[0].text.includes('.') || sorted[sorted.length - 1].text.includes('.');
      const diffNumber = Math.round((maxPct - minPct) * 10) / 10;
      const diff = hasDecimal ? diffNumber.toFixed(1) : String(diffNumber);
      if (diff > 30) {
        lines.push(`⚠️ Load appears uneven (${diff}% difference).`);
        lines.push('Consider reviewing token usage in workflows.');
      } else {
        lines.push('✅ Load appears balanced across tokens');
      }
    }
  } else {
    lines.push(`⚠️ Only ${availableTokens} auth method(s) configured.`);
    lines.push('Consider adding:');
    if (!pat.source) {
      lines.push('- OWNER_PR_PAT PAT for cross-repo operations');
    }
    if (!app.source) {
      lines.push('- WORKFLOWS_APP GitHub App for higher rate limits');
    }
  }
  return lines;
}

function buildCurrentReport({
  summaryJson = '{}',
  consumerActivityJson = '[]',
  generated = formatGenerated(),
} = {}) {
  const summary = parseSummary(summaryJson);
  const lines = [
    '# 📊 API Rate Limit Diagnostic Report',
    '',
    `**Generated:** ${generated}`,
    '',
    '## 🔑 Authentication Token Rate Limits',
    '',
    '| Token | Core API | GraphQL | Search | Reset Time |',
    '|-------|----------|---------|--------|------------|',
    ...tokenRows(summary),
    '',
    '## ⚠️ Utilization Analysis',
    '',
    ...renderUtilizationAnalysis(summary),
    '',
  ];
  const consumerLines = buildConsumerActivityLines(consumerActivityJson);
  if (consumerLines.length > 0) {
    lines.push(...consumerLines, '');
  }
  lines.push(
    '',
    ...buildLoadBalancingLines(summary),
    '',
    '## 💡 Recommendations',
    '',
    '1. GitHub App tokens: higher rate limits than PATs',
    '2. GITHUB_TOKEN: higher limits, but limited scope',
    '3. Prefer GitHub App auth for high-volume operations',
    '4. Implement retry logic with exponential backoff',
    '5. Use conditional requests (ETags) to reduce API usage',
  );
  return lines;
}

function periodDays(startDate, endDate) {
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return 'unknown';
  }
  return Math.trunc((end - start) / 86400000);
}

function buildHistoricalReport({
  startDate,
  endDate,
  runCount = 0,
  runs = [],
  generated = formatGenerated(),
  serverUrl = process.env.GITHUB_SERVER_URL,
  repository = process.env.GITHUB_REPOSITORY,
} = {}) {
  const lines = [
    '# 📊 Historical API Rate Limit Report',
    '',
    `**Report Period:** ${startDate} to ${endDate}`,
    `**Generated:** ${generated}`,
    `**Data Points:** ${runCount} successful runs`,
    '',
  ];

  if (Number(runCount) === 0) {
    lines.push(
      '⚠️ **No diagnostic data available for this period.**',
      '',
      'Health 75 collects snapshots every 4 hours.',
      'Historical data is only available for successful runs.',
      '',
      "**Tip:** Run the workflow in 'current' mode to start collecting data.",
    );
    return lines;
  }

  lines.push(
    '## 📈 Summary Statistics',
    '',
    '| Metric | Value |',
    '|--------|-------|',
    `| Total Data Points | ${runCount} |`,
    '| Collection Frequency | Every 4 hours |',
    `| Period Duration | ${periodDays(startDate, endDate)} days |`,
    '',
    '## 📋 Available Run History',
    '',
    'Recent successful diagnostic runs in this period:',
    '',
  );

  const baseUrl = `${serverUrl}/${repository}`;
  for (const run of runs.slice(0, 10)) {
    lines.push(
      `- [${String(run.created_at || '').split('T')[0]}] Run #${run.run_number} - [View Details](${baseUrl}/actions/runs/${run.id})`,
    );
  }
  if (Number(runCount) > 10) {
    lines.push('', `_...and ${Number(runCount) - 10} more runs_`);
  }
  lines.push(
    '',
    '## 💡 Usage Notes',
    '',
    '- Each run captures a point-in-time API rate snapshot',
    '- Click a run above to view detailed rate limit data',
    '- Rate limits reset hourly; snapshots show utilization at collection time',
    '- For trend analysis, review multiple consecutive runs',
  );
  return lines;
}

function runCurrentReportStep({
  summaryJson = process.env.SUMMARY_JSON,
  consumerActivityJson = process.env.CONSUMER_ACTIVITY,
  outputPath = process.env.GITHUB_STEP_SUMMARY,
} = {}) {
  return appendSummary(buildCurrentReport({ summaryJson, consumerActivityJson }), outputPath);
}

function runHistoricalReportStep({
  startDate = process.env.START_DATE,
  endDate = process.env.END_DATE,
  runCount = Number(process.env.RUN_COUNT || 0),
  runsPath = '/tmp/runs.json',
  outputPath = process.env.GITHUB_STEP_SUMMARY,
} = {}) {
  const runs = fs.existsSync(runsPath) ? parseJson(fs.readFileSync(runsPath, 'utf8'), []) : [];
  return appendSummary(buildHistoricalReport({ startDate, endDate, runCount, runs }), outputPath);
}

module.exports = {
  appendSummary,
  buildConsumerActivityLines,
  buildCurrentReport,
  buildHistoricalReport,
  buildLoadBalancingLines,
  formatGenerated,
  periodDays,
  runCurrentReportStep,
  runHistoricalReportStep,
  tokenRows,
};
