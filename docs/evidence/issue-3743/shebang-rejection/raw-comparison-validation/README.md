# Raw comparison verification follow-up

The archive verifier now recomputes the matched comparison from raw JUnit and
coverage JSON using the existing comparison functions. It checks both stored
comparison copies and enforces the eight-node and no-regression contract before
rendering an acceptance note. Eight new regression cases include an unchanged
summary, six altered summary fields, and collection with altered outcomes while
archive bytes stay unchanged.

Earlier receipts, including archive-integrity-validation/, describe their
recorded source bytes. This directory binds the current verifier and regression
tests. All existing archives, production helpers, acceptance-run/ and historical
receipts remain unchanged from the recorded base commit.

The literal /opt/anaconda3/bin/python3 interpreter is absent on this runner.
Both literal acceptance commands are attempted once with a 120-second limit.
Their exit 127 results do not establish literal acceptance. The available Python
path, commands, exits, raw JUnit and measured validation file counts are recorded
in summary.json and the command receipts. The reserved replay output is untouched.

Task reconciliation: the literal-command task and first two acceptance criteria
must remain unchecked for this runner. Updating PR #4472 was rejected because the
connector requires approval and this run uses approval policy never. The PR was
observed open and ready for review. The other implementations have retained
passing evidence; this change advances verification of the comparison and its
current input bindings without claiming the interpreter blocker is resolved.

Black's multi-file event loop stalls in this sandbox. The retained serial helper
runs Black's real single-file CLI checks to populate its ordinary writable cache;
the required full-repository command then independently checks that cache against
the current file bytes. No formatting rule or check is disabled.

manifest.json binds every other archive member by SHA256 and byte length.
summary.json stays outside proof.tar.gz and binds that archive and current inputs.

The final commit attempt failed before staging: `.git/index.lock` could not be
created because `.git` is mounted read-only. Source changes and verified receipts
remain in the working tree for a writable checkout to commit.
