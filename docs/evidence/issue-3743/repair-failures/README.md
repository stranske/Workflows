# Runtime failures after dependency repair

Related to #3743, after independently accepted merged #3808. The earlier provider
CONCERNS/NON_PASS is preserved. This is the next test-only chunk, not completion
of the repository-wide 90% initiative.

The latest 400 scripts-touching commits rank `scripts/check_deliberate_break.py`
first: 73 repair-subject proxy commits and 82 touches. This is a prioritization
proxy, not a verified escaped-defect count. Current baseline coverage identifies
the previously unexecuted post-repair launch handlers and base dependency-error
handler. Production root/template bytes remain identical to base
`9a0219f361e4ba4b9072a554362ef378ff47ec4c`, SHA256
`cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`.

Six named cases cover both distributed copies. A private executable runs and
fails because of missing YAML. The repair stand-in installs nothing: it writes a
private fixture module. A later missing probe or removed command produces a real
ENOENT, whose original exception and cause must survive without another original
execution. A separate temporary Git repository exercises a real base archive:
head succeeds, base repair fails, its cause is reported as FAIL_BROKEN, the
archive disappears, and candidate bytes stay unchanged.

## Original validation

`/opt/anaconda3/bin/python3 -m pytest
tests/scripts/test_check_deliberate_break_repair_failures.py -q -o addopts=`:
6 passed. Exact complete argv/cwd/exits are retained in the archive.

The same six existing helper/replay test modules plus the new file yield
294 baseline passes and 300 candidate passes, with exactly six new JUnit nodes,
no removed nodes, no changed old outcomes and no covered-line regressions.
Identical helper scope contains 591 statements, 262 branches and zero exclusions.
Covered statements increase 563 → 568; covered branches remain 241. Combined
statement/branch coverage increases 94.25556858% → 94.84173505%. These are focused
helper values; no repository-wide percentage or hosted parity is claimed.

All six named cases actually fail under their respective production mutation
(exit 1, one JUnit failure, no collection error) and pass after byte-identical
restoration (exit 0, one pass). Replay creates a private source tree and restores
each mutated copy in `finally`; caller source/test hashes are unchanged. Rerun:

```sh
python3 docs/evidence/issue-3743/repair-failures/replay.py --output /tmp/new-repair-proof
```

The output directory must be new. An actual repeated-output invocation was
refused with FileExistsError; all 37 existing output-member hashes stayed equal.
Full-repository Black checks 677 files unchanged; focused Ruff, template
completeness, root/template byte parity and `git diff --check` pass. Black reports
its Python 3.12/target 3.13 parser warning; this is retained, not suppressed.

## Lossless evidence

The original proof contributes 93 complete members to `validation.tar.gz`: baseline/candidate coverage JSON,
JUnit and console, process receipts, history ranking, six RED/GREEN process
receipts and raw console/JUnit pairs, original/mutated/restored hashes, output
reuse refusal and formatting/template output. `manifest.json` binds the archive,
every decoded member, replay driver, comparison and test bytes. Every binding
was checked after packing. Extract with `tar -xzf validation.tar.gz -C <new-dir>`.
`comparison.json` lists all six new nodes and all five newly covered lines.

Matching keepalive owns hosted checks and review after PR birth. Reviewed Repo
Merge Verify Closer owns complete current expected topology, unchanged head,
full review threads and seven-minute activity floor, guarded merge, actual
verify:compare and bounded disposition. The broader source stays open.

## Parser review recovery

The fresh Semgrep thread on the initial review head identified the native XML
parser in this evidence driver. It now imports `defusedxml.ElementTree` (available
in the recorded Python environment as defusedxml 0.7.1; no package was installed).
Replay requires pytest and defusedxml. All six production mutations were actually
replayed again: RED exit 1 and exact-restoration GREEN exit 0. The archive retains
the original 55 members byte-for-byte plus the complete new 37-member replay
and a control proving a malicious entity is rejected with `EntitiesForbidden`.
Semgrep is unavailable locally; the hosted security scan must requalify the new
head. This parser-only evidence correction changes no production/test coverage
universe; the original 294-to-300 proof remains scoped as stated above.

## Automation-runner follow-up

- [x] Verify all six root/template cases, strengthening the base cases to observe
  the populated archive, its candidate test overlay, exact dependency exception
  identity, and exactly one head and one base command launch.
- [x] Replay all six production mutations: RED exit 1, byte-identical restoration,
  GREEN exit 0. Bind caller root, template, test, and replay-driver hashes.
- [x] Compare the matched suites: 294 baseline PASS and 300 candidate PASS,
  exactly six added nodes, unchanged old outcomes, and no covered-line or branch
  regressions. Preserve 591 statements, 262 branches, and zero exclusions.

Fresh receipts in `revalidation/` reproduce 563 → 568 covered statements and
241 covered branches, or 94.25556858% → 94.84173505% combined coverage. The six
cases also pass independently. Reusing `/tmp/new-repair-proof` fails before
mutation and leaves all 37 output files unchanged. Black checks all 677 files;
focused Ruff, template completeness, root/template parity against base, and
`git diff --check` pass. All 184 archived members verify, including the original
93 members preserved byte-for-byte. Historical test/driver snapshots remain
bound to the prior comparison; the manifest binds the current files separately.

This runner uses Python 3.14.7; `/opt/anaconda3/bin/python3` is absent. The replay
dependency was also absent. Its required modules were staged under `/tmp` from
the official [defusedxml 0.7.1 source](https://github.com/tiran/defusedxml/tree/v0.7.1),
with source, provenance, hashes, and an `EntitiesForbidden` control archived.
Tests install nothing and access no network. The matched suites run with
`PYTHONPATH` unset. An initial pair inherited the replay dependency path and
covered 240 branches because `_run` never saw an empty `PYTHONPATH`; those
receipts remain under `revalidation/with-replay-import-path/`.

The implementation and evidence are verified locally. This runner mounts
`.git` read-only, so `git add` fails creating `index.lock` and no commit can be
created. GitHub API access is unavailable, preventing PR checkbox updates and
readiness-state verification. These environment limits remain open; the literal
Anaconda-interpreter acceptance command was not rerun here.
