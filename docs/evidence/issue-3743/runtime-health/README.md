# Active PyYAML runtime health: bounded follow-up to #3743

This chunk exercises `_pyyaml_runtime_needs_repair` in the root and consumer-template helpers. Missing distribution metadata, an unsupported installed version, and an installed distribution whose real import fails must request repair; a supported distribution whose real import succeeds must not. Eight tests use controlled distribution metadata and a real temporary-module import, including an observable import marker. The missing/stale cases assert that importing was not attempted.

Production source bytes are unchanged from base `6020028dec510c931364fb69f63dc2a2aa297689`; root and template SHA-256 are both `cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`.

## Matched measurement

The archived command receipts name the exact eight existing test modules and the ninth candidate module, interpreter, working directory, exit status, coverage JSON, and JUnit output. Baseline and candidate used the same checkout, unchanged production source and Python 3.12.2 interpreter. Only the new test module was added to the candidate command.

| Measurement | Baseline | Candidate |
| --- | ---: | ---: |
| Passing cases | 304 | 312 |
| Root helper statements | 576/591 | 581/591 |
| Root helper branches | 248/262 | 249/262 |
| Coverage exclusions | 0 | 0 |

No existing test node was removed, no old outcome changed, and no previously covered line or branch regressed. New covered lines are 337, 338, 340, 343 and 344; the new branch is 339→340. Template behavior is tested directly; its coverage is not separately measured here.

The historical repair proof's six cases and 294→300 matched run remain historical and unchanged. The literal current repair-failure module now has **eight** passing cases. This new run reconciles the current counts; it does not rewrite the older archives or change the provider CONCERNS/CONCERNS verdict on #3832.

The ranking receipt records the last 400 script-touching commits: this helper leads the repair-subject proxy (73 matching subjects, 82 touches). These are ranking proxies, not verified escaped-defect counts.

## Reproduce

```bash
python -m pytest tests/scripts/test_check_deliberate_break_runtime_health.py -q -o addopts=
python docs/evidence/issue-3743/runtime-health/replay.py --output /tmp/runtime-health-proof-NEW
python -m pytest tests/scripts/test_check_deliberate_break_repair_failures.py -q -o addopts=
```

Use a fresh output path for every replay. The driver makes private source/test copies, flips four production decisions in each root/template variant, and runs the corresponding test. All eight mutations produced one failing case (exit 1), then one passing case (exit 0) after byte-identical restoration. Raw stdout, stderr, JUnit, commands, original/mutated/restored hashes and test hashes are archived. Reusing the output directory is refused before mutation; its 49 files remained byte-identical in the refusal check.

For matched coverage, use the baseline/candidate `argv` in the archived command receipts, replacing only report destinations with fresh paths. The candidate includes the new module; the baseline does not. `summary.json` binds the measured source, test and driver bytes.

`proof.tar.gz` stores the raw run packet. `manifest.json` binds its compressed bytes and every decoded member, plus this README, summary, driver and test. Full repository Black (699 files), focused Ruff, template completeness, and `git diff --check` passed. This evidence proves a bounded helper improvement; repository-wide 90%, native/hosted acceptance, provider PASS and whole-source completion remain unproven.
