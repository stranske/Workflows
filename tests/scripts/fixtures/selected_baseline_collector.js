// Offline API/ZIP fixture; production collector, formatter and manifest builder are real.
'use strict';
const {execFileSync}=require('child_process');
const {createHash}=require('crypto');
const {fetchVerifierEvidence,formatVerifierEvidence,buildContextSourceCoverage}=require('../../../.github/scripts/agents_verifier_context');
const {buildVerificationEvent}=require('../../../.github/scripts/verification_event');
(async()=>{
 const BASE='a'.repeat(40),HEAD='b'.repeat(40),MERGE='c'.repeat(40);
 const bytes=Buffer.from('unchanged source\n');
 const source={type:'file',path:'src/a.py',encoding:'base64',size:bytes.length,content:bytes.toString('base64'),sha:createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`),bytes])).digest('hex')};
 const archive=execFileSync('python3',['-c',"import sys,zipfile,io;b=io.BytesIO();z=zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED);z.writestr('huge.json','x'*300000) if sys.argv[1]=='partial' else None;z.writestr('combined.txt','EXACT_SELECTED_COVERAGE_TABLE: audit 1127/51 periodic 1075/99');z.close();sys.stdout.buffer.write(b.getvalue())",process.argv.includes('--complete')?'complete':'partial']);
 const selector={kind:'artifact_member',run_id:10,artifact_id:20,path:'combined.txt',evidence_role:'comparison-baseline',compared_paths:['src/a.py']};
 process.env.VERIFICATION_MATERIAL=JSON.stringify([selector]);
 const body=process.argv.includes('--complete') ? 'Evidence must be uploaded as a workflow artifact. Retain and assess the selected coverage table.' : 'Evidence must be provided in the PR body. Retain and assess the selected coverage table.';
 const diff='diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n';
 let downloads=0;
 const github={rest:{issues:{listComments:async()=>({data:[{id:1,body:'OPTIONAL_COMMENT_PAYLOAD_'.repeat(500),html_url:'https://github.com/o/r/pull/7#issuecomment-1',user:{login:'author'}}],headers:{}})},
 pulls:{listReviewComments:async()=>({data:[],headers:{}}),listReviews:async()=>({data:[],headers:{}})},
 repos:{compareCommitsWithBasehead:async()=>({data:{status:'ahead',base_commit:{sha:BASE},merge_base_commit:{sha:BASE}}}),getContent:async()=>({data:source})},
 actions:{getWorkflowRun:async()=>({data:{id:10,run_attempt:1,status:'completed',event:'push',head_sha:BASE,repository:{full_name:'o/r'}}}),listWorkflowRunArtifacts:async()=>({data:{total_count:1,artifacts:[{id:20,name:'proof',size_in_bytes:archive.length,expired:false}]},headers:{}}),downloadArtifact:async()=>{downloads++;return {data:archive}},listWorkflowRuns:async()=>({data:{total_count:0,workflow_runs:[]},headers:{}})}}};
 const evidence=await fetchVerifierEvidence({github,owner:'o',repo:'r',pullNumber:7,pullRequestBody:body,associatedCommitShas:[HEAD,MERGE],evaluatedSha:MERGE});
 const manifest=buildVerificationEvent({repository:'o/r',pull:{number:7,body,head:{sha:HEAD},merge_commit_sha:MERGE},issues:[],fullDiffBytes:Buffer.from(diff),evidence,selectors:[selector],ciResults:[]});
 const coverage=buildContextSourceCoverage({planSources:[{source:'Pull request #7',body}],diffText:diff,evidence});
 coverage.acceptance_source_discovery={required:false,status:'included'};
 process.stdout.write(JSON.stringify({body,diff,coverage,evidence:formatVerifierEvidence(evidence),manifest,downloads}));
})().catch(error=>{console.error(error);process.exitCode=1});
