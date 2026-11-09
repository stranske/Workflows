# Round 11 publication blocker

Round 11 implemented continuous read-only origin observation in docs/evidence/issue-4369/observe-maint68.js with 15 additional regression cases (47 Node tests pass; 124 existing Python receipt tests pass). Adjacent complete windows must agree at inclusive boundaries; gaps, overlaps, missing/conflicting boundary rows and scope changes are refused. The retained 198-run replay covers 2026-11-09T01:49:57Z–02:21:41Z and finds zero exact-path Maint 68/71 runs; no workflow was dispatched. The automation-origin chain and upstream non-PASS verifier remain unresolved.

Verified reconciliation is retained locally in runtime-4550/4558-round11-pr-body-reconciled.md. The PR-body update was rejected by automatic approval review (approval policy never). Explicit-path git add also failed: .git/index.lock is on a read-only filesystem, so no commit or push was made. Please have the existing authorized writer publish the code/tests and reconcile the proven checkboxes; this run cannot clear the external acceptance blockers.

Posting that comment and adding `needs-human` were also rejected by automatic approval review: `MCP tool call requires approval, but approval policy is never`. Neither succeeded.
