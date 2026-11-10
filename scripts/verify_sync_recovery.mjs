#!/usr/bin/env node
// Read-only operational replay. Inputs remain outside the source repository.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const maint71 = require('../.github/scripts/maint71_merge_sync_prs.js');
const campaign = require('../.github/scripts/sync_dependency_campaign.js');
const args = process.argv.slice(2);
const evidence = args[args.indexOf('--evidence') + 1];
const current = args[args.indexOf('--current') + 1];
const connection = JSON.parse(fs.readFileSync(path.join(evidence,
  'resume-paem-unresolved-threads.json'))).data.repository.pullRequest.reviewThreads;
const live = JSON.parse(fs.readFileSync(path.join(current, 'paem-pr.json')))
  .data.repository.pullRequest;
if (connection.nodes.map(t=>t.id).sort().join() !== live.reviewThreads.nodes.map(t=>t.id).sort().join()
  || live.reviewThreads.pageInfo.hasNextPage !== false) throw new Error('historical/current thread inventory differs');
// Historical capture retains pre-disposition flags; today's complete inventory
// establishes that this replay does not silently omit another conversation.
connection.pageInfo = live.reviewThreads.pageInfo;
const rules = JSON.parse(fs.readFileSync(path.join(current, 'paem-rules.json')));
const protection = JSON.parse(fs.readFileSync(path.join(current, 'paem-protection.json')));
const readPolicy = fn => fn({paginate: async () => rules,rest:{repos:{getBranchRules(){},
  getBranchProtection:async()=>({data:protection})}}});
const active = connection.nodes.filter(t => !t.isResolved && !t.isOutdated);
const legacyGate = await maint71.confirmExactHeadSyncFindingGate({
  owner: 'stranske', repo: 'Portable-Alpha-Extension-Model', pr: {number:2454,head:{sha:'9c85282d05359ddc468d0881ec6b09269ac592a2'}},
  threads: active, record: {}, read: () => { throw new Error('unexpected evidence read'); },
});
const gate = maint71.repositoryConversationGate
  ? await maint71.repositoryConversationGate({connection,owner:'stranske',repo:'Portable-Alpha-Extension-Model',branch:'main',
      read: readPolicy})
  : legacyGate;
const verified = gate.ok === false && gate.reason === 'merge_blocked_repository_policy'
  && gate.unresolved_outdated_count === 7;
const liveGate = maint71.repositoryConversationGate
  ? await maint71.repositoryConversationGate({connection:live.reviewThreads,owner:'stranske',repo:'Portable-Alpha-Extension-Model',branch:'main',
      read: readPolicy})
  : legacyGate;
console.log(JSON.stringify({input:'PAEM2454 before truthful disposition',active:active.length,
  unresolved_outdated:connection.nodes.filter(t=>!t.isResolved&&t.isOutdated).length,
  blocking:gate.ok?'none':gate.reason,drainable:gate.next_command||'none',verified}));
console.log(JSON.stringify({input:'PAEM2454 current merged head',state:live.state,blocking:liveGate.ok?'none':liveGate.reason,
  unresolved:liveGate.unresolved_count}));
const completed = JSON.parse(fs.readFileSync(path.join(current,'consumed-run.json')));
const [,lane,key] = completed.display_title.replace(/\s+/g,' ').trim()
  .match(/^Merge Sync PRs \[([^\]]+)\] (\S+)$/);
const intent = {lane,continuation_key:key,repository:'stranske/Ready',pr:668};
const receipts = campaign.mergeContinuationAcknowledgments
  ? campaign.mergeContinuationAcknowledgments([], [completed], [intent]) : [];
const restored = campaign.parseCampaignMarker(campaign.formatCampaignMarker({
  continuation_acknowledgments:receipts,items:[],delivery_handoffs:[],stats:{}}));
const workflow = fs.readFileSync(new URL('../.github/workflows/maint-82-sync-dependency-campaign.yml',import.meta.url),'utf8');
const step = workflow.split('- name: Dispatch due Maint 71 continuations')[1].split('\n      - name: Upload campaign state')[0];
const script = step.split('          script: |\n')[1].split('\n').map(line=>line.replace(/^ {12}/,'')).join('\n');
const execute = new (Object.getPrototypeOf(async function(){}).constructor)('require','process','github','context','core',script);
let dispatches = 0;
const github = {rest:{actions:{listWorkflowRuns:async()=>({data:{workflow_runs:[]}}),
  createWorkflowDispatch:async()=>{dispatches++;}}}};
