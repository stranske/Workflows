'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {gzipSync}=require('zlib'),{createHash}=require('crypto');
const {collectGzipAssets,selectors}=require('../../.github/scripts/verifier_gzip_assets');
const {parseDiffFiles,retainCaptureBytes}=require('../../.github/scripts/agents_verifier_context');
const {requiredEvidence,buildVerificationEvent}=require('../../.github/scripts/verification_event');
const sha=b=>createHash('sha256').update(b).digest('hex');
function fixture(dir,{status='added',raw=gzipSync(Buffer.from('proof π\r\n')),paths=['docs/verification/é.log.gz']}={}) {
 const blob=createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${raw.length}\0`),raw])).digest('hex');
 const roots=['a','b','c'].map(x=>x.repeat(40));
 const diffText=paths.map(p=>`diff --git a/${p} b/${p}\n${status==='added'?'new file mode 100644\n':''}index 0000000..1234567\nBinary files /dev/null and b/${p} differ\n`).join('');
 let calls=0;
 const github={rest:{git:{getCommit:async()=>({data:{sha:'d'.repeat(40),tree:{sha:roots[0]}}}),getTree:async({tree_sha})=>({data:{sha:tree_sha,truncated:false,tree:tree_sha===roots[0]?[{path:'docs',sha:roots[1],type:'tree',mode:'040000'}]:tree_sha===roots[1]?[{path:'verification',sha:roots[2],type:'tree',mode:'040000'}]:paths.map(p=>({path:p.split('/').at(-1),type:'blob',mode:'100644',size:raw.length,sha:blob}))}}),getBlob:async({file_sha})=>{calls++;assert.equal(file_sha,blob);return {data:{sha:blob,size:raw.length,encoding:'base64',content:raw.toString('base64')}};}}}};
 return {args:{github,owner:'a',repo:'b',evaluatedSha:'d'.repeat(40),diffText,files:parseDiffFiles(diffText,99999).fileSummaries,directory:dir,retain:retainCaptureBytes},calls:()=>calls,blob,raw};
}
function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'gzip-contract-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;}
test('actual collector invokes bounded decoder, retains exact raw/Unicode bytes and requirements selection',async t=>{
 const dir=temp(t),f=fixture(dir);
 const rows=await collectGzipAssets({...f.args,material:JSON.stringify([{kind:'git_blob',path:'docs/verification/é.log.gz'}])});
 assert.equal(rows[0].status,'captured');assert.equal(rows[0].necessity,'required');
 assert.deepEqual(fs.readFileSync(path.join(dir,rows[0].raw_sha256+'.gz')),f.raw);
 assert.equal(fs.readFileSync(path.join(dir,rows[0].text_sha256+'.txt'),'utf8'),'proof π\r\n');
 assert.equal(rows[0].git_blob_sha,f.blob);
 assert.deepEqual(requiredEvidence([{kind:'git_blob',path:rows[0].source}],{gzip_assets:rows})[0].raw_sha256,sha(f.raw));
 assert.throws(()=>requiredEvidence([{kind:'git_blob',path:rows[0].source,ref:'attacker'}],{gzip_assets:rows}));
});
test('same bytes at distinct paths remain distinct assets; no filename-based optional claim',async t=>{
 const f=fixture(temp(t),{paths:['docs/verification/a.log.gz','docs/verification/b.log.gz']});
 const rows=await collectGzipAssets(f.args);assert.equal(rows.length,2);assert.ok(rows.every(r=>r.status==='captured'&&r.necessity==='unknown'));
 assert.equal(rows[0].raw_sha256,rows[1].raw_sha256);
});
test('all non-added sides explicitly unsupported, not new-side-only admitted',async t=>{
 const f=fixture(temp(t),{status:'modified'});const rows=await collectGzipAssets(f.args);
 assert.equal(rows[0].status,'unavailable');assert.match(rows[0].reason,/sides_unsupported/);assert.equal(f.calls(),0);
});
test('CRC failure stays typed per-item failure and cannot satisfy required selector',async t=>{
 const f=fixture(temp(t),{raw:Buffer.from('not gzip')});const rows=await collectGzipAssets(f.args);
 assert.equal(rows[0].status,'unavailable');assert.throws(()=>requiredEvidence([{kind:'git_blob',path:rows[0].source}],{gzip_assets:rows}),/unavailable/);
});
test('truncated trees and identity mismatch are refused before derivation',async t=>{
 const f=fixture(temp(t));f.args.github.rest.git.getTree=async()=>({data:{truncated:true}});
 const rows=await collectGzipAssets(f.args);assert.equal(rows[0].status,'unavailable');assert.equal(f.calls(),0);
});
test('selectors never accept repository/ref/hash authority or traversal',()=>{
 for(const row of [{kind:'git_blob',path:'docs/verification/a.log.gz',repo:'evil/x'}, {kind:'git_blob',path:'docs/verification/../a.log.gz'}, {kind:'git_blob',path:'src/main.bin'}]) assert.throws(()=>selectors([row]));
});

test('wrong commit, blob hash and duplicate tree identities refuse capture',async t=>{
 for(const kind of ['commit','blob','duplicate','symlink']) {
  const f=fixture(temp(t));
  if(kind==='commit') f.args.github.rest.git.getCommit=async()=>({data:{sha:'f'.repeat(40),tree:{sha:'a'.repeat(40)}}});
  if(kind==='blob') f.args.github.rest.git.getBlob=async()=>({data:{sha:f.blob,size:f.raw.length,encoding:'base64',content:Buffer.from('tampered').toString('base64')}});
  if(kind==='duplicate'||kind==='symlink') {
   const previous=f.args.github.rest.git.getTree;
   f.args.github.rest.git.getTree=async args=>{const response=await previous(args);if(args.tree_sha==='c'.repeat(40)) {
    if(kind==='duplicate') response.data.tree.push(response.data.tree[0]);else response.data.tree[0].mode='120000';
   } return response;};
  }
  assert.equal((await collectGzipAssets(f.args))[0].status,'unavailable',kind);
 }
});
test('a failed decoder still retains the authenticated compressed original',async t=>{
 const dir=temp(t),f=fixture(dir,{raw:Buffer.from('not gzip')});
 const [row]=await collectGzipAssets(f.args);
 assert.equal(row.status,'unavailable');assert.equal(row.raw_status,'captured');
 assert.deepEqual(fs.readFileSync(path.join(dir,row.raw_sha256+'.gz')),f.raw);
});

test('old non-blob selector bound is unchanged and shared with fail-fast collector validation',async t=>{
 const comments=Array.from({length:21},(_,i)=>({kind:'comment',url:`https://github.com/a/b/pull/1#issuecomment-${i+1}`}));
 assert.throws(()=>selectors(comments),/count bound/);
 assert.throws(()=>requiredEvidence(comments,{}),/count bound/);
 const assets=Array.from({length:80},(_,i)=>({kind:'git_blob',path:`docs/verification/${i}.log.gz`}));
 assert.equal(selectors([...assets,...comments.slice(0,20)]).size,80);
 assert.throws(()=>selectors([...assets,{kind:'git_blob',path:'docs/verification/81.log.gz'}]),/count bound/);
 const f=fixture(temp(t));await assert.rejects(collectGzipAssets({...f.args,material:comments}),/count bound/);assert.equal(f.calls(),0);
});
test('real Git C-quoted Unicode path traverses actual parser, collector and Python byte join',async t=>{
 const {spawnSync,execFileSync}=require('child_process');
 const dir=temp(t),name='docs/verification/é.log.gz',f=fixture(dir);
 fs.mkdirSync(path.join(dir,'docs/verification'),{recursive:true});fs.writeFileSync(path.join(dir,name),f.raw);
 const git=spawnSync('git',['-c','core.quotePath=true','diff','--no-index','--','/dev/null',name],{cwd:dir,encoding:'utf8'});
 assert.equal(git.status,1);assert.match(git.stdout,/\\303\\251/);
 const files=parseDiffFiles(git.stdout,99999).fileSummaries;assert.equal(files[0].toPath,name);
 const rows=await collectGzipAssets({...f.args,diffText:git.stdout,files});assert.equal(rows[0].status,'captured');
 const coverage={gzip_asset_binding:{repository:'a/b',evaluated_sha:'d'.repeat(40)},gzip_asset_sources:rows};
 const input={coverage,patch:git.stdout,directory:dir};
 const code='import json,sys;from pathlib import Path;from tools.verifier_gzip_assets import verified_assets;x=json.load(sys.stdin);r=verified_assets(x["coverage"],Path(x["directory"]),x["patch"].encode());assert len(r)==1;assert next(iter(r.values()))["verified"]';
 execFileSync('python3',['-c',code],{cwd:path.resolve(__dirname,'../..'),input:JSON.stringify(input),env:{...process.env,PYTHONPATH:'.'}});
});

