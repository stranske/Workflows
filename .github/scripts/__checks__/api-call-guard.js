#!/usr/bin/env node
/**
 * API Call Guard - CI check for unprotected GitHub API calls
 * 
 * This script scans .github/scripts/*.js files to ensure all GitHub API calls
 * are wrapped with the token-aware retry pattern for rate limit resilience.
 * 
 * Usage:
 *   node .github/scripts/__checks__/api-call-guard.js
 * 
 * Exit codes:
 *   0 - All API calls are properly wrapped
 *   1 - Unprotected API calls found (see report)
 */

const fs = require('fs');
const path = require('path');

// Patterns that indicate an API call
const API_CALL_PATTERNS = [
  /github\.rest\./g,
  /github\.graphql\(/g,
  /github\.paginate\(/g,
  /octokit\.rest\./g,
  /octokit\.graphql\(/g,
];

// Patterns that indicate the retry wrapper is being used
const RETRY_WRAPPER_PATTERNS = [
  /withRetry\s*\(/,
  /createTokenAwareRetry/,
  /paginateWithRetry/,
  /ensureRateLimitWrapped/,
  /createRateLimitedGithub/,
];

// Files that are exempt from this check (the retry wrapper itself, tests, etc.)
const EXEMPT_FILES = [
  'github-api-with-retry.js',
  'github-rate-limited-wrapper.js',
  'rate-limit-aware-client.js',
  'token_load_balancer.js',
  'api-helpers.js', // Low-level helpers used by retry wrapper
];

// Files in __tests__ directory are exempt
const EXEMPT_DIRS = ['__tests__', '__checks__', 'node_modules'];

function scanFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  const fileName = path.basename(filePath);
  
  // Check if file is exempt
  if (EXEMPT_FILES.includes(fileName)) {
    return { exempt: true, file: filePath };
  }
  
  // Check if file imports the retry wrapper
  const hasRetryImport = RETRY_WRAPPER_PATTERNS.some(pattern => pattern.test(content));
  
  // Find all API calls
  const apiCalls = [];
  lines.forEach((line, index) => {
    const lineNum = index + 1;
    
    // Skip comments
    if (line.trim().startsWith('//') || line.trim().startsWith('*')) {
      return;
    }
    
    API_CALL_PATTERNS.forEach(pattern => {
      // Reset lastIndex for global patterns
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(line)) !== null) {
        apiCalls.push({
          line: lineNum,
          code: line.trim(),
          match: match[0],
        });
      }
    });
  });
  
  if (apiCalls.length === 0) {
    return { noApiCalls: true, file: filePath };
  }
  
  // Check if API calls are wrapped in withRetry or use wrapped github client
  const unprotectedCalls = apiCalls.filter(call => {
    // Simple heuristic: check if the line or nearby context has withRetry
    const lineContent = call.code;
    
    // Check if this call is inside a withRetry callback
    // Look for patterns like: withRetry(() => github.rest. or withRetry((client) => client.rest.
    if (/withRetry\s*\(\s*\(?[^)]*\)?\s*=>\s*/.test(lineContent)) {
      return false; // This call is wrapped
    }
    
    // Check if the call uses a client parameter (indicating it's in a callback)
    if (/\(client\)\s*=>\s*client\./.test(lineContent)) {
      return false; // Using client param pattern
    }
    
    // If file has ensureRateLimitWrapped import and wraps github at entry,
    // all subsequent API calls are protected via the proxy
    if (hasRetryImport) {
      return false; // File imports wrapper, assume calls are protected
    }
    
    return true; // Unprotected
  });
  
  return {
    file: filePath,
    hasRetryImport,
    totalApiCalls: apiCalls.length,
    unprotectedCalls,
    protected: unprotectedCalls.length === 0,
  };
}

function scanDirectory(dirPath) {
  const results = [];
  
  function walk(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      
      if (entry.isDirectory()) {
        if (!EXEMPT_DIRS.includes(entry.name)) {
          walk(fullPath);
        }
      } else if (entry.isFile() && entry.name.endsWith('.js')) {
        results.push(scanFile(fullPath));
      }
    }
  }
  
  walk(dirPath);
  return results;
}

function generateReport(results) {
  const issues = results.filter(r => !r.exempt && !r.noApiCalls && !r.protected);
  const protected = results.filter(r => r.protected);
  const exempt = results.filter(r => r.exempt);
  const noApiCalls = results.filter(r => r.noApiCalls);
  
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║          GitHub API Call Protection Audit Report            ║');
  console.log('╚══════════════════════════════════════════════════════════════╝\n');
  
  console.log(`📊 Summary:`);
  console.log(`   ✅ Protected files: ${protected.length}`);
  console.log(`   ⏭️  Exempt files: ${exempt.length}`);
  console.log(`   📄 No API calls: ${noApiCalls.length}`);
  console.log(`   ❌ Unprotected files: ${issues.length}\n`);
  
  if (issues.length > 0) {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('                    ❌ UNPROTECTED API CALLS                    ');
    console.log('═══════════════════════════════════════════════════════════════\n');
    
    let totalUnprotected = 0;
    
    issues.forEach(issue => {
      const relPath = path.relative(process.cwd(), issue.file);
      console.log(`📁 ${relPath}`);
      console.log(`   Total API calls: ${issue.totalApiCalls}`);
      console.log(`   Unprotected: ${issue.unprotectedCalls.length}`);
      console.log(`   Has retry import: ${issue.hasRetryImport ? 'Yes' : 'No'}`);
      console.log('');
      
      issue.unprotectedCalls.slice(0, 5).forEach(call => {
        console.log(`   Line ${call.line}: ${call.code.substring(0, 80)}${call.code.length > 80 ? '...' : ''}`);
      });
      
      if (issue.unprotectedCalls.length > 5) {
        console.log(`   ... and ${issue.unprotectedCalls.length - 5} more`);
      }
      console.log('');
      
      totalUnprotected += issue.unprotectedCalls.length;
    });
    
    console.log('═══════════════════════════════════════════════════════════════');
    console.log(`Total unprotected API calls: ${totalUnprotected}`);
    console.log('');
    console.log('🔧 To fix, wrap API calls with the token-aware retry pattern:');
    console.log('');
    console.log('   const { createTokenAwareRetry } = require(\'./github-api-with-retry.js\');');
    console.log('   const { withRetry } = await createTokenAwareRetry({ github, core });');
    console.log('   const { data } = await withRetry((client) => client.rest.issues.get({...}));');
    console.log('');
  }
  
  return issues.length;
}

// Main
const scriptsDir = path.join(__dirname, '..');
const results = scanDirectory(scriptsDir);
const issueCount = generateReport(results);

process.exit(issueCount > 0 ? 1 : 0);
