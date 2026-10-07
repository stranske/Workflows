'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const cp = require('node:child_process');
const Module = require('node:module');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const directory = path.join(root, 'templates/consumer-repo/.github/scripts');
function server() {
  const inventories = new Map(); const history = new Map([[1, new Map()]]); const blobs = new Map();
  let version = 1; let reads = 0; let writes = 0;
  const sha = (n) => n.toString(16).padStart(40, '0');
  const indexSha = sha(400000);
  const entries = Array.from({length:1001},(_,i) => {
    const owner = `owner/repo:${i+1}:1`; const blobSha = sha(i+500000);
    const value = {version:1,repository:'owner/repo',owner_attempt:owner,pr_number:9000,generation:'a'.repeat(64),receipt:{id:'b'.repeat(64),claim_digest:'c'.repeat(64),owner_attempt:owner,head_sha:'d'.repeat(40),provider:'codex',consumed_at:'2026-10-01T00:00:00.000Z'}};
    blobs.set(blobSha,{sha:blobSha,encoding:'base64',content:Buffer.from(JSON.stringify(value)).toString('base64')});
    return {path:crypto.createHash('sha256').update(owner).digest('hex')+'.json',type:'blob',sha:blobSha};
  });
  const request = async(method,url,body) => {
    if (url.includes('/contents/.github/keepalive-authority-presence/')) {
      const key = url.split('keepalive-authority-presence/')[1].split('?')[0];
      if(method==='PUT') { assert.equal(body.sha,undefined); if(inventories.has(key)) throw Object.assign(new Error('existing'),{status:422}); inventories.set(key,body.content); writes++; version++; history.set(version,new Map(inventories)); return {}; }
      const ref = url.split('?ref=')[1]; const snapshot = ref==='keepalive-authority-state' ? inventories : history.get(parseInt(ref,16)-100000);
      if(!snapshot || !snapshot.has(key)) throw Object.assign(new Error('missing'),{status:404});
      return {sha:sha(600000),encoding:'base64',content:snapshot.get(key)};
    }
    assert.equal(method,'GET');
    if(url.includes('/git/ref/'))return {object:{type:'commit',sha:sha(100000+version)}};
    if(url.includes('/git/commits/'))return {tree:{sha:sha(200000+parseInt(url.split('/').pop(),16)-100000)}};
    if(url.includes('/git/trees/')) {
      const n=parseInt(url.split('/').pop(),16);
      if(n>200000 && n<300000)return {truncated:false,tree:[{path:'.github',type:'tree',sha:sha(n+100000)}]};
      if(n>300000 && n<400000)return {truncated:false,tree:[{path:'keepalive-authority-attempts',type:'tree',sha:indexSha}]};
      if(n===400000)return {truncated:false,tree:entries};
    }
    const blob=blobs.get(url.split('/git/blobs/')[1]); assert.ok(blob,url); reads++; return blob;
  };
  return {request,stats:()=>({blob_reads:reads,inventory_writes:writes})};
}
(async()=>{
 const oldFile=path.join(directory,'keepalive_authority_state.js'); const oldModule=new Module(oldFile);oldModule.filename=oldFile;oldModule.paths=Module._nodeModulePaths(directory);
 oldModule._compile(cp.execFileSync('git',['-C',root,'show','6102cc666ac99371d2196f038969ca481b314f20:templates/consumer-repo/.github/scripts/keepalive_authority_state.js'],{encoding:'utf8'}),oldFile);
 const before=server();for(const pr of [42,43,44])assert.equal(await oldModule.exports.hasAttemptIndexesForPr(before.request,'owner/repo',pr),false);assert.equal(before.stats().blob_reads,3003);
 const after=server();
 for(const pr of [42,43,44]) {
  for(const filename of ['keepalive_authority_state.js','keepalive_reporter_applicability.js'])delete require.cache[require.resolve(path.join(directory,filename))];
  const {replayReporterAuthority}=require(path.join(directory,'keepalive_reporter_applicability.js'));
  assert.deepEqual(await replayReporterAuthority({github:{},context:{repo:{owner:'owner',repo:'repo'}},prNumber:pr,readAuthority:async()=>null,makeRequest:()=>after.request}),{prNumber:pr,results:[]});
 }
 assert.equal(after.stats().blob_reads,1001);assert.equal(after.stats().inventory_writes,1);
 const {replayReporterAuthority}=require(path.join(directory,'keepalive_reporter_applicability.js'));
 await assert.rejects(replayReporterAuthority({github:{},context:{repo:{owner:'owner',repo:'repo'}},prNumber:9000,readAuthority:async()=>null,makeRequest:()=>after.request}),/ledger is missing/);
 assert.equal(after.stats().blob_reads,1001);
 console.log(JSON.stringify({before:before.stats(),after:after.stats(),warm_blob_reads:0,negative_prs:3,positive_missing_ledger:'rejected',consumer_default_helper:'actual default helper across module reloads',live_api_load:0},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
