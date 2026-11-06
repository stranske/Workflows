'use strict';

const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),{createHash}=require('crypto');
const root=path.resolve(__dirname,'../../..');
const read=file=>fs.readFileSync(path.join(root,file),'utf8');
const lineage=JSON.parse(read('docs/evidence/verifier-correction-inert-split/deployment-lineage.json'));
const surfaces=['.github/workflows/agents-verify-to-new-pr.yml','templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml'];

for(const surface of surfaces) {
 test(`${surface}: typed effect job is unconditionally source-disabled independent of admitted outputs`,()=>{
  const source=read(surface),header=source.split('\n  apply-correction:\n')[1].split('    steps:\n')[0];
  const condition=header.split('    if: >-\n')[1].split('    runs-on:')[0].trim();
  assert.match(condition,/^false\s*&&/);
  const poisoned=new Proxy({}, {get(){throw Error('disabled condition read caller-controlled activation');}});
  assert.equal(new Function('github','needs',`return (${condition});`)(poisoned,poisoned),false);
  assert.doesNotMatch(condition,/vars\.|secrets\.|inputs\./);
 });
 test(`${surface}: ordinary merged-PR label lane preserves exact pre-interface job bytes`,()=>{
  const source=read(surface),job=source.slice(source.indexOf('  create-new-pr:\n'),source.indexOf('\n  collect-correction:\n')).trimEnd();
  assert.equal(createHash('sha256').update(job).digest('hex'),lineage.legacy_job_sha256[surface]);
  assert.doesNotMatch(job,/guardLegacyCorrection|correction_guard|resolveCodingScope/);
 });
 test(`${surface}: collection retains read-only permissions and cannot receive an effect activation callback`,()=>{
  const job=read(surface).split('\n  collect-correction:\n')[1].split('\n  apply-correction:\n')[0];
  const header=job.split('    steps:\n')[0];
  assert.doesNotMatch(header,/: write/);
  assert.match(header,/contents: read/);assert.match(header,/actions: read/);
  assert.doesNotMatch(job,/authenticateDecision\s*:|createWorkflowDispatch\s*\(|rest\.issues\.create\s*\(/);
 });
}
test('new-producer deployment proof is scoped to the introduced typed interface, not ordinary historical ownership',()=>{
 assert.equal(lineage.pr.merged,false);assert.equal(lineage.pr.head,'fdc2b85c5c63525bfa7127a905eb3360a7c00a4b');
 assert.equal(lineage.repositories.length,17);
 assert.ok(lineage.repositories.every(row=>row.workflow_blob==='50ca772edbf5150f226d5db4f39333324d43b6b9'
  && row.typed_markers.length===0 && row.dispatch_total===0));
 assert.ok(lineage.introduction.every(row=>row.ancestor_of_canonical_main===false));
 assert.ok(lineage.authored_producer_versions.filter(row=>row.calls_collect_submission).length>0);
 assert.ok(lineage.authored_producer_versions.every(row=>row.passes_authenticate_decision===false));
});
