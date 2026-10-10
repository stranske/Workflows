# Verifier caller security repair — bounded source result

Base HEAD remains `e79e2c0fa7f9562f1283f8be62f2ce6d649672b4`. No commit,
push, GitHub/API operation, live provider call, assessor, automation write,
issue-3821 modification, or historical receipt rewrite was performed.
Parent remains the sole publisher. Source capacity acceptance and provider
acceptance are **UNKNOWN**.

## Baseline finding attribution

The reported hosted findings are pre-existing defects, not introduced by this
branch's fingerprint change. Inspection preceded repair: Health 51 runs zizmor
over all three workflow directories with advisory scan/upload steps; its only
authored rule configuration changes unpinned-uses to ref-pin. Health 52 uses
the mutable registry packs `p/default`, `p/python`, `p/github-actions`, and
`p/secrets`, with advisory scan/upload steps. Neither authored workflow nor
`.github/zizmor.yml` differs between local `origin/main` and published HEAD.
Local origin/main is `8ee9d8cd4b1016c85a169a2029ab9dc56ce298ad`; it was not
refreshed remotely. `git diff origin/main HEAD --` the consumer caller contains
only the five added fingerprint-contract lines. No scanner baseline or rule
configuration was changed by this repair.

The hosted IDs/lines supplied by the parent were Semgrep 114274520839, template
line 345 (`secrets: inherit`), and zizmor 114274026181 (target trigger, global
writes, inherited secrets, credentials, interpolation and local-action notes).
No hosted run was independently fetched. Local baseline scans of the actual
published YAML reproduce the inherited-secret finding at template line 345
and the reported zizmor defect classes. Full-file SARIF scanning can surface
existing constructs when a file changes; this result does not claim a new
fingerprint regression caused those constructs.

## Repair and retained boundary

- Source and template retain `pull_request_target: labeled` for post-merge fork
  secret availability. A job gate now rejects unmerged PRs and non-exact labels
  before checkout or secret handling. The existing manual API merged check is
  retained. Repository label permission or workflow-dispatch authorization is
  the authorization boundary, not fork authorship.
- Both caller helper checkouts and the reusable caller checkout explicitly use
  trusted `github.sha`; all relevant checkouts disable credential persistence.
  Workflows helpers retain the resolved default-branch contract. The optional
  checkout App token is restricted to contents read on the caller repository;
  the public Workflows checkout uses the workflow token.
- Workflow defaults grant nothing. Caller check jobs read contents and PRs and
  no longer receive rotating PAT/App credentials. Verifier jobs read contents,
  issues, Actions and Models and write PR comments. Consumer fingerprint
  persistence has only contents read and PR write. The disabled issue creation
  step and `pr_verifier._should_create_issue` returning False justify removing
  issues write. Re-enabling issue creation needs separate permission review.
- Both reusable calls explicitly map all six declared secrets, including
  lowercase `workflows_app_id`/`workflows_app_private_key`. Reusable App inputs
  use those same declared names. The shared API retry library's existing App
  credential rotation remains unchanged; installation permissions are outside
  this bounded caller repair.
- Consumer fingerprint reason/hash outputs now use quoted shell environment
  variables. The complete Compute state fingerprint step is byte/structure
  equivalent to published HEAD. Standard v2, expanded v6, merged/label gate,
  success-only persistence, native capacity and all-arms executable bodies are
  retained. Every reusable `run` and `with.script` body is unchanged.

The two inline `zizmor: ignore[dangerous-triggers]` comments apply only to the
necessary trigger nodes. No config-wide exclusion or scanner weakening was
added. `--no-ignores` still reports exactly those two dangerous-trigger findings
alongside the pre-existing local-action notes. The trust-boundary documentation
explains why removing this event would break fork verification. Accepted base
code and branches selected by privileged dispatchers are trusted; malicious
maintainer-merged code and LLM prompt-injection resistance are not proven here.

## Verification and scanner limits

All Python validation used the cached locked offline prefix:

```text
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock
```

