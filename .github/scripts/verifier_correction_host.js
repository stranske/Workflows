'use strict';

// Native cross-reference identity for correction requests: timeline event identity and the
// frozen cross-reference projection/digest that verification_event.js binds. The fresh-facts
// collector that used to live here had no production caller after Auto-Pilot was retired
// (#5379) and was removed.
const {digest}=require('./verification_event');
const need=(value,reason)=>{if(!value)throw new Error(reason);};
function timelineIdentity(row) {
 need(row && typeof row.event==='string','Native timeline event type unavailable');
 if(row.event==='committed') {
  need(typeof row.sha==='string' && /^[a-f0-9]{40}$/.test(row.sha) && typeof row.node_id==='string' && row.node_id.length>0,
   'Native committed timeline identity unavailable');
  return `committed:${row.sha}:${row.node_id}`;
 }
 if(row.event==='cross-referenced') {
  const source=row.source?.issue;
  need(Number.isSafeInteger(row.actor?.id) && row.actor.id>0 && typeof row.created_at==='string'
   && Number.isFinite(Date.parse(row.created_at)) && row.source.type==='issue'
   && Number.isSafeInteger(source?.id) && source.id>0 && typeof source.node_id==='string' && source.node_id.length>0,
   'Native cross-reference timeline identity unavailable');
  return `cross-referenced:${digest({actor_id:row.actor.id,created_at:row.created_at,source_issue_id:source.id,source_node_id:source.node_id})}`;
 }
 if(Number.isSafeInteger(row.id) && row.id>0)return `event:${row.event}:${row.id}`;
 throw Error('Unsupported native timeline event identity; UNKNOWN');
}
function crossReferenceProjection(row,pull) {
 timelineIdentity(row);
 need(row.event==='cross-referenced' && typeof row.source.issue.repository?.full_name==='string'
  && row.source.issue.number===pull.number && row.source.issue.pull_request
  && typeof pull.head?.sha==='string' && /^[a-f0-9]{40}$/.test(pull.head.sha), 'Exact native source PR lineage unavailable');
 return {schema:'closer-correction-native-crossref/v1',event:row.event,actor_id:row.actor.id,created_at:row.created_at,source_issue_id:row.source.issue.id,
  source_node_id:row.source.issue.node_id,source_repository:row.source.issue.repository.full_name.toLowerCase(),
  source_pr:String(row.source.issue.number),source_head_sha:pull.head.sha};
}
function crossReferenceDigest(row,pull) {return digest(crossReferenceProjection(row,pull));}
module.exports={timelineIdentity,crossReferenceDigest,crossReferenceProjection};
