// Source-owned, immutable Git blob capture. Derived text is never a Git patch.
'use strict';
const path = require('path');
const {createHash} = require('crypto');
const {execFileSync} = require('child_process');
const {ensureRateLimitWrapped} = require('./github-rate-limited-wrapper.js');
const SCHEMA = 'verifier-gzip-text-asset/v1';
const CODEC = 'gzip-single-member-utf8/v1';
const MAX_RAW = 4 * 1024 * 1024;
const MAX_TEXT = 4 * 1024 * 1024;
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
function evidencePath(value) {
  return typeof value === 'string' && /^docs\/verification\/(?:[^/]+\/)*[^/]+\.(?:log|txt|xml)\.gz$/.test(value)
    && !/[\\\x00-\x1f\x7f]/.test(value) && value.split('/').every(p => p && p !== '.' && p !== '..');
}
function validatedSelectors(value) {
  const rows = typeof value === 'string' ? (value.trim() ? JSON.parse(value) : []) : value ?? [];
  if (!Array.isArray(rows) || rows.some(row => !row || typeof row !== 'object'
      || !['git_blob','comment','artifact_member'].includes(row.kind))) throw new Error('Invalid verification material selectors');
  const selected = rows.filter(row => row.kind === 'git_blob');
  if (selected.length > 80 || rows.length - selected.length > 20) throw new Error('Verification material selector count bound');
  if (selected.some(row => Object.keys(row).sort().join(',') !== 'kind,path' || !evidencePath(row.path))
      || new Set(selected.map(row => row.path)).size !== selected.length) throw new Error('Invalid git_blob path selector');
  const artifacts = rows.filter(row => row.kind === 'artifact_member');
  const safe = value => typeof value === 'string' && value.length > 0 && value.length <= 1024
    && !/[\\\x00-\x1f\x7f*?\[\]^]/.test(value) && !value.startsWith('/') && !value.startsWith('-')
    && !/^[A-Za-z]:/.test(value) && value.split('/').every(part => part && part !== '.' && part !== '..');
  for (const row of artifacts) {
    if (![row.run_id,row.artifact_id].every(id => Number.isSafeInteger(id) && id > 0) || !safe(row.path)
        || (row.evidence_role !== undefined && row.evidence_role !== 'comparison-baseline')) throw new Error('Invalid artifact member selector');
    if (row.evidence_role === 'comparison-baseline') {
      if (Object.keys(row).sort().join(',') !== 'artifact_id,compared_paths,evidence_role,kind,path,run_id'
          || !Array.isArray(row.compared_paths) || !row.compared_paths.length || row.compared_paths.length > 8
          || !row.compared_paths.every(safe) || new Set(row.compared_paths).size !== row.compared_paths.length) throw new Error('Invalid comparison baseline paths');
    } else if (row.compared_paths !== undefined) throw new Error('Compared paths require comparison baseline role');
  }
  if (new Set(artifacts.filter(row => row.evidence_role === 'comparison-baseline')
      .flatMap(row => row.compared_paths)).size > 8) throw new Error('Comparison baseline source count bound');
  return rows;
}
function selectors(value) {
  return new Set(validatedSelectors(value).filter(row => row.kind === 'git_blob').map(row => row.path));
}
async function collectGzipAssets({github, owner, repo, evaluatedSha, diffText, files, directory, retain, material, core}) {
  const required = selectors(material);
  const candidates = files.filter(f => f.binary && evidencePath(f.toPath));
  for (const source of required) if (!candidates.some(file => file.toPath === source)) throw new Error('Required git_blob is not a supported changed evidence asset');
  if (!candidates.length) return [];
  if (!/^[a-f0-9]{40}$/.test(evaluatedSha || '')) throw new Error('Gzip asset immutable merge identity unavailable');
  if (new Set(candidates.map(f => f.toPath)).size !== candidates.length) throw new Error('Gzip asset inventory ambiguous');
  if (candidates.length <= 80) github = await ensureRateLimitWrapped({github,core,env:process.env});
  const trees = new Map();
  let rootPromise;
  // One collection pass shares immutable metadata reads, including rejection.
  // A later independent collection creates fresh promises and may retry normally.
  function rootTree() {
    if (!rootPromise) rootPromise = Promise.resolve().then(async () => {
      const commit = (await github.rest.git.getCommit({owner,repo,commit_sha:evaluatedSha})).data;
      if (commit?.sha !== evaluatedSha) throw new Error('Git commit identity mismatch');
      const root = commit.tree?.sha;
      if (!/^[a-f0-9]{40}$/.test(root || '')) throw new Error('Git commit tree unavailable');
      return root;
    });
    return rootPromise;
  }
  function tree(sha) {
    if (!trees.has(sha)) trees.set(sha, Promise.resolve().then(async () => {
      const value = (await github.rest.git.getTree({owner,repo,tree_sha:sha})).data;
      if (!value || value.sha !== sha || value.truncated || !Array.isArray(value.tree)) throw new Error('Git tree unavailable or truncated');
      return value.tree;
    }));
    return trees.get(sha);
  }
  let rawTotal = 0, textTotal = 0;
  const result = [];
  for (const file of candidates) {
    const record = {schema:SCHEMA, codec:CODEC, source:file.toPath, input_id:`gzip_asset:${hash(Buffer.from(file.toPath,'utf8'))}`, repository:`${owner}/${repo}`.toLowerCase(),
      evaluated_sha:evaluatedSha, change_kind:file.status, necessity:required.has(file.toPath) ? 'required' : 'unknown',
      patch_sha256:hash(Buffer.from(diffText.slice(file.start,file.end).replace(/\n$/,''),'utf8')), status:'unavailable'};
    try {
      if (candidates.length > 80) throw new Error('gzip_asset_inventory_count_bound');
      // V1 must not claim a new-side-only view covers modified/deleted/renamed assets.
      if (file.status !== 'added') throw new Error('gzip_asset_change_sides_unsupported');
      let sha = await rootTree();
      const parts = file.toPath.split('/');
      let entry;
      for (let i=0;i<parts.length;i++) {
        const entries = (await tree(sha)).filter(row => row.path === parts[i]);
        if (entries.length !== 1) throw new Error('Git path absent or ambiguous');
        entry = entries[0];
        if (i < parts.length-1 && (entry.type !== 'tree' || entry.mode !== '040000')) throw new Error('Git path traverses non-tree');
        sha = entry.sha;
      }
      if (!Number.isSafeInteger(entry.size) || entry.size < 1 || entry.size > MAX_RAW || entry.type !== 'blob' || entry.mode !== '100644' || !/^[a-f0-9]{40}$/.test(sha)) throw new Error('Git asset is not a regular blob');
      const blob = (await github.rest.git.getBlob({owner,repo,file_sha:sha})).data;
      if (blob?.sha !== sha || blob.encoding !== 'base64' || !Number.isSafeInteger(blob.size) || blob.size > MAX_RAW || blob.size < 1
          || typeof blob.content !== 'string') throw new Error('Git blob metadata invalid');
      const encoded = blob.content.replace(/\n/g,'');
      if (encoded.length > Math.ceil(MAX_RAW/3)*4) throw new Error('Git blob encoded byte bound');
      const raw = Buffer.from(encoded,'base64');
      if (raw.toString('base64') !== encoded || raw.length !== blob.size
          || createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${raw.length}\0`),raw])).digest('hex') !== sha) throw new Error('Git blob content identity mismatch');
      rawTotal += raw.length;
      if (rawTotal > 32*1024*1024) throw new Error('Gzip cumulative raw bound');
      retain(directory,hash(raw),'gz',raw);
      Object.assign(record,{raw_status:'captured',mode:entry.mode,git_blob_sha:sha,raw_sha256:hash(raw),raw_bytes:raw.length});
      const decoded = JSON.parse(execFileSync('python3',[path.resolve(__dirname,'../../tools/verifier_gzip_assets.py')],
        {input:raw,maxBuffer:Math.ceil(MAX_TEXT*4/3)+4096,timeout:15000,encoding:'utf8',stdio:['pipe','pipe','pipe']}));
      const text = Buffer.from(decoded.text_base64,'base64');
      textTotal += text.length;
      if (textTotal > 64*1024*1024 || decoded.codec !== CODEC || decoded.raw_sha256 !== hash(raw)
          || decoded.raw_bytes !== raw.length || decoded.text_sha256 !== hash(text) || decoded.text_bytes !== text.length) throw new Error('Gzip derived view identity mismatch');
      retain(directory,hash(text),'txt',text);
      Object.assign(record,{status:'captured',mode:entry.mode,git_blob_sha:sha,raw_sha256:hash(raw),raw_bytes:raw.length,
        text_sha256:hash(text),text_bytes:text.length});
    } catch (error) { record.reason=String(error.message || error); }
    result.push(record);
  }
  for (const source of required) if (!result.some(row => row.source === source)) throw new Error('Required git_blob is not a supported changed evidence asset');
  return result;
}
module.exports = {collectGzipAssets,evidencePath,selectors,validatedSelectors};
