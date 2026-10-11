# Issue 3835: named evidence destinations

This bounded shared-grammar repair recognizes active evidence delivery `as an
artifact`, PR/inline review-comment destinations, and checklist validation
output/results. Destination ORs, polarity, optional clauses, product capability
and quoted literals continue through the existing shared grammar. Missing or
unavailable named evidence cannot borrow a present PR body.

The production source and consumer template are byte-identical at SHA256
`a743cbfed0bdd653a2a33ee3061650b75175d84ded1031604908343c12fc9c53`.
Base commit: `6020028dec510c931364fb69f63dc2a2aa297689`.
Runtime: Python 3.12.2 from `/opt/anaconda3/bin/python3`.

## Reproduction and focused gate

```sh
python -m pytest tests/scripts/test_pr_verifier_delivery_destinations.py \
  tests/scripts/test_pr_verifier_prompt_coverage.py -k issue3835 -q -o addopts=
```

With the new regressions and original production bytes: **14 failed, 14 passed**
(exit 1). With the repaired production bytes: **28 passed** (exit 0).
The 28 cases cover direct destinations, bounded positive/negative/optional/
product/literal controls, shared ORs, and all three original examples through
the actual coverage floor with the required destination absent and unavailable.

## Independent production reversals

```sh
python docs/evidence/issue-3835-evidence-destinations/replay.py \
  --output /tmp/issue3835-proof-new
```

Use a clean checkout, the validation environment and a **new** output path.
The replay deliberately rewrites both production copies while running. It
validates all mutation anchors before writing, restores the exact fixed bytes
in `finally`, and refuses an existing output directory. Do not run it beside
another writer or test process using the same checkout.

Each of the three repaired grammar rules is separately reversed while the
other two fixes remain intact. The selected direct regression and its
absent/unavailable floor regressions give **3 failures, zero errors, exit 1**.
Exact byte restoration then gives **3 passes, exit 0** on the same named nodes.
All three reversal/restoration pairs passed; both source hashes after every
pair equal the fixed hash above. `three-rule-proof/receipts.json` in the archive
retains each exact argv, cwd, exit status and mutant/fixed/restored hashes.
Raw stdout, stderr and JUnit are retained for all six phases.

## Complete regression gate

```sh
python -m pytest tests/scripts/test_pr_verifier_delivery_destinations.py \
  tests/scripts/test_pr_verifier_prompt_coverage.py -q -o addopts= -n 4 \
  --junitxml=/tmp/opener3835-full-parallel.xml
```

**92,822 passed, zero failures/errors/skips, exit 0** in 384.83 seconds.
The complete result is recorded in `manifest.json` and the archived full JUnit.
An initial serial run was deliberately interrupted after 8,857 passing cases
(exit 2) to rerun the entire two-module selection with four pytest-xdist workers;
its partial log/JUnit are retained and are not counted as a complete gate.

Black, Ruff, `git diff --check`, byte-for-byte source/template comparison and
`python scripts/validate_template_completeness.py` passed.
`python -m pytest tests/scripts/test_sync_manifest_docs.py -q -o addopts=` gave
**2 passed, 1 existing skip**. The full gate above overrides only pytest's
repository-wide default addopts; it does not narrow the two selected modules.

## Evidence integrity and scope

`raw-validation.tar.gz` retains the initial RED/fixed GREEN, interrupted serial
run, complete four-worker run, and independent reversal/restoration receipts.
`manifest.json` binds every archive member plus the archive and five initial
code/test/replay inputs by SHA256. Extract into a fresh directory and verify
member hashes before reuse. The five input hashes describe the initial
implementation; subsequent test extensions have their own receipts below.

These results prove the named grammar and deterministic coverage-floor behavior
in the local two-module gate. They do not establish native provider acceptance,
complete campaign/capture partitioning, downstream generated-consumer rollout,
whole-repository coverage, or hosted runtime parity. Workflows #3820/#3831 and
the ordinary source-to-consumer promotion/reconciliation remain separate owners.

## Follow-up acceptance checks

The follow-up adds floor checks for coverage-report artifact delivery, inline
review comments, checked validation-output items and validation results. Each
named channel is tested as present, absent and unavailable with the PR body
present. Exempt negative/optional/product/literal clauses are also paired with
an independent mandatory artifact delivery, and shared operation aliases are
checked through the actual artifact floor.

`followup-validation.json` records the current input hashes, commands and
results. `followup-validation.tar.gz` retains the focused gate, targeted
coverage, full gate and each independent RED/GREEN replay's raw outputs and
receipts. The original archive and manifest remain historical evidence.
The formatter cache is populated by serial Black CLI checks before the required
whole-repository check; concurrent formatter workers stall in this sandbox.
The serial bootstrap and both formatter logs are retained in the follow-up archive.
