# Follow-up resolver validation

The standard-permission follow-up adds 36 authored-resolver cases covering empty
or malformed manual inputs, valid and invalid immutable-index targets, and
origin run/attempt/head/event/producer mismatches. Summary and failure events
capture output snapshots, verifying that unresolved PR locks are empty before
the summary is published and remain empty when resolution fails. A failed
summary write likewise leaves every PR-target output cleared.

`round-validation.json` retains current source hashes and the actual commands,
logs and JUnit for **56 resolver passes** and **139 focused workflow passes**.
The required `node --test` command exits successfully but reports one file-level
case in this environment; the additional `--test-isolation=none` run exposes all
**29 passing classifier/replay cases**. Both logs are retained.

The original `manifest.json` and `mutation-receipt.json` describe the earlier
production mutation proof, including its original test revision. Their retained
artifact hashes and six-failure/six-pass JUnit results were verified, and both
current production workflow hashes still match the byte-identical restoration.
Production workflows were only read during this follow-up; the mutation was
not rerun under standard permissions.

Ruff, template sync and template completeness pass. Completeness writes its
summary to `/tmp` because the runner's summary destination is read-only. The
full Black 26.10.0 check passes for **698 files** with line length 100 and the
required exclusions. The sandbox blocks Black's default process-pool startup
and stalls its event-loop wakeups with a single worker; the retained launcher
adds periodic wakeups while leaving the installed CLI, formatting rules and
source selection unchanged. Its exact source and invocation are in the receipt.

The workspace's `.git` directory is read-only: staging fails when Git creates
`index.lock`. The follow-up commit is therefore created in an isolated bare
clone under `/tmp`, using the workspace as its work tree. The resulting
`round-commit.patch` can be applied to the PR branch in a writable checkout.
