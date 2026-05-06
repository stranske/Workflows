'use strict';

const fs = require('node:fs');

const CURRENT_TOKEN_PATHS = [
  ['github_token', '.tokens.github_token'],
  ['owner_pr_pat', '.tokens.owner_pr_pat'],
  ['workflows_app', '.tokens.workflows_app'],
];

const ALERT_TOKEN_PATHS = [
  ['github_token', '.tokens.github_token'],
  ['owner_pr_pat', '.tokens.owner_pr_pat'],
  ['service_bot_pat', '.tokens.service_bot_pat'],
  ['workflows_app', '.tokens.workflows_app'],
  ['keepalive_app', '.tokens.keepalive_app'],
  ['gh_app', '.tokens.gh_app'],
];

function parseSummary(input) {
  if (!input) {
    return {};
  }
  try {
    return typeof input === 'string' ? JSON.parse(input) : input;
  } catch (_error) {
    return {};
  }
}

function parsePct(value) {
  const cleaned = String(value ?? '0').replace(/[^0-9.]/g, '');
  return cleaned ? Number(cleaned) : 0;
}

function pctText(value) {
  const cleaned = String(value ?? '0').replace(/[^0-9.]/g, '');
  return cleaned || '0';
}

function getToken(summary, tokenKey) {
  const token = summary?.tokens?.[tokenKey];
  return token && typeof token === 'object' ? token : {};
}

function classifyPct(pct, { moderate = 50, high = 80 } = {}) {
  if (pct > high) {
    return 'high';
  }
  if (pct > moderate) {
    return 'moderate';
  }
  return 'normal';
}

function currentUtilizationWarnings(summaryInput) {
  const summary = parseSummary(summaryInput);
  const warnings = [];
  for (const [tokenKey] of CURRENT_TOKEN_PATHS) {
    const token = getToken(summary, tokenKey);
    if (!token.source) {
      continue;
    }
    const source = token.source || 'unknown';
    const corePct = parsePct(token.core?.pct);
    const graphqlPct = parsePct(token.graphql?.pct);
    const corePctText = pctText(token.core?.pct);
    const graphqlPctText = pctText(token.graphql?.pct);
    const coreClass = classifyPct(corePct);
    const graphqlClass = classifyPct(graphqlPct);
    if (coreClass === 'high') {
      warnings.push({ source, resource: 'Core API', pct: corePct, pctText: corePctText, class: 'high' });
    } else if (coreClass === 'moderate') {
      warnings.push({ source, resource: 'Core API', pct: corePct, pctText: corePctText, class: 'moderate' });
    }
    if (graphqlClass === 'high') {
      warnings.push({ source, resource: 'GraphQL', pct: graphqlPct, pctText: graphqlPctText, class: 'high' });
    } else if (graphqlClass === 'moderate') {
      warnings.push({ source, resource: 'GraphQL', pct: graphqlPct, pctText: graphqlPctText, class: 'moderate' });
    }
  }
  return warnings;
}

function renderUtilizationAnalysis(summaryInput) {
  const warnings = currentUtilizationWarnings(summaryInput);
  if (warnings.length === 0) {
    return ['✅ All tokens within normal utilization (<50%)'];
  }
  return warnings.flatMap((warning) => {
    if (warning.class === 'high') {
      return [`- 🔴 **${warning.source}** ${warning.resource}: ${warning.pctText}%`, '  - HIGH RISK'];
    }
    return [`- 🟡 **${warning.source}** ${warning.resource}: ${warning.pctText}%`, '  - MODERATE'];
  });
}

function hasHighUsageAlert(summaryInput) {
  const summary = parseSummary(summaryInput);
  return ALERT_TOKEN_PATHS.some(([tokenKey]) => {
    const token = getToken(summary, tokenKey);
    if (!token.source) {
      return false;
    }
    return parsePct(token.core?.pct) > 85 || parsePct(token.graphql?.pct) > 85;
  });
}

function criticalCoreWarnings(summaryInput) {
  const summary = parseSummary(summaryInput);
  return CURRENT_TOKEN_PATHS.flatMap(([tokenKey]) => {
    const token = getToken(summary, tokenKey);
    if (!token.source) {
      return [];
    }
    const corePct = parsePct(token.core?.pct);
    const corePctText = pctText(token.core?.pct);
    return corePct > 90 ? [`::warning::Critical API rate limit utilization detected (${corePctText}%)`] : [];
  });
}

function appendOutput(name, value, outputPath = process.env.GITHUB_OUTPUT) {
  if (!outputPath) {
    return;
  }
  fs.appendFileSync(outputPath, `${name}=${value}\n`);
}

function runAlertCheckStep({
  summaryJson = process.env.SUMMARY_JSON,
  outputPath = process.env.GITHUB_OUTPUT,
} = {}) {
  const alertNeeded = hasHighUsageAlert(summaryJson) ? 'true' : 'false';
  appendOutput('alert_needed', alertNeeded, outputPath);
  return alertNeeded;
}

function runCriticalWarningStep({ summaryJson = process.env.SUMMARY_JSON } = {}) {
  const warnings = criticalCoreWarnings(summaryJson);
  warnings.forEach((warning) => console.log(warning));
  return warnings;
}

module.exports = {
  ALERT_TOKEN_PATHS,
  CURRENT_TOKEN_PATHS,
  classifyPct,
  criticalCoreWarnings,
  currentUtilizationWarnings,
  hasHighUsageAlert,
  parsePct,
  pctText,
  parseSummary,
  renderUtilizationAnalysis,
  runAlertCheckStep,
  runCriticalWarningStep,
};
