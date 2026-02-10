'use strict';

function escapeRegExp(value) {
  return value.replace(/[\\^$.*+?()[\]{}|]/g, '\\$&');
}

function expandBraces(pattern) {
  const start = pattern.indexOf('{');
  if (start === -1) {
    return [pattern];
  }
  let depth = 0;
  let end = -1;
  for (let i = start; i < pattern.length; i += 1) {
    const char = pattern[i];
    if (char === '\\') {
      i += 1;
      continue;
    }
    if (char === '{') {
      depth += 1;
    } else if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) {
    return [pattern];
  }
  const prefix = pattern.slice(0, start);
  const suffix = pattern.slice(end + 1);
  const body = pattern.slice(start + 1, end);
  const parts = [];
  let current = '';
  let nested = 0;
  for (let i = 0; i < body.length; i += 1) {
    const char = body[i];
    if (char === '\\') {
      current += char;
      if (i + 1 < body.length) {
        current += body[i + 1];
        i += 1;
      }
      continue;
    }
    if (char === '{') {
      nested += 1;
    } else if (char === '}') {
      nested -= 1;
    }
    if (char === ',' && nested === 0) {
      parts.push(current);
      current = '';
      continue;
    }
    current += char;
  }
  parts.push(current);
  const expanded = [];
  for (const part of parts) {
    for (const next of expandBraces(`${prefix}${part}${suffix}`)) {
      expanded.push(next);
    }
  }
  return expanded;
}

function globToRegExp(pattern) {
  let regex = '^';
  for (let i = 0; i < pattern.length; i += 1) {
    const char = pattern[i];
    if (char === '\\') {
      const next = pattern[i + 1];
      if (next !== undefined) {
        regex += escapeRegExp(next);
        i += 1;
      } else {
        regex += '\\\\';
      }
      continue;
    }
    if (char === '*') {
      const next = pattern[i + 1];
      if (next === '*') {
        const nextChar = pattern[i + 2];
        if (nextChar === '/') {
          regex += '(?:.*/)?';
          i += 2;
        } else {
          regex += '.*';
          i += 1;
        }
      } else {
        regex += '[^/]*';
      }
      continue;
    }
    if (char === '?') {
      regex += '[^/]';
      continue;
    }
    if (char === '[') {
      let j = i + 1;
      let content = '';
      let closed = false;
      if (pattern[j] === '!' || pattern[j] === '^') {
        content += '^';
        j += 1;
      }
      for (; j < pattern.length; j += 1) {
        const inner = pattern[j];
        if (inner === '\\') {
          if (j + 1 < pattern.length) {
            content += `\\${pattern[j + 1]}`;
            j += 1;
            continue;
          }
        }
        if (inner === ']') {
          closed = true;
          break;
        }
        content += inner;
      }
      if (closed) {
        regex += `[${content}]`;
        i = j;
      } else {
        regex += '\\[';
      }
      continue;
    }
    regex += escapeRegExp(char);
  }
  regex += '$';
  return new RegExp(regex);
}

function minimatch(pathname, pattern, options = {}) {
  if (typeof pathname !== 'string' || typeof pattern !== 'string') {
    return false;
  }

  const opts = options || {};

  if (!opts.nocomment && pattern.startsWith('#')) {
    return false;
  }

  if (!opts.nonegate && pattern.startsWith('!')) {
    const next = pattern.slice(1);
    return !minimatch(pathname, next, { ...opts, nonegate: true });
  }

  let target = pathname;
  let pat = pattern;

  if (opts.nocase) {
    target = target.toLowerCase();
    pat = pat.toLowerCase();
  }

  const patterns = expandBraces(pat);
  for (const expanded of patterns) {
    const regex = globToRegExp(expanded);
    if (regex.test(target)) {
      return true;
    }
  }
  return false;
}

module.exports = { minimatch };