test('malformed selector types remain invalid while empty input preserves legacy behavior',()=>{
 for(const value of [false,0,{},'null','false']) assert.throws(()=>selectors(value));
 assert.equal(selectors('   ').size,0);assert.equal(selectors(undefined).size,0);
});

test('real Git C1 and Unicode separator names keep labels escaped and native coverage complete',async t=>{
 const {spawnSync,execFileSync}=require('child_process');
 for(const character of ['\u0085','\u2028','\u2029']) {
  const dir=temp(t),name=`docs/verification/a${character}.log.gz`,f=fixture(dir,{paths:[name]});
  fs.mkdirSync(path.join(dir,'docs/verification'),{recursive:true});fs.writeFileSync(path.join(dir,name),f.raw);
  const git=spawnSync('git',['-c','core.quotePath=true','diff','--no-index','--','/dev/null',name],{cwd:dir,encoding:'utf8'});
  assert.equal(git.status,1);
  const files=parseDiffFiles(git.stdout,99999).fileSummaries;assert.equal(files[0].toPath,name);
  const rows=await collectGzipAssets({...f.args,diffText:git.stdout,files});assert.equal(rows[0].status,'captured');
  const input={coverage:{gzip_asset_binding:{repository:'a/b',evaluated_sha:'d'.repeat(40)},gzip_asset_sources:rows},patch:git.stdout,directory:dir,name};
  const code=`import json,sys,os
from pathlib import Path
from tools.verifier_gzip_assets import review_assets
from scripts.langchain.pr_verifier import build_prompt_inputs
x=json.load(sys.stdin);os.environ['VERIFIER_EVIDENCE_CAPTURE_DIR']=x['directory']
c=x['coverage'];c.update(schema='verifier-context-source-coverage/v1',stage='generated-context',changed_code_sources=[dict(source=x['name'],status='unavailable')],acceptance_sources=[],acceptance_evidence_sources=[])
tick=chr(96)
context=chr(10).join(['- Repository: a/b','- Target commit: '+tick+'d'*40+tick,'','## Context source coverage','',tick*3+'json',json.dumps(c),tick*3,'','## CI Information',''])
views=review_assets(c,x['patch'].encode(),context=context)
label=next(iter(views.values())).splitlines()[1]
assert json.dumps(x['name'],ensure_ascii=True) in label
assert x['name'] not in label
coverage=build_prompt_inputs(context,x['patch'],lossless=True).coverage
assert coverage.files[0].status=='complete',coverage.reasons
`;
  execFileSync('python3',['-c',code],{cwd:path.resolve(__dirname,'../..'),input:JSON.stringify(input),env:{...process.env,PYTHONPATH:'.'}});
 }
});

