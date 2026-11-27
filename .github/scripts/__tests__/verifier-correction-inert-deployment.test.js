'use strict';

const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),{createHash}=require('crypto');
const {gunzipSync}=require('node:zlib');
const root=path.resolve(__dirname,'../../..');
const read=file=>fs.readFileSync(path.join(root,file),'utf8');
const lineage=JSON.parse(read('docs/evidence/verifier-correction-deployment-lineage.json'));
const surfaces=['.github/workflows/agents-verify-to-new-pr.yml','templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml'];

// Both predecessor surfaces had these exact job bytes at 7c5ac26448ed6149ba984584ed1db821ce049371.
const predecessorJob=gunzipSync(fs.readFileSync(path.join(root,
  'tests/fixtures/verifier_correction/ordinary-followup-predecessor.yml.gz'))).toString('utf8');
const successorSha256='625e3dc9f5eac0334439b4838a12e173f3962662ff6408cc581a0df903745b31';

for(const surface of surfaces) {
 test(`${surface}: authored workflow has only the ordinary and read-only collection jobs`,()=>{
  const source=read(surface);
  const jobNames=[...source.split('\njobs:\n')[1].matchAll(/^  ([\w-]+):/gm)].map(match=>match[1]);
  assert.deepEqual(jobNames,['create-new-pr','collect-correction']);
 });
 test(`${surface}: ordinary merged-PR label lane preserves exact pre-interface job bytes`,()=>{
  assert.equal(createHash('sha256').update(predecessorJob).digest('hex'),lineage.legacy_job_sha256[surface]);
  assert.doesNotMatch(predecessorJob,/guardLegacyCorrection|correction_guard|resolveCodingScope/);
 });
 test(`${surface}: ordinary merged-PR label lane matches the exact continuation identity successor`,()=>{
  const source=read(surface),job=source.slice(source.indexOf('  create-new-pr:\n'),source.indexOf('\n  collect-correction:\n')).trimEnd();
  assert.equal(createHash('sha256').update(job).digest('hex'),successorSha256);
  assert.doesNotMatch(job,/guardLegacyCorrection|correction_guard|resolveCodingScope/);
  assert.equal(source,read(surfaces[1-surfaces.indexOf(surface)]));
 });
 test(`${surface}: collection retains read-only permissions and cannot receive an effect activation callback`,()=>{
  const job=read(surface).split('\n  collect-correction:\n')[1];
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
