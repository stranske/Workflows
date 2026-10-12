# Active PyYAML runtime health: bounded follow-up to #3743

This chunk exercises `_pyyaml_runtime_needs_repair` in the root and consumer-template helpers. Missing distribution metadata, an unsupported installed version, and an installed distribution whose real import fails must request repair; a supported distribution whose real import succeeds must not. Eight tests use controlled distribution metadata and a real temporary-module import, including an observable import marker. The missing/stale cases assert that importing was not attempted.

The controls also verify the successful import's module identity and file path,
retain the genuine `ImportError` raised by the broken private module, and check
that failed or avoided imports leave no cached module. A `finally` block removes
the successful private import, including when a production mutation fails an
assertion, so later tests cannot inherit a module from a deleted temporary tree.

Production source bytes are unchanged from base `6020028dec510c931364fb69f63dc2a2aa297689`; root and template SHA-256 are both `cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`.

## Matched measurement

The fresh command receipts in `matched/` name the exact eight existing test
modules and the ninth candidate module, interpreter, working directory, exit
status, coverage JSON, and JUnit output. Baseline and candidate used the same
checkout, unchanged production source and Linux Python 3.14.8 interpreter. Only
the runtime-health test module was added to the candidate command. Both commands
skip slow tests with `-m "not slow"`.

The requested `/opt/anaconda3/bin/python3` is unavailable in this environment.
The original Python 3.12.2 macOS packet, archive, manifest, summary, README, driver
and exact test bytes are retained unchanged under `previous-runtime-health/`
inside the new archive. Those historical file bindings are verified against
their retained snapshots; the current manifest binds the strengthened test.

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

For matched coverage, use the baseline/candidate `argv` in the archived
`matched/` command receipts, replacing only report destinations with fresh
paths. Use `--cov=scripts.check_deliberate_break`: the slash form without `.py`
is interpreted as a module name and collects no data. The initial attempts
using that form are retained separately from the valid matched measurement.
The candidate includes the runtime-health module; the baseline does not.
`summary.json` binds the measured source, test and driver bytes, and
`comparison.json` retains the computed count, outcome and coverage comparison.

The committed collector now reproduces and validates this measurement directly:

```bash
python docs/evidence/issue-3743/runtime-health/measure.py --output /tmp/runtime-health-measure-NEW
```

It requires pytest, pytest-cov and defusedxml, fixes the exact eight baseline
modules, and adds only the runtime-health module to the candidate. It retains
raw commands, console, coverage JSON and JUnit, verifies the exact eight added
node IDs and unchanged old outcomes, rejects line/branch regressions and a
changed coverage universe, and checks source/test/evidence hashes before and
after collection. Its checks remain active under optimized Python. Reports must
go to a fresh directory outside the repository; output reuse is refused before
collection. The collector also retains separate current eight-case runtime-health
and repair receipts and explicitly identifies the historical six-case snapshots.

Fresh receipts in `collector-measurement/` reproduce 304/312 PASS, 576/581
covered statements and 248/249 covered branches. `collector-replay/` retains a
fresh eight-mutation replay. `collector-validation/` records nine rejected
corrupt private packets, output-reuse checks, and successful full Black (700
files), focused Ruff, template completeness and diff checks. The absent
defusedxml dependency was staged from hash-verified, already archived source;
its provenance and three source modules are retained, with no network access
or package installation. Child pytest commands clear that staging import path.
Every one of the prior archive's 108 decoded members is preserved byte-for-byte;
its compressed archive, manifest, README and summary are also retained as
`collector-validation/previous-*`. Older repair/module archives remain unchanged.

`proof.tar.gz` stores the raw run packet. `manifest.json` binds its compressed
bytes and every decoded member, plus this README, summary, driver, test and both
production sources. All earlier issue-3743 evidence outside this directory
remains unchanged, checked against the archived before/after SHA-256 inventory.
Full repository Black (699 files), focused Ruff, strict template completeness,
and `git diff --check` passed. The sandbox blocks Black's process workers; the
existing serial checker populated a writable cache before the required full
Black command passed. Template validation used a writable summary destination.
Commands and unsuccessful initial attempts are retained in the archive.

This evidence proves a bounded helper improvement; repository-wide 90%, the
requested Anaconda interpreter rerun, hosted/native acceptance, provider PASS
and whole-source completion remain unproven. Both literal Anaconda commands are
recorded as unavailable. The checkout's Git metadata is read-only, so local
staging fails. The GitHub connector confirms PR #3838 is open and ready, but
blocks blob creation because approval is required and this run's approval policy
is `never`. The verified source/evidence commit is exported from a writable
temporary repository as a Git bundle. Remote publication and PR checkbox updates
remain blocked; local task reconciliation is retained in the archive.

## Current replay binding after review recovery

The matched `summary.json`, `manifest.json` and `proof.tar.gz` above are the
immutable original Linux measurement packet. Their replay hash names the original
driver used by that run. The selected-JUnit and optimized-Python review recovery
subsequently changed the current driver. Its current hash, all original decoded
archive members and the later proof artifacts are reconciled in
`current-binding-20261012.json`; historical summaries are not rebound to new bytes.
`closer-guard-20261011/guard-proof.json` binds the current driver and its actual
macOS Anaconda optimized eight-mutation RED/restored-GREEN execution. The Linux
interpreter-unavailable record remains true for its original environment.

`tests/scripts/test_runtime_health_replay.py` is the direct regression suite for
the two accepted review findings, not unrelated coverage expansion. Run it with
the runtime-health and repair-failure modules before closer acceptance. Current
command receipts are retained in `binding-validation-20261012/`. Hosted complete
topology, zero active threads, a new seven-minute floor after this documentation
push and actual post-merge comparison remain separate gates.
