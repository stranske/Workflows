# Release acceptance and closing-source controls

Both production fixtures were compared with GitHub PRs #3769 and #3787:
complete body, title, release branch and head SHA match (`fixture-parity.json`).
Trusted author/repository and transport responses remain synthetic test inputs.

The named suites now verify every fixture task and acceptance item survives in
the generated context. The acceptance inventory contains only the release PR
when no genuine issue source is declared. New #3787 controls append genuine
`Fix #123` and `Closes #123` directives, including an explicit local-request
declaration. Both source resolvers require issue #123; both real context builders
retrieve its acceptance or report required discovery unavailable for inaccessible
issues and PR-shaped responses. Body and title directives are covered by the
resolver controls. Existing Related-to, metadata, branch, ambiguity and malformed
source tests remain in the same suites.

The required command exits 0:

```sh
node --test .github/scripts/__tests__/source-context.test.js .github/scripts/__tests__/agents-verifier-context.test.js
```

Node 24 in this runner summarizes isolated files without individual test names.
The retained complete output adds `--test-isolation=none` to expose all named
tests (185 after the exact fixture-surface locks). Captured console lines have
trailing whitespace removed. The same two files are executed in both commands;
`receipt.json` records the commands and exit codes.

Independent root-only and consumer-only restoration of the merged `52712f28`
resolver reproduces `github_issue` #3782 and required discovery: 17 tests fail
in each experiment against the current suites. Each fixed-byte restoration
passes all 185 tests. RED/GREEN output, classifications and source hashes are
retained here; `fixed_sha256` matches current HEAD resolver bytes
(`28c230e58898d72cdcbe5842ca6eff57bdd1d2252cbced1bb2f2aec44aafd13d`).
Both parser and verifier-context `cmp` commands exit 0. Production code requires
no further change for these controls.

Template sync and completeness validation pass. Completeness uses
`GITHUB_STEP_SUMMARY=/tmp/release-template-summary.md` because the inherited
Actions summary path is read-only in the local sandbox. `git diff --check` passes.

Original runs 37400729553 and 37481681340 remain CONCERNS/NON_PASS. No provider
verdict or post-merge comparison is inferred from unit results. After merge,
Orphan Steward owns the single repaired-input comparison and complete artifact
inventory; source #3757 topology and observed provider verdicts remain required.


## Immutable manifest binding after PR #3800

`manifest.json` binds each entry to evaluated merge
`35552aa22e794fbed1a6ee59d4942ede66fa386e` through its explicit `revision` field.
Verify the exact blob at that revision rather than compare a historical test
hash with a later working tree. For each entry, the byte length and SHA256 are
of `git show <revision>:<path>`. No retained console, fixture, receipt or source
bytes were regenerated to change the outcome.

PR #3800 updated this directory's README, four complete RED/GREEN captures and
receipt, but left their earlier manifest hashes behind. Its test entries also
pre-dated the updated suites. `manifest-before-title-metadata-replay.json`
preserves that original manifest verbatim as historical, superseded metadata;
it is not the acceptance manifest for the replay delivered by PR #3800.
The replacement binds all 13 entries to the immutable evaluated merge, including
both complete test files and both root/template implementations. Later parser
repair PR #3807 is separate and does not change this historical binding.

The 2026-10-07 closer audit independently downloaded expanded comparison
37572459483 and release follow-up 37567257334. The expanded comparison remains
CONCERNS/CONCERNS and NON_PASS because its input omitted evidence. The release
follow-up's complete seven-file bundle records CONCERNS/PASS, NON_PASS and
`acceptance_source_discovery.required=false`; original baseline 37400729553
remains CONCERNS/CONCERNS, NON_PASS. No provider verdict is relabeled.

On audit main `7793e353f` the named resolver/builder command passed 190 tests;
receipt tests passed 20; the full JavaScript suite passed 2,077 with one existing
skip. Four actual root/template conflict/negation source mutations each exited
1, followed by exit 0 and byte-identical restoration. Those are current-main
checks; the 185-test historical transcript above belongs to its recorded
revision. They do not establish complete release topology or provider PASS.
