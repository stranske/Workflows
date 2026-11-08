'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { repositoryConversationGate, syncMergeFailureDisposition, preserveFrozenCanaryRefresh } = require('../maint71_merge_sync_prs');
const { mergeContinuationAcknowledgments, hasContinuationAcknowledgment, observeMaint71Runs,
  formatCampaignMarker, parseCampaignMarker, planMaint71Continuations } = require('../sync_dependency_campaign');
const connection = nodes => ({pageInfo:{hasNextPage:false},nodes});
const thread = {id:'outdated-finding',isResolved:false,isOutdated:true};
const run = {id:42433696440,run_attempt:1,event:'workflow_dispatch',status:'completed',conclusion:'success',
  repository:{full_name:'stranske/Workflows'},head_branch:'main',path:'.github/workflows/maint-71-merge-sync-prs.yml',
  display_title:'Merge Sync PRs [dev-tool]\n7133316e9b2cd59697b5',updated_at:'2026-11-08T01:18:43Z'};
const intent = {lane:'dev-tool',continuation_key:'7133316e9b2cd59697b5'};

test('outdated unresolved conversations obey legacy and applicable ruleset policies', async()=>{
  for (const legacy of [true,false]) {
    const client={paginate:async()=>legacy?[]:[{type:'pull_request',parameters:{required_review_thread_resolution:true}}],
      rest:{repos:{getBranchRules(){},getBranchProtection:async()=>({data:{required_conversation_resolution:{enabled:legacy}}})}}};
    const result=await repositoryConversationGate({connection:connection([thread]),read:fn=>fn(client)});
    assert.equal(result.ok,false);assert.equal(result.reason,'merge_blocked_repository_policy');
    assert.equal(result.unresolved_outdated_count,1);assert.match(result.next_command,/dispositions-and-resolve/);
  }
});
test('resolved conversations require no policy read; optional resolution adds no gate; denied reads stay unknown',async()=>{
  assert.equal((await repositoryConversationGate({connection:connection([{...thread,isResolved:true}]),read:()=>assert.fail()})).ok,true);
  const client={paginate:async()=>[],rest:{repos:{getBranchRules(){},getBranchProtection:async()=>({data:{}})}}};
  assert.equal((await repositoryConversationGate({connection:connection([thread]),read:fn=>fn(client)})).ok,true);
  client.rest.repos.getBranchProtection=async()=>{throw Object.assign(new Error('denied'),{status:403});};
  assert.equal((await repositoryConversationGate({connection:connection([thread]),read:fn=>fn(client)})).reason,'repository_conversation_policy_unknown');
  assert.equal(syncMergeFailureDisposition(new Error('All comments must be resolved.'),{blocked:false,raw_active_count:0}).status,'merge_blocked_repository_policy');
});
test('durable success survives serialization and an empty run-history page; failed/untrusted runs cannot consume',()=>{
  const receipts=mergeContinuationAcknowledgments([],[run],[intent]);assert.equal(receipts.length,1);
  const state=parseCampaignMarker(formatCampaignMarker({items:[],stats:{},continuation_acknowledgments:receipts}));
  assert.equal(hasContinuationAcknowledgment(mergeContinuationAcknowledgments(state.continuation_acknowledgments,[],[intent]),intent),true);
  for(const change of [{conclusion:'failure'},{head_branch:'other'},{path:'other.yml'},{repository:{full_name:'other/repo'}},{event:'pull_request'}]) {
    assert.deepEqual(mergeContinuationAcknowledgments([],[{...run,...change}],[intent]),[]);
  }
  assert.equal(hasContinuationAcknowledgment(receipts,{...intent,continuation_key:'new-material-state'}),false);
  assert.deepEqual(mergeContinuationAcknowledgments(receipts,[],[{...intent,continuation_key:'new-material-state'}]),[]);
});
test('exact workflow completion outside retained history is read once and identity checked',async()=>{
  let exactReads=0;const read=fn=>fn({rest:{actions:{listWorkflowRuns:async()=>({data:{workflow_runs:[]}}),
    getWorkflowRun:async()=>{exactReads++;return{data:run};}}}});
  assert.deepEqual(await observeMaint71Runs({read,owner:'stranske',repo:'Workflows',workflowRun:{id:run.id}}),[run]);
  assert.equal(exactReads,1);
});
test('an early completion wake retains the exact run across serialization until terminal success',async()=>{
  let current={...run,status:'in_progress',conclusion:null};
  const read=fn=>fn({rest:{actions:{listWorkflowRuns:async()=>({data:{workflow_runs:[]}}),
    getWorkflowRun:async()=>({data:current})}}});
  const observed=await observeMaint71Runs({read,owner:'stranske',repo:'Workflows',completionRunId:run.id});
  assert.deepEqual(mergeContinuationAcknowledgments([],observed,[intent]),[]);
  const saved=parseCampaignMarker(formatCampaignMarker({items:[],stats:{},continuation_completion_runs:[observed[0].id]}));
  current=run;
  const terminal=await observeMaint71Runs({read,owner:'stranske',repo:'Workflows',pendingRunIds:saved.continuation_completion_runs});
  assert.equal(hasContinuationAcknowledgment(mergeContinuationAcknowledgments([],terminal,[intent]),intent),true);
});

