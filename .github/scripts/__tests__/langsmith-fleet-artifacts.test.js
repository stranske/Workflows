const { test } = require('node:test');
const assert = require('node:assert/strict');
const { findFleetArtifact } = require('../langsmith-fleet-artifacts.js');
const name = 'langsmith-fleet.ndjson';
const item = (id, extra={}) => ({id, name, expired:false, created_at:'2026-10-11', ...extra});
function fixture(list, run=async()=>({data:{path:'trusted.yml'}})) {
  const calls=[], warnings=[];
  return {calls,warnings,options:{owner:'o',repo:'r',name,
    trustedWorkflowPaths:new Set(['trusted.yml']),core:{warning:s=>warnings.push(s)},
    withRetry:fn=>fn(),github:{rest:{actions:{listArtifactsForRepo:async p=>{calls.push(p);return list(p);},getWorkflowRun:run}}}}};
}
test('large repository uses server-side exact name and never scans unrelated records', async()=>{
 const f=fixture(async p=>{assert.equal(p.name,name);return {data:{total_count:1,artifacts:[item(1)]}};});
 assert.equal((await findFleetArtifact(f.options)).id,1);assert.equal(f.calls.length,1);
});
test('exact artifact wins even when a newer suffix exists',async()=>{
 const f=fixture(async()=>({data:{total_count:1,artifacts:[item(1)]}}));
 assert.equal((await findFleetArtifact(f.options)).id,1);
});
test('expired exact artifacts do not hide a trusted suffix; untrusted and absent runs skipped',async()=>{
 const f=fixture(async p=>({data:{total_count:4,artifacts:p.name?[item(1,{expired:true})]:[
 item(2,{name:'bad-'+name,workflow_run:{id:2}}),item(3,{name:'norun-'+name}),
 item(4,{name:'good-'+name,workflow_run:{id:4}}),item(5,{name:'expired-'+name,expired:true})]}}),
 async p=>({data:{path:p.run_id===4?'trusted.yml':'untrusted.yml'}}));
 assert.equal((await findFleetArtifact(f.options)).id,4);
});
test('500 reduces page size without retrying the identical request',async()=>{
 const f=fixture(async p=>{if(p.per_page>1)throw Object.assign(new Error('500'),{status:500});
 return {data:{total_count:1,artifacts:[item(1)]}};});
 assert.equal((await findFleetArtifact(f.options)).id,1);assert.deepEqual(f.calls.map(p=>p.per_page),[30,10,1]);
});
test('reduced later page retains offset and does not skip records',async()=>{
 const f=fixture(async p=>{if(p.page===1)return {data:{total_count:31,artifacts:Array.from({length:30},()=>item(0,{expired:true}))}};
 if(p.per_page===30)throw Object.assign(new Error('500'),{status:500});
 assert.equal(p.page,4);return {data:{total_count:31,artifacts:[item(9)]}};});
 assert.equal((await findFleetArtifact(f.options)).id,9);
});
test('authorization errors fail immediately',async()=>{
 const f=fixture(async()=>{throw Object.assign(new Error('forbidden'),{status:403});});
 await assert.rejects(findFleetArtifact(f.options),/forbidden/);assert.equal(f.calls.length,1);
});
test('listing budget exhaustion is UNKNOWN, not a missing-artifact success',async()=>{
 const f=fixture(async()=>({data:{total_count:31260,artifacts:Array.from({length:30},()=>item(0,{expired:true}))}}));
 await assert.rejects(findFleetArtifact({...f.options,maxRequests:2}),/UNKNOWN/);assert.equal(f.calls.length,2);
});
test('no artifacts returns null after two bounded empty listings',async()=>{
 const f=fixture(async()=>({data:{total_count:0,artifacts:[]}}));
 assert.equal(await findFleetArtifact(f.options),null);assert.equal(f.calls.length,2);
});

