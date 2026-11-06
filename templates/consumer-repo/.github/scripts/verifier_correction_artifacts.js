'use strict';

// Existing Actions artifacts are the immutable transport, not a new authority
// store. Every effect-side checkpoint must be uploaded AND authenticated back.
const fs=require('fs');
const path=require('path');
const {createHash}=require('crypto');
const {createTokenAwareRetry}=require('./github-api-with-retry');
const {readRetainedArchive}=require('./verifier_pending_execution');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const hex=value=>typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
const positive=value=>Number.isSafeInteger(value) && value>0;
const need=(value,reason)=>{if(!value)throw new Error(reason);};
const SPECS=Object.freeze({
  admitted:{workflow:'.github/workflows/agents-verify-to-new-pr.yml',job:'collect-correction',step:'Upload admitted correction request',member:'correction-admitted.json'},
  ledger:{workflow:'.github/workflows/agents-verify-to-new-pr.yml',job:'Apply admitted correction',step:'Consume admitted correction',member:'verifier-followup-ledger.ndjson'},
  receipt:{workflow:'.github/workflows/agents-verify-to-new-pr.yml',job:'Apply admitted correction',step:'Consume admitted correction',member:'correction-receipt.json'},
  formatpause:{workflow:'.github/workflows/agents-auto-pilot.yml',job:'auto-pilot',step:'Execute step - Format (inline)',member:'correction-format-pause.json'},
  createdpr:{workflow:'.github/workflows/agents-auto-pilot.yml',job:'auto-pilot',step:'Execute step - Create PR',member:'correction-created-pr.json'},
  redispatch:{workflow:'.github/workflows/agents-auto-pilot.yml',job:'auto-pilot',step:'Re-dispatch for next step',member:'correction-redispatch.json'},
  formatredispatch:{workflow:'.github/workflows/agents-auto-pilot.yml',job:'format-pause-wakeup',step:'Clear pause and redispatch format step',member:'correction-redispatch.json'},
  started:{workflow:'.github/workflows/agents-auto-pilot.yml',job:'auto-pilot',step:'Record admitted correction start',member:'correction-started.json'},
});
function artifactName(kind,run,attempt,suffix='') {
  need(SPECS[kind] && positive(run) && positive(attempt),'Invalid correction artifact kind/execution');
  need(typeof suffix==='string' && (!suffix || /^[a-f0-9]{64}-r[1-9]\d{0,5}$/.test(suffix)),'Invalid correction artifact suffix');
  return `verifier-correction-${kind}-${run}-${attempt}${suffix?`-${suffix}`:''}`;
}
async function runtimeArtifactClient(root) {
  // root is the trusted runner-temp SDK install, never a request field.
  const {pathToFileURL}=require('url');
  const module=await import(pathToFileURL(path.join(root,'node_modules/@actions/artifact/lib/artifact.js')).href);
  return new module.DefaultArtifactClient();
}
async function createArtifactTransport({github,repository,current,artifactClient=null,outputDirectory,clock=()=>new Date()}) {
  need(typeof repository==='string' && /^[a-z0-9_.-]+\/[a-z0-9_.-]+$/.test(repository),'Invalid transport repository');
  need(positive(current?.run_id) && positive(current?.run_attempt),'Current trusted execution unavailable');
  const [owner,repo]=repository.split('/');
  const {withRetry}=await createTokenAwareRetry({github,env:{},tokenRegistry:{isInitialized:()=>false},task:'correction-artifact-proof'});
  const read=async(resource,method,args)=>(await withRetry(client=>client.rest[resource][method]({owner,repo,...args,request:{timeout:15000,retries:0}}),{maxRetries:2,initialDelay:250,maxDelay:1000})).data;
  const pages=async(resource,method,args,key)=>{
    const result=[],ids=new Set();let total;
    for(let page=1;page<=10;page++) {
      const data=await read(resource,method,{...args,per_page:100,page});
      const rows=data?.[key];need(Array.isArray(rows) && Number.isSafeInteger(data.total_count) && data.total_count>=0,'Correction inventory unavailable');
      need(total===undefined || total===data.total_count,'Correction inventory changed while paginating');total=data.total_count;
      for(const row of rows){need(positive(row.id) && !ids.has(row.id),'Duplicate/incomplete correction inventory');ids.add(row.id);result.push(row);}
      if(result.length===total)return result;
      need(rows.length>0 && result.length<total,'Incomplete correction inventory');
    }
    throw new Error('Correction history exceeds bounded inventory; UNKNOWN');
  };
  const artifacts=run=>pages('actions','listWorkflowRunArtifacts',{run_id:run},'artifacts');
  const runs=async(workflow,since)=>{
    need(Object.values(SPECS).some(spec=>spec.workflow===workflow) && typeof since==='string' && Number.isFinite(Date.parse(since)),'Invalid correction history scope');
    const found=await pages('actions','listWorkflowRuns',{workflow_id:workflow.split('/').pop(),event:'workflow_dispatch',created:`>=${since}`},'workflow_runs');
    need(found.every(run=>typeof run.created_at==='string' && Number.isFinite(Date.parse(run.created_at))
      && Date.parse(run.created_at)>=Date.parse(since)),'Correction run inventory has unknown/out-of-scope creation time');
    return found;
  };
  const canonicalRun=async(runId,attempt,workflow)=>{
    const latest=await read('actions','getWorkflowRun',{run_id:runId});
    const run=await read('actions','getWorkflowRunAttempt',{run_id:runId,attempt_number:attempt});
    const metadata=await read('repos','get',{});
    need(latest.id===runId && latest.run_attempt>=attempt && run.id===runId && run.run_attempt===attempt
      && run.path===workflow && run.event==='workflow_dispatch'
      && run.repository?.full_name?.toLowerCase()===repository && run.head_repository?.full_name?.toLowerCase()===repository
      && positive(run.repository.id) && run.head_repository.id===run.repository.id
      && /^[a-f0-9]{40}$/.test(run.head_sha || '') && latest.head_sha===run.head_sha
      && metadata.full_name?.toLowerCase()===repository && typeof metadata.default_branch==='string'
      && run.head_branch===metadata.default_branch,'Correction artifact run is not the trusted default-branch execution');
    const head=await read('repos','getCommit',{ref:metadata.default_branch});
    const comparison=await read('repos','compareCommitsWithBasehead',{basehead:`${run.head_sha}...${head.sha}`});
    need(['ahead','identical'].includes(comparison.status) && comparison.base_commit?.sha===run.head_sha
      && comparison.merge_base_commit?.sha===run.head_sha,'Correction workflow origin is not canonical merged source');
    return run;
  };
  const load=async(selector,kind,expectedName)=>{
    const spec=SPECS[kind];need(spec && selector.repository===repository && positive(selector.run_id)
      && positive(selector.run_attempt) && positive(selector.artifact_id),'Invalid correction artifact selector');
    const run=await canonicalRun(selector.run_id,selector.run_attempt,spec.workflow);
    const artifact=await read('actions','getArtifact',{artifact_id:selector.artifact_id});
    need(artifact.id===selector.artifact_id && artifact.name===expectedName && artifact.expired===false
      && positive(artifact.size_in_bytes) && artifact.size_in_bytes<=4194304
      && /^sha256:[a-f0-9]{64}$/.test(artifact.digest || '') && artifact.workflow_run?.id===run.id
      && artifact.workflow_run.head_sha===run.head_sha && artifact.workflow_run.repository_id===run.repository.id
      && artifact.workflow_run.head_repository_id===run.repository.id,'Correction artifact metadata/origin unavailable');
    if(selector.archive_sha256!==undefined)need(hex(selector.archive_sha256) && artifact.digest===`sha256:${selector.archive_sha256}`,'Selected correction archive digest mismatch');
    const jobs=await pages('actions','listJobsForWorkflowRunAttempt',{run_id:run.id,attempt_number:run.run_attempt},'jobs');
    const job=jobs.filter(row=>row.name===spec.job);need(job.length===1,'Correction producer job unavailable/ambiguous');
    need(job[0].run_id===run.id && job[0].run_attempt===run.run_attempt && job[0].head_sha===run.head_sha,'Correction job attempt mismatch');
    const steps=(job[0].steps || []).filter(step=>step.name===spec.step);need(steps.length===1,'Correction producer step unavailable/ambiguous');
    const step=steps[0],active=step.status==='in_progress' && (
      (current.run_id===run.id && current.run_attempt===run.run_attempt)
      || ['ledger','redispatch','formatredispatch','createdpr','formatpause'].includes(kind));
    need((step.status==='completed' && (['ledger','redispatch','formatredispatch','createdpr','formatpause'].includes(kind) || step.conclusion==='success')) || active,'Correction producer step did not establish evidence');
    const at=Date.parse(artifact.created_at),begin=Date.parse(step.started_at),end=active?clock().getTime():Date.parse(step.completed_at);
    need(Number.isFinite(at) && Number.isFinite(begin) && Number.isFinite(end) && at>=begin && at<=end+1000,'Correction artifact is not in the selected attempt/step window');
    const archive=Buffer.from(await read('actions','downloadArtifact',{artifact_id:artifact.id,archive_format:'zip'}));
    need(archive.length>0 && archive.length<=4194304 && sha(archive)===artifact.digest.slice(7),'Correction artifact archive integrity mismatch');
    const files=readRetainedArchive(archive,{maxEntries:2,maxBytes:4194304});
    need(files.size===1 && files.has(spec.member),'Correction artifact member inventory mismatch');
    const bytes=files.get(spec.member);if(selector.member_sha256!==undefined)need(hex(selector.member_sha256) && sha(bytes)===selector.member_sha256,'Correction member changed');
    const refreshed=await read('actions','getWorkflowRunAttempt',{run_id:run.id,attempt_number:run.run_attempt});
    need(refreshed.head_sha===run.head_sha && refreshed.id===run.id && refreshed.run_attempt===run.run_attempt,'Correction source changed while collecting');
    return {bytes,proof:{repository,run_id:run.id,run_attempt:run.run_attempt,artifact_id:artifact.id,
      archive_sha256:sha(archive),member_sha256:sha(bytes),workflow:spec.workflow,job_id:job[0].id,created_at:artifact.created_at,run_created_at:run.created_at}};
  };
  const publish=async(kind,bytes,suffix='')=>{
    need(artifactClient && typeof artifactClient.uploadArtifact==='function' && typeof outputDirectory==='string','Runtime artifact upload unavailable');
    need(Buffer.isBuffer(bytes) && bytes.length>0 && bytes.length<=1048576,'Correction checkpoint exceeds bound');
    const name=artifactName(kind,current.run_id,current.run_attempt,suffix),member=SPECS[kind].member;
    // Both the workspace and member name are trusted host constants, not selectors.
    fs.mkdirSync(outputDirectory,{recursive:true});const file=path.join(outputDirectory,member);
    fs.writeFileSync(file,bytes,{flag:'w'});
    let id;
    try {id=(await artifactClient.uploadArtifact(name,[file],outputDirectory,{retentionDays:30})).id;}
    catch { /* Lost upload ACK is reconciled by exact current-run immutable name. */ }
    if(!positive(id)) {
      const matches=(await artifacts(current.run_id)).filter(row=>row.name===name);
      need(matches.length===1,'Upload outcome UNKNOWN; no effect may follow');id=matches[0].id;
    }
    const selected={repository,run_id:current.run_id,run_attempt:current.run_attempt,artifact_id:id,member_sha256:sha(bytes)};
    const retained=await load(selected,kind,name);need(retained.bytes.equals(bytes),'Exact checkpoint readback failed');
    return retained.proof;
  };
  const jobs=(run,attempt)=>pages('actions','listJobsForWorkflowRunAttempt',{run_id:run,attempt_number:attempt},'jobs');
  return {read,artifacts,runs,jobs,canonicalRun,load,publish,current:{...current},repository};
}
// The canonical workflow supplies a repository/PR concurrency lock derived from
// the authenticated seed. Artifact snapshots implement the existing NDJSON ledger
// within that lock. They are not a cross-workflow lock or a general authority DB.
async function correctionHistory({transport,request,since}) {
  const {canonical,digest}=require('./verification_event');
  const {validateRequest}=require('./verifier_correction_consumer');
  const {seedForRequest,effectKey,validateLedger}=require('./verifier_correction_effects');
  const contexts=[],snapshots=[],subjectPr=request.target.pr;
  const allRuns=await transport.runs(SPECS.admitted.workflow,since);
  for(const run of allRuns) {
    // A run title is only a discovery hint AFTER its canonical workflow source
    // has been authenticated. Caller-selected titles cannot erase history.
    await transport.canonicalRun(run.id,run.run_attempt,SPECS.admitted.workflow);
    need(positive(run.run_attempt) && run.run_attempt<=10,'Correction attempt history exceeds bound');
    const inventory=await transport.artifacts(run.id);
    for(let attempt=1;attempt<=run.run_attempt;attempt++) {
      const name=artifactName('admitted',run.id,attempt),found=inventory.filter(row=>row.name===name);
      need(found.length<=1,'Ambiguous admitted correction artifacts');
      if(!found.length) {
        const selectedAttempt=await transport.canonicalRun(run.id,attempt,SPECS.admitted.workflow);
        const jobs=await transport.jobs(run.id,attempt),effect=jobs.filter(job=>job.name===SPECS.ledger.job);
        need(selectedAttempt.status==='completed' && effect.length===1 && effect[0].status==='completed' && effect[0].conclusion==='skipped',
          'Prior correction execution has no complete non-effect evidence; UNKNOWN');
        continue;
      }
      const loaded=await transport.load({repository:request.target.repository,run_id:run.id,run_attempt:attempt,artifact_id:found[0].id},'admitted',name);
      const context=JSON.parse(loaded.bytes),{context_sha256,...payload}=context;
      need(context.schema==='closer-correction-admitted/v1' && digest(payload)===context_sha256
        && context.collector.repository===request.target.repository && context.collector.run_id===run.id
        && context.collector.run_attempt===attempt,'Admitted correction context corrupt');
      validateRequest(context.request);need(canonical(context.seed)===canonical(seedForRequest(context.request))
        && context.effect_key===effectKey(context.seed),'Admitted seed/request mismatch');
      if(context.request.target.pr!==subjectPr)continue;
      contexts.push({context,proof:loaded.proof});
      const prefix=`verifier-correction-ledger-${run.id}-${attempt}-`;
      const journals=inventory.filter(row=>row.name.startsWith(prefix));
      if(!journals.length && !(transport.current?.run_id===run.id && transport.current?.run_attempt===attempt)) {
        const selectedAttempt=await transport.canonicalRun(run.id,attempt,SPECS.admitted.workflow);
        const jobs=await transport.jobs(run.id,attempt),effect=jobs.filter(job=>job.name===SPECS.ledger.job);
        need(selectedAttempt.status==='completed' && effect.length===1 && effect[0].status==='completed' && effect[0].conclusion==='skipped',
          'Prior admitted effect has missing checkpoints without positive non-effect proof; UNKNOWN');
      }
      for(const artifact of journals) {
        const match=artifact.name.slice(prefix.length).match(/^([a-f0-9]{64})-r([1-9]\d*)$/);
        need(match && match[1]===context.effect_key,'Ledger scope/name mismatch');
        const journal=await transport.load({repository:request.target.repository,run_id:run.id,run_attempt:attempt,artifact_id:artifact.id},'ledger',artifact.name);
        const records=journal.bytes.toString('utf8').trim().split('\n').map(line=>JSON.parse(line));
        const snapshot=validateLedger({revision:Number(match[2]),records},context.effect_key);
        need(records.at(-1).consumer.run_id===String(run.id) && records.at(-1).consumer.run_attempt===String(attempt),
          'Last ledger record is not its authenticated producer');
        snapshots.push({key:context.effect_key,snapshot,proof:journal.proof});
      }
    }
  }
  contexts.sort((a,b)=>Date.parse(a.proof.run_created_at)-Date.parse(b.proof.run_created_at)
    || a.proof.run_id-b.proof.run_id || a.proof.run_attempt-b.proof.run_attempt);
  return {contexts,snapshots};
}
async function createArtifactLedger({transport,request,since,admittedProof}) {
  const {canonical,digest}=require('./verification_event');
  const {effectKey,seedForRequest,validateLedger}=require('./verifier_correction_effects');
  const key=effectKey(seedForRequest(request));let queue=Promise.resolve(),lastProof=null,lastAppendedIntent=null,seenRevision=0;
  const scan=()=>correctionHistory({transport,request,since});
  const read=async selected=>{
    need(selected===key,'Ledger request changed trusted seed key');
    const history=await scan(),matching=history.contexts.filter(row=>row.context.effect_key===key);
    need(matching.length>0,'Current admitted correction context unavailable');
    // The first validated request freezes its original deadline/budget/context;
    // changing caller operation/hold IDs cannot replace or extend it.
    need(matching[0].context.request.request_sha256===request.request_sha256,'Original request/limits rebound across aliases');
    need(!matching.some(row=>row.context.decision?.findings?.some(finding=>['security','authority_conflict'].includes(finding.classification))),
      'A retained qualified-owner hold cannot fall through ordinary correction');
    const snapshots=history.snapshots.filter(row=>row.key===key).sort((a,b)=>a.snapshot.revision-b.snapshot.revision);
    need(new Set(snapshots.map(row=>row.snapshot.revision)).size===snapshots.length,'Ambiguous duplicate ledger revisions');
    if(!snapshots.length) {
      need(seenRevision===0,'Previously observed checkpoint history disappeared; UNKNOWN');
      return {revision:0,records:[]};
    }
    const latest=snapshots.at(-1).snapshot;
    need(snapshots.length===latest.revision && snapshots.every((row,index)=>row.snapshot.revision===index+1
      && canonical(row.snapshot.records)===canonical(latest.records.slice(0,index+1))),'Missing/forked/expired correction checkpoint history');
    need(latest.revision>=seenRevision,'Previously observed checkpoint revisions disappeared; UNKNOWN');
    seenRevision=latest.revision;
    return validateLedger(latest,key);
  };
  const append=args=>{
    const result=queue.then(async()=>{
      need(args.effect_key===key,'Ledger append changed trusted key');
      const prior=await read(key);need(prior.revision===args.expected_revision,'Correction ledger revision conflict');
      const next=validateLedger({revision:prior.revision+1,records:[...prior.records,args.record]},key);
      lastProof=await transport.publish('ledger',Buffer.from(next.records.map(row=>JSON.stringify(row)).join('\n')+'\n'),`${key}-r${next.revision}`);
      seenRevision=Math.max(seenRevision,next.revision);
      const confirmed=await read(key);need(canonical(confirmed)===canonical(next),'Durable checkpoint readback did not match append');
      lastAppendedIntent=args.record.kind==='intent'?args.record:null;
      return args.record;
    });queue=result.catch(()=>{});return result;
  };
  const activeStage=async({record})=>{
    // Only append mints this process-local capability after exact readback. A
    // restarted consumer cannot reconstruct it from retained JSON or read().
    need(lastAppendedIntent && lastProof && canonical(record)===canonical(lastAppendedIntent),
      'No just-appended active stage capability');
    const current=await read(key),last=current.records.at(-1);
    need(canonical(last)===canonical(record) && last.kind==='intent' && last.revision===current.revision
      && last.consumer.run_id===String(transport.current?.run_id)
      && last.consumer.run_attempt===String(transport.current?.run_attempt)
      && lastProof.run_id===transport.current.run_id && lastProof.run_attempt===transport.current.run_attempt,
      'Active stage is not exact current native intent');
    return {schema:'closer-correction-active-stage/v1',effect_key:key,request_sha256:request.request_sha256,
      phase:last.phase,record_sha256:last.record_sha256,revision:current.revision,proof:lastProof};
  };
  const continuationSelector=async({issue})=>{
    const current=await read(key);need(current.records.at(-1)?.phase==='autopilot_dispatch' && lastProof,'No durable dispatch intent selector');
    return {schema:'closer-correction-continuation-selector/v1',repository:request.target.repository,
      collector:admittedProof,intent:{...lastProof,revision:current.revision},request_sha256:request.request_sha256,
      effect_key:key,issue,parent_dispatch:null};
  };
  return {read,append,scan,continuationSelector,activeStage};
}
module.exports={SPECS,artifactName,runtimeArtifactClient,createArtifactTransport,correctionHistory,createArtifactLedger};