test('empty asset collection returns before client initialization, and wrapped clients remain usable',async t=>{
 assert.deepEqual(await collectGzipAssets({files:[],material:[{kind:'comment',url:'https://github.com/a/b/pull/1#issuecomment-1'}]}),[]);
 const f=fixture(temp(t));f.args.github.__rateLimitWrapped=true;
 const [row]=await collectGzipAssets(f.args);assert.equal(row.status,'captured');assert.equal(f.calls(),1);
});

test('shared immutable commit/tree failures are observed once per collection, with fresh-call retry',async t=>{
 for(const endpoint of ['getCommit','getTree']) {
  const f=fixture(temp(t),{paths:['docs/verification/a.log.gz','docs/verification/b.log.gz','docs/verification/c.log.gz']});
  f.args.github.__rateLimitWrapped=true;
  let calls=0,fail=true;const original=f.args.github.rest.git[endpoint];
  f.args.github.rest.git[endpoint]=async args=>{calls++;if(fail)throw new Error('shared immutable metadata temporarily unavailable');return original(args);};
  const failed=await collectGzipAssets(f.args);
  assert.equal(calls,1,endpoint);assert.equal(failed.length,3);
  assert.ok(failed.every(row=>row.status==='unavailable'&&/shared immutable metadata/.test(row.reason)));
  assert.equal(f.calls(),0);
  fail=false;
  const recovered=await collectGzipAssets(f.args);
  assert.ok(recovered.every(row=>row.status==='captured'));
  assert.equal(calls,endpoint==='getCommit'?2:4,endpoint);
 }
});


test('asset count bound yields an explicit unavailable record for every path without reads',async t=>{
 const paths=Array.from({length:81},(_,i)=>`docs/verification/${i}.log.gz`);
 const f=fixture(temp(t),{paths});delete f.args.github;
 const rows=await collectGzipAssets(f.args);
 assert.equal(rows.length,81);assert.deepEqual(rows.map(row=>row.source),paths);
 assert.ok(rows.every(row=>row.status==='unavailable'&&row.reason==='gzip_asset_inventory_count_bound'));
 assert.equal(f.calls(),0);
 await assert.rejects(collectGzipAssets({...f.args,files:[...f.args.files,f.args.files[0]]}),/ambiguous/);
});