await execute(name=>name.includes('github-api-with-retry')
  ? {createTokenAwareRetry:async()=>({withRetry:fn=>fn(github)})} : campaign,
  {env:{CONTINUATIONS_JSON:JSON.stringify([intent]),REGISTERED_REPOS:'stranske/Ready',
    ACKNOWLEDGMENTS_JSON:JSON.stringify(restored.continuation_acknowledgments||[])}},github,
  {repo:{owner:'stranske',repo:'Workflows'},payload:{}},{notice(){},warning(){}});
const ackVerified = receipts.length === 1 && dispatches === 0;
console.log(JSON.stringify({input:`completed native run ${completed.id}`,continuation_key:key,
  history_rows:0,restored_acknowledgments:receipts.length,dispatches,verified:ackVerified}));
const producer = fs.readFileSync(new URL('../.github/workflows/maint-68-sync-consumer-repos.yml',import.meta.url),'utf8');
const guardStep = producer.split('- name: Check content refresh guard')[1].split('\n      - name: Authorize canary payload mutation')[0];
const guardScript = guardStep.split('          script: |\n')[1].split('\n').map(line=>line.replace(/^ {12}/,'')).join('\n');
const guardExecute = new (Object.getPrototypeOf(async function(){}).constructor)('require','process','github','context','core',guardScript);
const nativePr = JSON.parse(fs.readFileSync(path.join(current,'paem-rest-pr.json')));
// Replay the captured pre-merge producer phase. Its immutable native head and
// record are read back from GitHub; only the historical OPEN flag is restored.
nativePr.state='open';
const nativeHead = JSON.parse(fs.readFileSync(path.join(current,'paem-native-head.json')));
let redirect;
const producerClient={paginate:async()=>[nativePr],rest:{pulls:{list(){},get:async()=>({data:nativePr})},
  repos:{getCommit:async()=>({data:nativeHead})},actions:{createWorkflowDispatch:async params=>{redirect=params;}}}};
let allowed;
await guardExecute(name=>name.includes('github-api-with-retry')
  ? {createTokenAwareRetry:async()=>({withRetry:fn=>fn(producerClient)})}
  : name.includes('maint71_merge_sync_prs') ? maint71 : require('../'+name.replace(/^\.\//,'')),
  {env:{SOURCE_COMMIT:'7e377b7ad8cc06e506393218bc7459ba47757f01',EXPECTED_PLAN_ID:'',
    PLAN_ID:'sha256:4017589cec3ca50a3f528f382fe788b40f49cfcd2641214da354672b71ff27da',
    PLAN_SCOPE:'full',SCOPE_BASE_SHA:'',FORCE:'true',REQUESTED_REPOS:'stranske/Portable-Alpha-Extension-Model',CLEANUP_BRANCHES:'false'}},
  producerClient,{repo:{owner:'stranske',repo:'Workflows'},payload:{repository:{default_branch:'main'}}},
  {notice(){},setOutput(name,value){if(name==='allowed')allowed=value;},summary:{addRaw(){return this;},async write(){}}});
const sourceVerified=allowed==='false' && redirect?.inputs.scope_head_sha==='c2ac6f38d6f2ce73f000158fa6f729bfece82092'
  && redirect?.inputs.expected_plan_id==='sha256:4017589cec3ca50a3f528f382fe788b40f49cfcd2641214da354672b71ff27da';
console.log(JSON.stringify({input:'forced native PAEM refresh42444646712',unbound_mutation_allowed:allowed,
  redirected_source:redirect?.inputs.scope_head_sha,verified:sourceVerified}));
const count = Number(verified && liveGate.ok) + Number(ackVerified) + Number(sourceVerified);
console.log(`OUTCOME_1 priority_recoveries_verified=${count}/3`);
process.exitCode = count === 3 ? 0 : 1;
