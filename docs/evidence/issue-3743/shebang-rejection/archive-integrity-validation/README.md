# Archive member integrity follow-up

This run closes an inspection gap in `verify_archives.py`: duplicate member names
(including duplicate manifests), directories and links could previously pass
verification, and an unlisted regular file raised `KeyError`. The verifier now
rejects these inventories. Ten regression cases include a valid archive and
archives with missing files or incorrect member hashes and lengths. Each fixture
has matching outer archive hashes, so those hashes cannot hide inventory defects.

`summary.json` binds the current verifier, tests and recorded inputs by SHA256 and
byte length. `manifest.json` binds every other receipt file in this directory.
Raw command records include argv, cwd, environment overrides, exit, duration and
console output; focused and companion runs also retain raw JUnit. The archive
report verifies all four existing archives and their current input bindings.
Existing receipts, archives, production helpers, the eight-case test module and
`replay.py` remain unchanged from the base commit recorded in the summary.

The installed interpreter is
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`. The literal acceptance
interpreter `/opt/anaconda3/bin/python3` is absent. Both literal commands were
attempted once with a 120-second limit and returned exit 127 before any replay
output could be created. This run therefore does not establish those two literal
acceptance criteria. Earlier successful receipts remain records of their own
execution and are not substituted for these attempts.

Validation uses `-m "not slow"`: the focused module passes eight cases and the
seven companion modules pass 51 cases. Black checks the whole repository, Ruff
checks the 15 established paths, and strict template validation uses the
repository-documented `--source sync-manifest --strict` arguments. See the raw
receipts for results and the measured file counts in the summary.

The first multi-file Black invocation reached its time limit while waiting in
the event loop. Its raw receipt is retained as `black-initial.*`. The successful
`black.*` retry uses the same standard Black cache and checks all 927 files.
