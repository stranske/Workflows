'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {digest}=require('../verification_event');
const {seedForRequest,effectKey,sourceScopeDigest}=require('../verifier_correction_effects');
const {validateCorrectionDecision}=require('../verifier_correction_decision');
function fixture() {
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/no-incumbent-request.json')),seed=seedForRequest(request),bundle={seeds:[seed]};
 const profile={id:'inert-qualified-profile',role:'closer_interpret',qualification_ref:'inert:qualified-production-source',qualification_sha256:'e'.repeat(64)};
 const decision={schema:'closer-correction-decision/v1',seed_effect_key:effectKey(seed),source_scope_digest:sourceScopeDigest(seed),request_sha256:request.request_sha256,
 findings:[{...seed.finding,classification:'ordinary_substantive',required_tests_sha256:digest(request.required_tests)}],profile,retained_packet_ref:'inert:prepare-packet',decision_evidence_ref:'inert:bounded-source-decision'};
 const qualification={status:'qualified',role:'closer_interpret',profile_id:profile.id,qualification_ref:profile.qualification_ref,qualification_sha256:profile.qualification_sha256};
 return {request,seed,bundle,decision,qualification};
}
test('explicit independently qualified synthetic ordinary classification binds exact source and requirements',()=>{
 const f=fixture(),result=validateCorrectionDecision(f);assert.equal(result.status,'admitted');assert.equal(result.act_authorized,false);assert.equal(result.source_closure_authorized,false);
});
test('production-zero/missing qualification, security, authority conflict and uncertainty never fall through',()=>{
 for(const change of [f=>f.qualification=null,f=>f.qualification.status='unqualified',f=>f.decision.findings[0].classification='security',f=>f.decision.findings[0].classification='authority_conflict',f=>f.decision.findings[0].classification='unknown',f=>f.decision.profile.qualification_sha256='a'.repeat(64)]) {
  const f=fixture();change(f);assert.equal(validateCorrectionDecision(f).status,'owned_unknown');
 }
});
test('missing raw findings and changed test decisions remain owned UNKNOWN',()=>{
 for(const change of [f=>f.decision.findings=[],f=>f.bundle.seeds.push({...f.seed,finding:{id:'other',evidence:{ref:'evaluation.json#/concerns/1',sha256:'b'.repeat(64)}}}),f=>f.decision.findings[0].required_tests_sha256='a'.repeat(64),f=>f.decision.source_scope_digest='c'.repeat(64)]) {
  const f=fixture();change(f);assert.equal(validateCorrectionDecision(f).status,'owned_unknown');
 }
});
