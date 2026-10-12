# Head command launch failure proof

The existing helper's head-command error reporter was uncovered in the matched
helper suite. Four root/template controls now launch a real absent executable
(ENOENT) or a real non-executable file (EACCES) through `verify_spec`. They require
`FAIL_BROKEN`, `command-unavailable`, exact command and original OS error detail,
JSON serializability, unchanged proof/launcher bytes, and no dependency repair or
base archive extraction. Production root/template bytes are unchanged.

The controls also require exactly one command attempt, forbid runtime probes,
and preserve the candidate `app.py` bytes, including CRLF line endings. Recording
all attempts prevents an extra successful command from escaping the assertions.

## Reproduce

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break_head_launch.py -q -o addopts=
python3 docs/evidence/issue-3743/head-launch/replay.py --output /tmp/new-head-launch-proof
```

Use a fresh output directory. Replay mutates only private source copies. Each
case changes only the head error verdict from FAIL_BROKEN to PASS, requires the
selected verdict assertion to fail (exit1), restores exact original bytes, then
requires the same selected case to pass (exit0). XML validation rejects errors,
skips, unexpected nodes, and invalid assertion outcomes. Existing output is
rejected before source copies or mutations. This run verified29 retained files
remain byte-identical after rejected reuse.

## Observed validation

At base fdc18a19314492ce3b78623b4acfb75c00f6227e on macOS, Anaconda Python3.12:

- Identical ten-module baseline316PASS and candidate320PASS: exactly4 new PASS
  nodes, no removed nodes or changed old outcomes.
- Root helper583→585/591 statements,251/262 branches unchanged, zero exclusions;
  no covered-line or branch regression. Newly covered lines995–996.
- Four genuine production assertionRED/restoredGREEN pairs, zero errors/skips,
  equal original/restored hashes. Original/mutant/restored source bytes retained.
- Full-repositoryBlack, focusedRuff, strict template completeness and diff-check
  exit0. All640 tracked historical evidence files remain byte-identical.
- Fresh last400 scripts-touching commits rank this helper first:72 repair-subject
  proxy matches/82 touches. The proxy is not a verified escaped-defect count.

`summary.json` binds exact measured counts. `proof.tar.gz` retains raw console,
JUnit, argv/cwd/exits, coverageJSON/databases, replay receipts/source bytes, reuse
preservation hashes, validation logs, and ranking inputs. `manifest.json` binds
current files and every regular archive member by SHA256.

## Current Linux verification

Hosted Python 3.14.8 reran the strengthened tests: four PASS, four assertion RED
exit 1 / restored GREEN exit 0 mutation pairs, and rejected output reuse with all
29 proof files preserved. The identical ten-module comparison again measured
316 to 320 PASS, exactly four new nodes, no changed or removed old outcomes,
583 to 585 covered statements out of 591, and 251 covered branches out of 262.
There are zero exclusions and no covered-line or branch regressions. Production
and all 783 historical evidence files tracked at the base remain byte-identical.
Focused Ruff, strict template completeness, and diff validation pass. The full
Black check passes for all 712 files using a retained temporary serial adapter
that invokes installed Black's single-file checker with the normal CLI's file
selection and formatting rules. Its worker pool cannot start in this sandbox;
the single-worker fallback timed out. Both failed attempts are retained. Template
validation writes its summary to `/tmp` because the inherited summary path is
read-only.

`summary.json.current_run` records this interpreter and the current test hash.
The archive's `linux/` members retain its raw inputs, console/JUnit, coverage
databases/JSON, commands/exits, replay and reuse receipts, and validation logs.
The original macOS archive and metadata are retained under `linux/previous/`;
all original archive members remain unchanged.

`/opt/anaconda3/bin/python3` is absent in this runner. The two acceptance commands
that require that exact interpreter remain pending for the strengthened tests.
The original macOS measurements above describe the earlier test version.

## Verdict assertion validation

Replay now requires both the JUnit failure message and traceback to identify the
exact `assert 'PASS' == 'FAIL_BROKEN'` mismatch. An unrelated assertion containing
`FAIL_BROKEN`, a reversed comparison, or a longer assertion cannot establish
mutation detection. The new replay controls first exposed five accepted false
reports (five FAIL, four PASS), then all nine controls passed after the fix.
The four head launch tests retain their existing nodes and source bytes.
The nine replay controls run separately from the matched ten-module baseline
and candidate containing only the additional head launch module.

`summary.json.assertion_validation_run` records the new replay and control test
hashes. The archive's `assertion-validation/` members retain this round's raw
commands, console/JUnit, four real assertion RED/restored GREEN pairs, source
bytes, output reuse hashes, matched coverage inputs, and validation logs. Every
previous archive member remains byte-identical, with the previous archive and
metadata retained separately. The exact Anaconda commands remain unavailable.
Installed Black's normal CLI file selection and single-file checker pass for
all 713 files through a retained serial adapter; the same adapter rejects an
unformatted control without changing it. The native worker failure and the
initial matched-suite timeout are retained as unsuccessful attempts.

This is focused helper coverage, not repository-wide90%, hosted parity, provider
PASS or completion of broader source3743. Prior3856/3865 CONCERNS dispositions and
all historical proof remain unchanged. Keepalive owns fresh hosted CI/review;
closer owns exact topology, unchanged head, full threads, seven-minute review
floor, guarded merge, actual comparison and bounded acceptance disposition.
