'use strict';

const fs = require('node:fs');

function splitCsv(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalize(value) {
  return String(value || '').trim().toLowerCase();
}

function truthy(value) {
  if (value == null || value === false) return false;
  if (typeof value === 'string') return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function labelName(label) {
  if (typeof label === 'string') return label;
  if (label && typeof label === 'object') return label.name || '';
  return '';
}

function extractLabels(payload) {
  const labels = [];
  for (const item of payload?.issue?.labels || []) labels.push(labelName(item));
  for (const item of payload?.pull_request?.labels || []) labels.push(labelName(item));
  for (const item of payload?.discussion?.labels || []) labels.push(labelName(item));
  if (payload?.label && payload.action !== 'unlabeled') labels.push(labelName(payload.label));
  return unique(labels.map((item) => item.trim()).filter(Boolean));
}

function actorFrom(payload, actor) {
  return actor || payload?.sender?.login || payload?.actor?.login || payload?.actor || '';
}

function topLevelIndex(expression, operators) {
  let quote = '';
  let inBacktick = false;
  let depth = 0;
  for (let index = 0; index < expression.length; index += 1) {
    const char = expression[index];
    const prev = expression[index - 1];
    if (inBacktick) {
      if (char === '`' && prev !== '\\') inBacktick = false;
      continue;
    }
    if (quote) {
      if (char === quote && prev !== '\\') quote = '';
      continue;
    }
    if (char === '`') {
      inBacktick = true;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (char === '(' || char === '[' || char === '{') depth += 1;
    if (char === ')' || char === ']' || char === '}') depth -= 1;
    if (depth === 0) {
      for (const operator of operators) {
        if (expression.startsWith(operator, index)) {
          return { index, operator };
        }
      }
    }
  }
  return null;
}

function splitTopLevel(expression, delimiter) {
  const parts = [];
  let start = 0;
  let quote = '';
  let inBacktick = false;
  let depth = 0;
  for (let index = 0; index < expression.length; index += 1) {
    const char = expression[index];
    const prev = expression[index - 1];
    if (inBacktick) {
      if (char === '`' && prev !== '\\') inBacktick = false;
      continue;
    }
    if (quote) {
      if (char === quote && prev !== '\\') quote = '';
      continue;
    }
    if (char === '`') {
      inBacktick = true;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (char === '(' || char === '[' || char === '{') depth += 1;
    if (char === ')' || char === ']' || char === '}') depth -= 1;
    if (depth === 0 && char === delimiter) {
      parts.push(expression.slice(start, index).trim());
      start = index + 1;
    }
  }
  parts.push(expression.slice(start).trim());
  return parts;
}

function stripParens(expression) {
  let current = expression.trim();
  while (current.startsWith('(') && current.endsWith(')')) {
    let quote = '';
    let inBacktick = false;
    let depth = 0;
    let wrapsWholeExpression = true;
    for (let index = 0; index < current.length; index += 1) {
      const char = current[index];
      const prev = current[index - 1];
      if (inBacktick) {
        if (char === '`' && prev !== '\\') inBacktick = false;
        continue;
      }
      if (quote) {
        if (char === quote && prev !== '\\') quote = '';
        continue;
      }
      if (char === '`') {
        inBacktick = true;
        continue;
      }
      if (char === '"' || char === "'") {
        quote = char;
        continue;
      }
      if (char === '(') depth += 1;
      if (char === ')') depth -= 1;
      if (depth === 0 && index < current.length - 1) {
        wrapsWholeExpression = false;
        break;
      }
    }
    if (!wrapsWholeExpression) break;
    current = current.slice(1, -1).trim();
  }
  return current;
}

function parseLiteral(expression) {
  const value = expression.trim();
  if (value === 'null') return null;
  if (value === 'true') return true;
  if (value === 'false') return false;
  if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
  if ((value.startsWith("'") && value.endsWith("'")) || (value.startsWith('"') && value.endsWith('"'))) {
    return value.slice(1, -1).replace(/\\(['"\\])/g, '$1');
  }
  if (value.startsWith('`') && value.endsWith('`')) {
    const raw = value.slice(1, -1);
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  return undefined;
}

function flatten(values) {
  return values.flatMap((value) => (Array.isArray(value) ? flatten(value) : [value]));
}

function resolvePath(payload, pathExpression) {
  if (!pathExpression || pathExpression === '@') return payload;
  const segments = pathExpression.split('.').filter(Boolean);
  let current = [payload];
  for (const rawSegment of segments) {
    const flattenArray = rawSegment.endsWith('[]');
    const segment = flattenArray ? rawSegment.slice(0, -2) : rawSegment;
    const next = [];
    for (const item of current) {
      const source = Array.isArray(item) ? item : [item];
      for (const candidate of source) {
        if (candidate == null) continue;
        const value = segment ? candidate[segment] : candidate;
        if (flattenArray && Array.isArray(value)) {
          next.push(...value);
        } else {
          next.push(value);
        }
      }
    }
    current = next;
  }
  const compact = current.filter((item) => item !== undefined);
  if (compact.length === 0) return undefined;
  return compact.length === 1 ? compact[0] : compact;
}

function compare(left, operator, right) {
  if (operator === '==') return left === right;
  if (operator === '!=') return left !== right;
  if (operator === '>=') return left >= right;
  if (operator === '<=') return left <= right;
  if (operator === '>') return left > right;
  if (operator === '<') return left < right;
  return false;
}

function evaluateFunction(name, args, payload) {
  const values = args.map((arg) => evaluateExpression(arg, payload));
  if (name === 'contains') {
    const [subject, search] = values;
    if (Array.isArray(subject)) return subject.includes(search);
    return String(subject || '').includes(String(search || ''));
  }
  if (name === 'starts_with') return String(values[0] || '').startsWith(String(values[1] || ''));
  if (name === 'ends_with') return String(values[0] || '').endsWith(String(values[1] || ''));
  if (name === 'length') {
    if (values[0] == null) return 0;
    if (typeof values[0] === 'object') return Object.keys(values[0]).length;
    return String(values[0]).length;
  }
  if (name === 'not_null') return values.find((value) => value != null);
  throw new Error(`Unsupported custom-predicate function: ${name}`);
}

function evaluateExpression(expression, payload) {
  const current = stripParens(String(expression || '').trim());
  if (!current) return true;

  const orIndex = topLevelIndex(current, ['||']);
  if (orIndex) {
    return truthy(evaluateExpression(current.slice(0, orIndex.index), payload))
      || truthy(evaluateExpression(current.slice(orIndex.index + 2), payload));
  }
  const andIndex = topLevelIndex(current, ['&&']);
  if (andIndex) {
    return truthy(evaluateExpression(current.slice(0, andIndex.index), payload))
      && truthy(evaluateExpression(current.slice(andIndex.index + 2), payload));
  }
  if (current.startsWith('!')) return !truthy(evaluateExpression(current.slice(1), payload));

  const comparison = topLevelIndex(current, ['==', '!=', '>=', '<=', '>', '<']);
  if (comparison) {
    const left = evaluateExpression(current.slice(0, comparison.index), payload);
    const right = evaluateExpression(current.slice(comparison.index + comparison.operator.length), payload);
    return compare(left, comparison.operator, right);
  }

  const functionMatch = current.match(/^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$/);
  if (functionMatch) {
    return evaluateFunction(functionMatch[1], splitTopLevel(functionMatch[2], ','), payload);
  }

  const literal = parseLiteral(current);
  if (literal !== undefined) return literal;
  return resolvePath(payload, current);
}

function evaluatePredicate(predicate, payload) {
  if (!String(predicate || '').trim()) return true;
  return truthy(evaluateExpression(predicate, payload));
}

function applyMode(result, mode) {
  if (result.shouldRun || mode !== 'warning') return result;
  return {
    shouldRun: true,
    reason: `warning mode bypassed denial: ${result.reason}`,
    matchedLabel: result.matchedLabel || '',
    warningModeBypassed: true,
  };
}

function evaluateEligibility(options) {
  const payload = options.payload || {};
  const labels = extractLabels(payload);
  const normalizedLabels = labels.map(normalize);
  const expectedLabels = splitCsv(options.expectedLabels).map(normalize);
  const forbiddenLabels = splitCsv(options.forbiddenLabels).map(normalize);
  const expectedActors = splitCsv(options.expectedActors).map(normalize);
  const expectedActions = splitCsv(options.expectedActions).map(normalize);
  const eventName = normalize(options.eventName);
  const eventAction = normalize(payload.action);
  const actor = normalize(actorFrom(payload, options.actor));
  const mode = normalize(options.mode) || 'enforce';

  let result = { shouldRun: true, reason: 'eligible', matchedLabel: '' };

  if (expectedActions.length > 0 && !expectedActions.includes(eventAction) && !expectedActions.includes(eventName)) {
    result = {
      shouldRun: false,
      reason: `event action not allowed: ${eventAction || eventName || 'unknown'}`,
      matchedLabel: '',
    };
    return applyMode(result, mode);
  }

  if (expectedActors.length > 0 && !expectedActors.includes(actor)) {
    result = {
      shouldRun: false,
      reason: `actor not allowed: ${actor || 'unknown'}`,
      matchedLabel: '',
    };
    return applyMode(result, mode);
  }

  const forbidden = forbiddenLabels.find((label) => normalizedLabels.includes(label));
  if (forbidden) {
    result = { shouldRun: false, reason: `forbidden label matched: ${forbidden}`, matchedLabel: forbidden };
    return applyMode(result, mode);
  }

  if (expectedLabels.length > 0) {
    const matched = expectedLabels.find((label) => normalizedLabels.includes(label));
    if (!matched) {
      result = { shouldRun: false, reason: 'expected label not present', matchedLabel: '' };
      return applyMode(result, mode);
    }
    result.matchedLabel = matched;
  }

  const predicatePayload = {
    ...payload,
    event_name: eventName,
  };

  try {
    if (!evaluatePredicate(options.customPredicate, predicatePayload)) {
      result = { shouldRun: false, reason: 'custom predicate evaluated falsy', matchedLabel: result.matchedLabel };
      return applyMode(result, mode);
    }
  } catch (error) {
    result = {
      shouldRun: false,
      reason: `custom predicate error: ${error.message}`,
      matchedLabel: result.matchedLabel,
    };
    return applyMode(result, mode);
  }

  return result;
}

function writeOutput(name, value) {
  const outputPath = process.env.GITHUB_OUTPUT;
  if (!outputPath) {
    console.log(`${name}=${value}`);
    return;
  }
  const text = String(value);
  if (text.includes('\n')) {
    fs.appendFileSync(outputPath, `${name}<<EOF\n${text}\nEOF\n`, 'utf8');
  } else {
    fs.appendFileSync(outputPath, `${name}=${text}\n`, 'utf8');
  }
}

function loadPayload() {
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath) return {};
  return JSON.parse(fs.readFileSync(eventPath, 'utf8'));
}

function main() {
  const result = evaluateEligibility({
    payload: loadPayload(),
    eventName: process.env.INPUT_EVENT_NAME || process.env.GITHUB_EVENT_NAME || '',
    actor: process.env.GITHUB_ACTOR || '',
    expectedLabels: process.env.INPUT_EXPECTED_LABELS || '',
    forbiddenLabels: process.env.INPUT_FORBIDDEN_LABELS || '',
    expectedActors: process.env.INPUT_EXPECTED_ACTORS || '',
    expectedActions: process.env.INPUT_EXPECTED_ACTIONS || '',
    customPredicate: process.env.INPUT_CUSTOM_PREDICATE || '',
    mode: process.env.INPUT_MODE || 'enforce',
  });

  writeOutput('should-run', result.shouldRun ? 'true' : 'false');
  writeOutput('reason', result.reason);
  writeOutput('matched-label', result.matchedLabel || '');

  const annotation = result.warningModeBypassed || !result.shouldRun ? 'warning' : 'notice';
  console.log(`::${annotation}::agent-event-eligibility ${result.shouldRun ? 'allowed' : 'denied'}: ${result.reason}`);
}

if (require.main === module) {
  main();
}

module.exports = {
  evaluateEligibility,
  evaluateExpression,
  evaluatePredicate,
  extractLabels,
};