The new security suite passed 15 tests. It evaluates the exact job guard's
JS-compatible expression subset for merged/unmerged, exact/non-exact labels,
fork/same-repository and manual events; executes the authored manual gate script
with a stub API; checks token/secret/checkout contracts; and executes shell
injection payloads as inert reason/hash data. This is local execution, not a
hosted GitHub expression-engine or fork-event observation.

`python evidence/issue-3820/verifier-caller-security-red-green.py` deliberately
mutated actual production YAML six ways: inherited secrets, workflow-global
write, PR-head checkout, inverted merged gate, raw shell interpolation, and
persisted credentials. Every selected test executed and failed with exit 1;
each byte-identical restoration passed with exit 0. The secret mutation remains
valid YAML and uses the real `secrets: inherit` construct. Exact commands,
before/mutated/restored hashes and JUnit/transcripts are in
`verifier-caller-security-red-green.json` and the six paired proof artifacts.

Final bounded regressions: **869 passed, 19 skipped**, exit 0. Included workflow,
manifest compiler/delivery, drift, profile/fingerprint, native capacity/registry,
all-arms comparison, recovery, verdict and interpolation suites. The 18
Anthropic Models API contract skips and one absent owner-local authenticated
capture remain explicit; no provider acceptance is inferred. This was not the
full repository suite. Exact test arguments are in the commands receipt.

Final Ruff, Black, default actionlint (with available shellcheck), template-sync
validator and drift validator all exit 0. Drift reports 6 in-sync pairs, 20
existing allowlisted pairs and zero unallowlisted drift. Only verifier pair 14
hashes/rationale were refreshed; its original divergence review date remains.

Actual scanners were Semgrep 1.179.0 and zizmor 1.30.1. Zizmor used `--offline`
and the unchanged repository config. Semgrep retrieved the authored four
registry packs with metrics/version checks disabled; this is scanner rule
retrieval, not a live verifier/provider run. Hosted tool/rule versions are
unverified, and registry packs are mutable.

- Final Semgrep on the consumer template alone: exit 0, zero findings/errors.
- Baseline three-file Semgrep: 16 findings, including both inherited-secret
  calls. Final three-file Semgrep: exit 1, 14 remaining mutable-action-tag
  findings (2 root caller, 12 reusable), all pre-existing. Fourteen parser/
  matching warnings remain in unchanged reusable script bodies; the baseline
  had 18 warnings. The aggregate scan is **not green**.
- Baseline zizmor: 38 findings, including global writes, inherited secrets,
  persisted credentials, dangerous triggers and overbroad checkout App tokens.
  Final zizmor: exit 12, 21 residual findings: 17 informational interpolation
  notes in unchanged reusable bodies and 4 low self-repository syntax notes.
  The consumer has only its existing low local-action syntax note. The targeted
  permission/secret/credential defects are absent; the two trigger findings
  have the narrowly documented dispositions. The aggregate scan is **not green**.

Scanner JSON/transcripts retain findings and warnings without historical
rewrites. Final source/scanner-input hashes and semantic-preservation assertions
are in `verifier-caller-security-bindings.json`; scanner results bind to those
final three workflow hashes. Review/publication/hosted reruns belong to parent.

## Changed paths and preservation

Changed existing production/documentation paths:

- `.github/workflows/agents-verifier.yml`
- `templates/consumer-repo/.github/workflows/agents-verifier.yml`
- `.github/workflows/reusable-agents-verifier.yml`
- `.github/sync-manifest.yml` (existing managed entry annotated; scope unchanged)
- `config/template-drift-allowlist.txt` (verifier pair only)
- `docs/ops/CONSUMER_REPO_MAINTENANCE.md`

Added test: `tests/workflows/test_verifier_caller_security.py`.
Added evidence paths are enumerated with SHA-256 in
`verifier-caller-security-artifacts.json`, including this note and the mutation
runner. All evidence created by this offload uses the
`evidence/issue-3820/verifier-caller-security-` prefix.

All **22** original untracked artifacts and **140** prior evidence files retain
their original bytes. A full initial-file hash comparison confirms that only
the six listed pre-existing source/docs paths changed; preservation details are
in `verifier-caller-security-preservation.json`. Final production diff-check is
clean. No source capacity or provider acceptance is claimed: both remain
**UNKNOWN**.
