'use strict';

const {canonical,digest}=require('./verification_event');
const {validateRequest}=require('./verifier_correction_consumer');
const {effectKey,sourceScopeDigest}=require('./verifier_correction_effects');
const same=(a,b)=>canonical(a)===canonical(b);
const sha=value=>typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
const exact=(row,fields)=>row && typeof row==='object' && !Array.isArray(row)
  && same(Object.keys(row).sort(),fields.split(' ').sort());
const need=(value,reason)=>{if(!value)throw new Error(reason);};

// qualification is independently loaded by trusted host code from Core's actual
// production qualification source. No request/decision boolean can replace it.
// The reviewed production role registry is independently source-loaded. The
// caller must separately authenticate retained classification output; role
// eligibility alone never proves that this decision was emitted by that role.
function validateCorrectionDecision({request,seed,bundle,decision,qualification}) {
  const unknown=reason=>({status:'owned_unknown',reason,act_authorized:false,source_closure_authorized:false});
  try {
    validateRequest(request);
    need(exact(decision,'schema seed_effect_key source_scope_digest request_sha256 findings profile retained_packet_ref decision_evidence_ref'), 'Correction decision fields unavailable');
    need(decision.schema==='closer-correction-decision/v1' && decision.seed_effect_key===effectKey(seed)
      && decision.source_scope_digest===sourceScopeDigest(seed) && decision.request_sha256===request.request_sha256,
    'Correction decision source/request mismatch');
    need(Array.isArray(bundle?.seeds) && bundle.seeds.length>0 && Array.isArray(decision.findings)
      && decision.findings.length===bundle.seeds.length,'Every original raw finding must be accounted');
    const expected=bundle.seeds.map(row=>({id:row.finding.id,evidence:row.finding.evidence}));
    const actual=decision.findings.map(row=>({id:row.id,evidence:row.evidence}));
    need(new Set(actual.map(canonical)).size===actual.length && expected.every(row=>actual.some(other=>same(row,other))),
      'Correction decision omits/substitutes raw findings');
    for(const row of decision.findings) {
      need(exact(row,'id evidence classification required_tests_sha256')
        && ['ordinary_substantive','security','authority_conflict','unknown'].includes(row.classification), 'Risk classification unavailable');
      if(row.classification!=='ordinary_substantive')return unknown('qualified_owner_or_risk_collection_required');
    }
    const selected=decision.findings.find(row=>row.id===seed.finding.id && same(row.evidence,seed.finding.evidence));
    need(selected && sha(selected.required_tests_sha256) && selected.required_tests_sha256===digest(request.required_tests),
      'Exact source-bound required-test decision unavailable');
    need(exact(decision.profile,'id role qualification_ref qualification_sha256')
      && typeof decision.profile.id==='string' && decision.profile.id.length>0
      && decision.profile.role==='closer_interpret' && sha(decision.profile.qualification_sha256)
      && typeof decision.profile.qualification_ref==='string' && decision.profile.qualification_ref.length>0,
    'Declared classification profile unavailable');
    need(qualification && qualification.status==='qualified' && qualification.role==='closer_interpret'
      && qualification.profile_id===decision.profile.id && qualification.qualification_ref===decision.profile.qualification_ref
      && qualification.qualification_sha256===decision.profile.qualification_sha256,
    'Actual production classification qualification unavailable');
    need(typeof decision.retained_packet_ref==='string' && decision.retained_packet_ref.length>0
      && typeof decision.decision_evidence_ref==='string' && decision.decision_evidence_ref.length>0,
    'Bounded source decision evidence unavailable');
    return {status:'admitted',decision_sha256:digest(decision),required_tests:request.required_tests,
      qualification_ref:qualification.qualification_ref,act_authorized:false,source_closure_authorized:false};
  } catch(error) {return unknown(String(error.message));}
}
module.exports={validateCorrectionDecision};
