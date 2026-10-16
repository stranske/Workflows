# PR #3943 task reconciliation

Reviewed commits `3babd920` and `fccc1cc9` before adding replay regression tests.
The following implementation tasks were already complete and independently verified:

- [x] Real executable-file/PATH malformed launcher cases: eight root/template passes.
- [x] Eight exact assertion RED/restored GREEN pairs on private production copies,
  with byte-identical restoration and output reuse rejection.
- [x] Matched baseline/candidate JUnit and coverage, exact commands and exits,
  source/test/replay bytes, and lossless archive member manifests.

Both existing archives retain their original bytes. Their 122 historical and 151
PATH-proof manifest bindings verify. The existing matched comparison has 340
baseline passes and 348 candidate passes, exactly eight additions and no coverage
regressions. Production root/template helpers remain equal and unchanged from base.

This round adds fourteen replay regression cases: twelve invalid result cases,
restoration after failed RED validation, and a real eight-pair run followed by reuse
rejection before any source copy or checkout. Fresh receipts and current input
bindings are in `summary.json` and `proof.tar.gz` alongside this document.

Fresh verification: eight launcher passes, 21 replay-test passes, eight exact
assertion RED1/restored GREEN0 pairs, and all 93 proof files preserved on reuse.
Matched coverage again reports 340 baseline / 348 candidate passes, identical
1,244 statement / 556 branch universes, zero exclusions and no regressions.
The new archive verifies all 316 member hashes and byte lengths, plus its current
source/test/replay bindings. Full Black (754 files), focused Ruff, strict template
completeness and `git diff --check` each exit 0.

The two literal acceptance commands using `/opt/anaconda3/bin/python3` remain
unchecked: that interpreter is absent. Fresh runs record the installed Python 3.14
interpreter instead. Full Black uses the previously archived serial per-file
adapter because parallel worker completion hangs in this sandbox. Strict template
validation directs its step summary into writable `/tmp`.

The PR body update was rejected by automatic approval review with
`MCP tool call requires approval, but approval policy is never`. The prepared
replacement is retained at `/tmp/pr-3943-reconciled-body.md`; remote checkboxes
have not been updated by this run. No additional approval route was attempted.

The requested commit is also blocked: `git add` and `git commit` both failed
because `.git/index.lock` cannot be created on the read-only Git directory.
The tested source change and evidence remain in the working tree.
