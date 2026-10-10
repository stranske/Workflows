# Workflows #3820 source recovery evidence

Base: `427798df1c0dd46a39d1f94e809b8959952d9ca4` (current origin/main at implementation).
Implementation issue: https://github.com/stranske/Workflows/issues/3820.

The completed Sol assessment was read and adjudicated without another assessment or
changes to its parent worktree. Its two-layer diagnosis is supported by code and the
immutable capture. The proposed finite discovery ceilings are implemented as bounds,
not assertions that omitted production evidence fits. Unsupported archives are still
incomplete. No scoped archive exclusion, batching, campaign action or provider routing
change is introduced.

The authenticated original capture lives at:
`/Users/teacher/.codex/automations/sync-dependency-pr-closer/worktrees/maint71-targeted-disposition-20261004/evidence/run-38059805990/comparison-results-38059805990`.
It is not copied into this repository. `test_authenticated_capture_replay` asserts all
three packet SHA256 values before evaluating it. Hosted tests skip only this owner-local
replay when `VERIFIER_RECOVERY_CAPTURE_DIR` is absent; local validation sets it explicitly.
Original expanded allocation reproduces four complete files and 127635/257099 included
changed-code characters. Repaired allocation represents seven complete files and all
257099 characters, with coverage still insufficient because captured retrieval failed.
An injected PASS becomes CONCERNS and retains its independent finding.

`original-pagination-red.txt` and `original-prompt-capacity-red.txt` retain new tests
failing against the original production source before repairs. `deliberate_red_green.py`
then mutates repaired production code, tests while it is broken, restores byte-identical
source/template copies, and retests. `deliberate-red-green.json` records exact replacements,
commands, source hashes, exit codes, output hashes and output tails for eight mutations:

- Restore single-page run/artifact discovery.
- Ignore incomplete reference sources.
- Ignore unsupported archive payloads.
- Remove the global download bound.
- Restore the old expanded diff allocation.
- Remove native input capacity preflight.
- Remove schema-repair input capacity preflight.
- Disable the incomplete-coverage floor.

Every mutation yielded RED exit 1 and restored GREEN exit 0. Reproduce with:

```sh
export VERIFIER_RECOVERY_CAPTURE_DIR=/Users/teacher/.codex/automations/sync-dependency-pr-closer/worktrees/maint71-targeted-disposition-20261004/evidence/run-38059805990/comparison-results-38059805990
python3 evidence/issue-3820/deliberate_red_green.py
node --test .github/scripts/__tests__/agents-verifier-context.test.js
python3 -m pytest tests/scripts/test_pr_verifier_prompt_coverage.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_fallback.py tests/scripts/test_pr_verifier_structured_output.py tests/workflows/test_verifier_evidence_profile.py tests/workflows/test_verifier_terminal_disposition.py tests/workflows/test_verifier_verdict_parsing.py tests/workflows/test_reusable_workflow_inputs_doc.py tests/workflows/test_sync_manifest_delivery.py -q --no-cov
scripts/sync_templates.sh
python3 scripts/validate_template_sync.py
python3 scripts/validate_template_completeness.py
actionlint .github/workflows/reusable-agents-verifier.yml templates/consumer-repo/.github/workflows/agents-verifier.yml
```

`context-green.txt`, `python-green.txt` and `workflows-green.txt` retain suite outcomes.
Empty `actionlint.txt` is successful exit 0. Existing sync-manifest entries cover both
repaired scripts and the consumer caller; no managed file is added or re-scoped.
The consumer fingerprint and input snapshot carry `bounded-native-capacity-v2` so
previously fingerprinted expanded inputs cannot suppress this changed contract.

Limits: omitted production comments/artifacts and original archive inventories remain
unknown. The currently selected models have no capacity facts in the installed native
client profiles. Native counting and exact-model capacity are required before generation;
unknown/overflow blocks with NON_PASS, including schema repair and counting auth failure.
No provider invocation or live acceptance is claimed by these offline tests. Expanded
compare skips its uncounted ancillary CLI; expanded checkbox is rejected. Standard Python
evaluations also enforce capacity. These safety constraints may reduce verifier liveness
until model profiles/native counting are supported; the repair does not invent capacities.
Post-merge compare, final review/merge, sync regeneration and promotion remain parent-owned.