test('same-plan forced refresh inherits signed source; an explicit original tuple ends the redirect',async()=>{
  const source='a'.repeat(40),newMain='b'.repeat(40),head='c'.repeat(40),plan=`sha256:${'d'.repeat(64)}`;
  const repository='stranske/Ready';
  const record={schema:'sync-pr-delivery-record/v1',repository,plan_id:plan,generation:'generation',
    source_commit:source,head_observed_sha:head,head_observed_at:'2026-11-08T00:00:00Z',
    durable_issue_url:'https://github.com/stranske/Workflows/issues/3926',desired_tree_hash:'tree',
    lease_expires_at:'2026-11-11T00:00:00Z'};
  const metadata={consumer_repo:repository,plan_id:plan,plan_scope:'full',source_commit:source};
  const pr={number:668,state:'open',user:{login:'stranske'},labels:[{name:'sync'},{name:'automated'}],
    head:{ref:'sync/workflows-candidate',sha:head,repo:{full_name:repository}},base:{repo:{full_name:repository}},
    body:`<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->\n<!-- workflows-consumer-sync:v1 ${JSON.stringify(metadata)} -->`};
  const requests=[];
  const client={paginate:async()=>[pr],rest:{pulls:{list(){},get:async()=>({data:pr})},
    repos:{getCommit:async()=>({data:{sha:head,commit:{verification:{verified:true,reason:'valid'},
      message:`Consumer-sync plan ID: ${plan}\nPlan scope: full\nScope base SHA: full\nSource commit: ${source}`}}})},
    actions:{createWorkflowDispatch:async args=>{requests.push(args);}}}};
  const args={withRetry:fn=>fn(client),context:{repo:{owner:'stranske',repo:'Workflows'},payload:{}},core:{notice(){}},
    expectedCanaries:[repository],requestedRepos:repository,planId:plan,planScope:'full',sourceCommit:newMain,force:true,cleanupBranches:false};
  assert.equal((await preserveFrozenCanaryRefresh(args)).redirected,true);
  assert.equal(requests[0].inputs.scope_head_sha,source);assert.equal(requests[0].inputs.expected_plan_id,plan);
  assert.equal(requests[0].inputs.force,'true');assert.equal(requests[0].inputs.cleanup_branches,'false');
  assert.equal((await preserveFrozenCanaryRefresh({...args,sourceCommit:source,expectedPlanId:plan,explicitSourceCommit:source})).redirected,false);
  assert.equal((await preserveFrozenCanaryRefresh({...args,sourceCommit:source,expectedPlanId:plan,explicitSourceCommit:source.toUpperCase()})).redirected,false);
  await assert.rejects(preserveFrozenCanaryRefresh({...args,expectedPlanId:plan}),/explicit_source_missing/);
  assert.equal(requests.length,1);
  client.rest.repos.getCommit=async()=>({data:{sha:head,commit:{verification:{verified:false}}}});
  await assert.rejects(preserveFrozenCanaryRefresh(args),/native_head_unverified/);
  assert.equal(requests.length,1,'unverified source cannot authorize replay');
});
