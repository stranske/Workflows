# PR #3808 task reconciliation

Reviewed commits `5ba58717` and `1ba1f86e` and verified their retained receipts
before continuing. The existing tests and production mutation controls satisfy
the three original tasks and four acceptance criteria. Fresh receipts in this
directory also exercise the stricter replay driver.

- [x] Add fourteen root/template runtime-probe cases: the named suite passes
  fourteen cases with real child imports, sentinel decisions and exact exception
  preservation (`runtime-suite.xml`).
- [x] Run every named case against its production mutation and exact restoration:
  fourteen distinct RED exit 1 / GREEN exit 0 controls, complete raw console,
  JUnit, argv, cwd and hashes (`replay/controls.json`).
- [x] Compare the same source and branch coverage settings: 272 baseline tests
  and 286 candidate tests, complete coverage JSON and JUnit (`comparison.json`).
- [x] Runtime-probe acceptance: fourteen passes, real private fixture imports,
  FileNotFoundError/ENOENT/filename/cause preservation, and failed repair retaining
  its exact exception without rerunning (`runtime-suite.command.json`).
- [x] Replay acceptance: fresh output directory, fourteen distinct executed RED
  failures and GREEN passes, matching original/restored hashes, all phase receipts
  retained (`production-replay.command.json`, `replay/controls.json`).
- [x] Coverage acceptance: unchanged source universe, 591 statements, 262 branches,
  zero exclusions, covered lines 552 to 563 and branches 239 to 241; all tests pass
  with zero errors, failures or skips (`baseline.json`, `candidate.json`).
- [x] Source and validation acceptance: production root/template bytes equal each
  other and base `98b6ed3d`; focused/repository Black, Ruff, template sync,
  completeness and diff checks pass (command receipts and `source-provenance.json`).

These are local reconciled marks. The GitHub connector confirmed the PR is open
with `isDraft=false` at head `1ba1f86e`. Automatic approval review rejected the
PR-body update: "MCP tool call requires approval, but approval policy is never".
No remote checkbox update is claimed. The canonical Git metadata is read-only;
the source/test changes and receipts are committed using isolated metadata with
a bundle for handoff.
