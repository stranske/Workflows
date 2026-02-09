'use strict';

function escapeRegex(text) {
  return text.replace(/([\\^$*+?.()|{}\[\]])/g, '\\$1');
}

function isEscaped(pattern, index) {
  let count = 0;
  for (let i = index - 1; i >= 0 && pattern[i] === '\\'; i -= 1) {
    count += 1;
  }
  return count % 2 === 1;
}

function findBraceRange(pattern) {
  let start = -1;
  let depth = 0;
  for (let i = 0; i < pattern.length; i += 1) {
    const char = pattern[i];
    if (char === '\\') {
      i += 1;
      continue;
    }
    if (char === '{' && !isEscaped(pattern, i)) {
      if (depth === 0) {
        start = i;
      }
      depth += 1;
      continue;
    }
    if (char === '}' && !isEscaped(pattern, i)) {
      depth -= 1;
      if (depth === 0) {
        return { start, end: i };
      }
    }
  }
  return null;
}

function splitBraceParts(content) {
  const parts = [];
  let current = '';
  let depth = 0;
  for (let i = 0; i < content.length; i += 1) {
    const char = content[i];
    if (char === '\\') {
      current += char;
      if (i + 1 < content.length) {
        current += content[i + 1];
        i += 1;
      }
      continue;
    }
    if (char === '{' && !isEscaped(content, i)) {
      depth += 1;
    } else if (char === '}' && !isEscaped(content, i)) {
      depth = Math.max(0, depth - 1);
    } else if (char === ',' && depth === 0) {
      parts.push(current);
      current = '';
      continue;
    }
    current += char;
  }
  parts.push(current);
  return parts;
}

function expandBraces(pattern) {
  const range = findBraceRange(pattern);
  if (!range) {
    return [pattern];
  }
  const prefix = pattern.slice(0, range.start);
  const suffix = pattern.slice(range.end + 1);
  const content = pattern.slice(range.start + 1, range.end);
  const parts = splitBraceParts(content);
  const expanded = [];
  for (const part of parts) {
    for (const next of expandBraces(`${prefix}${part}${suffix}`)) {
      expanded.push(next);
    }
  }
  return expanded;
}

function convertCharacterClass(source) {
  let body = '';
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === '\\') {
      if (i + 1 < source.length) {
        body += `\\${source[i + 1]}`;
        i += 1;
      }
      continue;
    }
    if (i === 0 && char === '!') {
      body += '^';
      continue;
    }
    body += char;
  }
  return `[${body}]`;
}

function globToRegex(pattern) {
  let regex = '';
  for (let i = 0; i < pattern.length; i += 1) {
    const char = pattern[i];
    if (char === '\\') {
      if (i + 1 < pattern.length) {
        regex += escapeRegex(pattern[i + 1]);
        i += 1;
      } else {
        regex += '\\\\';
      }
      continue;
    }
    if (char === '*') {
      if (pattern[i + 1] === '*') {
        if (pattern[i + 2] === '/') {
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
      let found = false;
      for (; j < pattern.length; j += 1) {
        if (pattern[j] === ']' && !isEscaped(pattern, j)) {
          found = true;
          break;
        }
      }
      if (found) {
        const raw = pattern.slice(i + 1, j);
        regex += convertCharacterClass(raw);
        i = j;
        continue;
      }
    }
    regex += escapeRegex(char);
  }
  return new RegExp(`^${regex}$`);
}

function minimatch(input, pattern, options = {}) {
  const patterns = expandBraces(String(pattern || ''));
  const candidate = String(input || '');
  const flags = options.nocase ? 'i' : '';

  for (const entry of patterns) {
    const regex = globToRegex(entry);
    const testRegex = flags ? new RegExp(regex.source, flags) : regex;
    if (testRegex.test(candidate)) {
      return true;
    }
  }
  return false;
}

module.exports = {
  minimatch,
};