async function guardLegacyCorrection({transport,pr,since}) {
 const {digest}=require('./verification_event');
 const {validateRequest}=require('./verifier_correction_consumer');
 for(const run of await transport.runs(SPECS.admitted.workflow,since)) {
  need(positive(run.run_attempt) && run.run_attempt<=10,'Legacy correction guard history exceeds bound');
  const inventory=await transport.artifacts(run.id);
  for(let attempt=1;attempt<=run.run_attempt;attempt++) {
   const actual=await transport.canonicalRun(run.id,attempt,SPECS.admitted.workflow);
   const jobs=await transport.jobs(run.id,attempt),effect=jobs.filter(job=>job.name===SPECS.ledger.job);
   need(effect.length<=1,'Ambiguous correction effect job history');
   // Older collection-only canonical executions have no effect job. A skipped
   // job/consumer step positively proves that this attempt did not enter effects.
   if(!effect.length)continue;
   const job=effect[0];need(job.run_id===run.id && job.run_attempt===attempt && job.head_sha===actual.head_sha,
    'Correction guard effect attempt identity unavailable');
   const consume=(job.steps || []).filter(step=>step.name===SPECS.ledger.step);
   if(job.status==='completed' && (job.conclusion==='skipped' || (consume.length===1
    && consume[0].status==='completed' && consume[0].conclusion==='skipped')))continue;
   const name=artifactName('admitted',run.id,attempt),matches=inventory.filter(row=>row.name===name);
   need(matches.length===1,'Possible correction effect has missing/ambiguous original context; UNKNOWN');
   const loaded=await transport.load({repository:transport.repository,run_id:run.id,run_attempt:attempt,artifact_id:matches[0].id},'admitted',name);
   const context=JSON.parse(loaded.bytes),{context_sha256,...payload}=context;
   need(context.schema==='closer-correction-admitted/v1' && digest(payload)===context_sha256
    && context.collector.run_id===run.id && context.collector.run_attempt===attempt
    && context.collector.repository===transport.repository,'Correction guard context identity unavailable');
   validateRequest(context.request);
   if(context.request.target.pr===String(pr))throw Error('Existing scoped correction may have started; reconcile its exact intent instead of repeating the label lane');
  }
 }
 return {effect_state:'confirmed_not_started',reason:'no_prior_typed_effect_in_this_scope',retry_authorized:false,act_authorized:false,source_closure_authorized:false};
}
module.exports.guardLegacyCorrection=guardLegacyCorrection;
