# Source merge and documentation recovery — 2026-10-10

The source owner merged #3821 exact `2f2b9286fdabe1367673afe8776ebe07d495dd47`
as `cfeff10dd0213068fcc5ee893323d445a6ecc341` at 19:25:01 UTC.
Release #3823 then advanced main to eaf43808 (full second parent retained by Git).
#3822's reviewed head b90b168563f5b2786b9aa1280d7ce2b1a8c2977b conflicted with
the repeated #3821 squash content. A normal, non-rewriting merge was used.

## Conflict disposition

All eleven conflicted files were inspected. For those files,
`git diff 2f2b9286 origin/main -- <conflicted files>` showed only the unrelated
CodeRabbit manifest-description change already incorporated through main71357.
The #3822 side preserves all subsequent native/registry/aggregation/security/
checkout repairs. After resolution, the executable verifier, caller template,
manifest, drift baseline, capacity fixtures and recovery tests were byte-identical
to b90. One automatically reintroduced obsolete static-v2 test assertion was
removed: existing executable tests already require expanded-v6 and standard-v2.
One documentation blank line was restored. Release metadata/changelog remain.

## Adopted documentation findings

The independent source-design assessment950324 found two nonblocking doc errors.
Added two tests; command
`python3 -m pytest -q tests/workflows/test_verifier_evidence_profile.py -k 'workflow_inventory_names or workflow_guide_distinguishes'`
actually failed both assertions (2 failed,42 deselected,0.40s).
The attempted .venv command was unavailable and is not validation.
Corrected WORKFLOWS.md expanded fingerprint v4 to executable v6 and
WORKFLOW_GUIDE.md to distinguish caller-only App token from the Workflows
scripts checkout's github.token. No runtime capacity facts or code changed.

## Stable post-merge validation

Locked offline command prefix:
`uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m`.

Pytest selector: tests/workflows/test_verifier_expanded_checkout.py,
test_verifier_expanded_comparison.py, test_verifier_caller_security.py,
test_verifier_evidence_profile.py; tests/scripts/test_template_drift_allowlist.py,
test_validate_template_sync.py, test_native_capacity_recovery.py,
test_native_capacity_registry.py.
Actual result: **619 passed,18 scoped skipped,55.11s**, process exit0.
JUnit:20261010-source-merge-green.xml. An initial selector named nonexistent
tests/test_template_sync.py and ran zero tests; it is excluded.
Locked Ruff and Black checks on the changed test passed; git diff --check passed.

## Limits and continuation

Prior b90 assessments/reviewer dispositions are historical on a changed head.
Fresh exact-head review, authoritative CI/topology, seven-minute floor, direct
mergeability and zero active non-outdated findings remain mandatory.
#3821 post-merge standard compare38079721596 was workflow SUCCESS but actual
CONCERNS/CONCERNS:55841/459923 code chars,21/58 files complete, acceptance evidence
truncated. It is not acceptance; source3822 owns native expanded recovery.
This local source regression is not authenticated native capacity, provider PASS,
deployment, generated delivery acceptance or permission to bypass Maint68/71.