test('exact discovery pages only matching names and stops at the first usable page', async () => {
  const inventory = Array.from({ length: 31260 }, (_, id) =>
    item(id, { name: `unrelated-${id}` }));
  inventory.splice(0, 33, ...Array.from({ length: 33 }, (_, id) =>
    item(id, { expired: id < 31, created_at: `2026-10-${id === 32 ? '09' : '10'}` })));
  const f = fixture(async params => {
    assert.equal(params.name, name, 'exact evidence must not trigger inventory discovery');
    const matches = inventory.filter(artifact => artifact.name === params.name);
    const offset = (params.page - 1) * params.per_page;
    return { data: {
      total_count: matches.length,
      artifacts: matches.slice(offset, offset + params.per_page),
    } };
  });

  assert.equal((await findFleetArtifact(f.options)).id, 31);
  assert.deepEqual(f.calls.map(params => [params.name, params.per_page, params.page]), [
    [name, 30, 1], [name, 30, 2],
  ]);
});

test('legacy discovery stops in a large inventory after a trusted ref-qualified producer', async () => {
  const inventory = Array.from({ length: 31260 }, (_, id) =>
    item(id, { name: `unrelated-${id}` }));
  inventory[0] = item(0, { expired: true });
  inventory[61] = item(61, { name: `untrusted-${name}`, workflow_run: { id: 1 } });
  inventory[62] = item(62, { name: `also-untrusted-${name}`, workflow_run: { id: 1 } });
  inventory[63] = item(63, { name: `expired-${name}`, expired: true, workflow_run: { id: 2 } });
  inventory[64] = item(64, { name: `trusted-${name}`, workflow_run: { id: 3 } });
  const runCalls = [];
  const f = fixture(async params => {
    const matches = params.name
      ? inventory.filter(artifact => artifact.name === params.name) : inventory;
    const offset = (params.page - 1) * params.per_page;
    return { data: {
      total_count: matches.length,
      artifacts: matches.slice(offset, offset + params.per_page),
    } };
  }, async params => {
    runCalls.push(params.run_id);
    return { data: { path: params.run_id === 3
      ? 'trusted.yml@refs/heads/main' : 'untrusted.yml@refs/heads/main' } };
  });

  assert.equal((await findFleetArtifact(f.options)).id, 64);
  assert.deepEqual(f.calls.map(params => [params.name, params.per_page, params.page]), [
    [name, 30, 1], [undefined, 30, 1], [undefined, 30, 2], [undefined, 30, 3],
  ]);
  assert.deepEqual(runCalls, [1, 3], 'skip expired evidence and cache producer checks');
});

test('ref-qualified workflow paths still require an exact trusted filename', async () => {
  for (const path of ['untrusted.yml@main', 'prefix/trusted.yml@main', 'trusted.yml.bak@main']) {
    const f = fixture(async params => ({ data: {
      total_count: params.name ? 0 : 1,
      artifacts: params.name ? [] : [item(1, {
        name: `legacy-${name}`, workflow_run: { id: 1 },
      })],
    } }), async () => ({ data: { path } }));
    assert.equal(await findFleetArtifact(f.options), null, path);
  }
});

for (const succeeds of [false, true]) {
  test(`workflow retries count actual requests (success=${succeeds})`, async () => {
    let runCalls = 0;
    const f = fixture(async p => ({data:{total_count:p.name?0:1,
      artifacts:p.name?[]:[item(1,{name:'legacy-'+name,workflow_run:{id:1}})]}}), async () => {
      runCalls += 1;
      if (!succeeds || runCalls < 2) throw Object.assign(new Error('503'),{status:503});
      return {data:{path:'trusted.yml'}};
    });
    f.options.withRetry = async (fn, {maxRetries}) => {
      for (let attempt=0;;attempt++) {
        try { return await fn(); } catch (error) {
          if (attempt >= maxRetries || error.status !== 503) throw error;
        }
      }
    };
    if (succeeds) assert.equal((await findFleetArtifact({...f.options,maxRequests:4})).id,1);
    else await assert.rejects(findFleetArtifact({...f.options,maxRequests:3}),/UNKNOWN|503/);
    assert.ok(f.calls.length + runCalls <= (succeeds?4:3), 'actual network attempts exceed cap');
  });
}
