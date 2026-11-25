# Fixes Documentation Index

This folder consolidates fix summaries and supporting materials.

## Current Entries

- [sparse-checkout-audit-2026-02-03.md](sparse-checkout-audit-2026-02-03.md) — Sparse-checkout dependency audit and fix summary
- [sparse-checkout-audit-2026-02-03.csv](sparse-checkout-audit-2026-02-03.csv) — Spreadsheet of affected workflows and status

## January 2026 integration-test incidents

The integration consumer exposed three distinct problems. Early runs failed on Black and Ruff formatting. Maint 70 provided a manual formatting path and Maint 71 added automated repair. A later dependency conflict required regenerating the lockfile after a Ruff pin changed. Runs 60 and 61 exposed a failure parsing the run ID and a validation script that had drifted from its template. [Formatting repair](https://github.com/stranske/Workflows/pull/594) · [Dependency repair](https://github.com/stranske/Workflows/pull/672) · [Template repair](https://github.com/stranske/Workflows/pull/841)

For a current incident, inspect the [integration sync source](../../.github/workflows/maint-69-sync-integration-repo.yml) and the [workflow catalog](../WORKFLOW_GUIDE.md). The [manual formatter](../../.github/workflows/maint-70-fix-integration-formatting.yml), [automated fixer](../../.github/workflows/maint-71-auto-fix-integration.yml) and [local formatting script](../../scripts/fix-integration-tests-formatting.sh) show the supported entry points.

To sync the integration repository immediately, run this command with an authenticated GitHub CLI. It dispatches Maint 69 on `main` and returns status 1 if the request fails. [Sync runs](https://github.com/stranske/Workflows/actions/workflows/maint-69-sync-integration-repo.yml)

```sh
(gh workflow run maint-69-sync-integration-repo.yml --repo stranske/Workflows --ref main || exit 1)
```

To request a formatting repair, use Maint 70 on the default branch. Set `format_subject` in your shell to supply a custom commit message. The command returns the GitHub CLI status. Follow the [formatting run](https://github.com/stranske/Workflows/actions/workflows/maint-70-fix-integration-formatting.yml) and check [integration CI](https://github.com/stranske/Workflows-Integration-Tests/actions) for the result.

```sh
(
  command -v gh >/dev/null || { echo "GitHub CLI (gh) is required." >&2; exit 1; }
  gh workflow run maint-70-fix-integration-formatting.yml --repo stranske/Workflows \
    -f "commit_message=${format_subject:-fix: Auto-format files to meet lint standards}"
)
```

To run the local script from Workflows, pass the path to the Workflows-Integration-Tests checkout.

```sh
bash scripts/fix-integration-tests-formatting.sh /path/to/Workflows-Integration-Tests
```

On a fresh Integration-Tests checkout, use Python 3.13 or newer to create and
activate an isolated environment, then install the receiver’s pinned dev extra:

```sh
python3 -m venv /path/to/Workflows-Integration-Tests/.venv
. /path/to/Workflows-Integration-Tests/.venv/bin/activate
python -m pip install -e '/path/to/Workflows-Integration-Tests[dev]'
```

The default formats only the two incident files with Black. To format the whole
checkout with Black and Ruff, run
`bash scripts/fix-integration-tests-formatting.sh --all /path/to/Workflows-Integration-Tests`.
The underscore-named script still runs full formatting from the Integration-Tests
root. Both entries use the tools already available in your environment.

The January patch reproduces the four files in the [landed integration repair](https://github.com/stranske/Workflows-Integration-Tests/commit/0994ab8223df4c9523690dc514063e4e0a089e0e). The April edit changed six lines of Python-version context. Both editions are in the [offline patch archive](integration-test-repair-2026.tar.gz).

| Edition | Archive member | SHA-256 |
| --- | --- | --- |
| [January original](https://github.com/stranske/Workflows/blob/6a1400231ed2624331ba2abd2490b5848cb8aaac/docs/integration-test-failure-fix.patch) | `january.patch` | `85ca2b15eb94af924d4c8095739efde26fd43027175c1808ecbbbd8c90face24` |
| [April revision](https://github.com/stranske/Workflows/blob/a9ce00e4e93563e55bf95147549d212ba997b393/docs/integration-test-failure-fix.patch) | `april.patch` | `a4bfc53430f02859808a4a4cf106d6ba8bd801b6df648e9f4d4d2b1697cb6867` |

To recover an edition from the Workflows checkout offline, select its member by name.

```sh
tar -xOzf docs/fixes/integration-test-repair-2026.tar.gz january.patch > fix.patch
shasum -a 256 fix.patch
```

Earlier incident reports preserve the commands, pins and test plan. [Root reports](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9) · [Documentation records](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9/docs) · [Run 60 and 61 records](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9/docs/fixes)

## February 2026 high-volume API audit

The [February report](https://github.com/stranske/Workflows/blob/c81cbdc78829bcea31191b323e0e9d82d3de80a6/docs/fixes/high-volume-workflows-api-audit.md) and [follow-up](https://github.com/stranske/Workflows/blob/395fba3dda6d18a65f50a1e0acbf509e3b0b9cab/docs/fixes/high-volume-workflows-api-audit.md) document the token load balancer and retry-wrapper rollout. The [last report edition](https://github.com/stranske/Workflows/blob/1c4bd2076047fce01066b098b34ac4f226caff10/docs/fixes/high-volume-workflows-api-audit.md) retains its workflow sections and the [recorded remediation plan](https://github.com/stranske/Workflows/blob/1c4bd2076047fce01066b098b34ac4f226caff10/docs/fixes/high-volume-workflows-api-audit.md#remediation-plan-recorded). Open the [71-row table](https://github.com/stranske/Workflows/blob/c81cbdc78829bcea31191b323e0e9d82d3de80a6/docs/fixes/high-volume-workflows-api-audit-table.csv) directly from this index.

The [offline audit archive](high-volume-workflows-api-audit.tar.gz) contains the last report edition and the original table at their original paths and Git mode `100644`.

| Member | Git blob ID | SHA-256 |
| --- | --- | --- |
| `docs/fixes/high-volume-workflows-api-audit.md` | `37de6be62844b98c2af65f3101844ed48efda02f` | `a5c4ade5103b645d5967cc8254ca7ea04f39e29d67b7eff84113efaf11f35f1f` |
| `docs/fixes/high-volume-workflows-api-audit-table.csv` | `7b05225ae136050cb08208fef982b4385e961515` | `6dab27776df197a725e2b85795182930bbfb574b517b2d44b4aad0b775253f94` |

Run from the repository root to recover and verify both files offline.

```sh
recovery=$(mktemp -d)
tar -xpzf docs/fixes/high-volume-workflows-api-audit.tar.gz -C "$recovery"
(cd "$recovery" && shasum -a 256 -c <<'SUMS'
a5c4ade5103b645d5967cc8254ca7ea04f39e29d67b7eff84113efaf11f35f1f  docs/fixes/high-volume-workflows-api-audit.md
6dab27776df197a725e2b85795182930bbfb574b517b2d44b4aad0b775253f94  docs/fixes/high-volume-workflows-api-audit-table.csv
SUMS
)
```

## February 2026 setup API client coverage

The [historical coverage table](../archive/audits/setup-api-client-coverage-audit.csv) records 60 entries across 56 workflows. Forty-four entries were marked `Unverified` during the rollout. For current guidance, see [API rate limit management](../ops/api-rate-limit-management.md). The [recorded remediation plan](RATE_LIMIT_REMEDIATION_PLAN.md) tracks its own checklist. [Pinned original table](https://github.com/stranske/Workflows/blob/699e5086acc590589adb262230a3cfef6d3f8f88/docs/fixes/setup-api-client-coverage-audit.csv)

Run from the repository root to recover the CSV at its original path and mode in a temporary directory.

```sh
recovery=$(mktemp -d)
mkdir -p "$recovery/docs/fixes"
install -m 0644 docs/archive/audits/setup-api-client-coverage-audit.csv "$recovery/docs/fixes/setup-api-client-coverage-audit.csv"
printf '%s  %s\n' ffe921a2bb43cc0a50e15d1e1b6c3a6f61e1a65f40eed7cae92fc0d252bf8f5e "$recovery/docs/fixes/setup-api-client-coverage-audit.csv" | shasum -a 256 -c
```

## November 2026 agent verification receipts

[PR #4470](https://github.com/stranske/Workflows/pull/4470) records how the [sentence-delivery test](../../tests/scripts/test_report_sentence_delivery.py) distinguishes a reported sentence in a PR comment from absent or unavailable evidence. [PR #4709](https://github.com/stranske/Workflows/pull/4709) records the deliberate break and restoration of the [queued-check ordering regression](../../tests/test_check_checks_reported.py).

| Original file at its recorded revision | Git blob ID | SHA-256 of the recovered bytes |
|---|---|---|
| [CONTINUATION_SUMMARY.md](https://github.com/stranske/Workflows/blob/42ca713e15cb7a0b290ab4ccb473c73740827a2f/CONTINUATION_SUMMARY.md) | `a0f0f53d07a627a748a572bff07edb43fef68da3` | `520713e88a5437aa17f2b804d583544f063317d59d5da7de578089c97aa171aa` |
| [EXACT_SENTENCE_RECORD.txt](https://github.com/stranske/Workflows/blob/42ca713e15cb7a0b290ab4ccb473c73740827a2f/EXACT_SENTENCE_RECORD.txt) | `2d806c787a9fabfc815611b1df32c10273a0e92f` | `4b67416d25b0394835e71c22932df3676d980fe573a5377ea8dfec38349c66e3` |
| [cursor-output-4709.md](https://github.com/stranske/Workflows/blob/51f9943bf3030134f20fe91a400ca2684d9cab5d/cursor-output-4709.md) | `f9d8f51bfa389806a7ed015803960b7ca4cb1044` | `ac2967efcaca1f7223a7d4ab1886cfd00346619401609d419f0b822687d4aab8` |

Use the commit and filename in each link to recover the bytes with `git show <commit>:<filename>`. Piping that output to `git hash-object --stdin` prints the Git blob ID.
