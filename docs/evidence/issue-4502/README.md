# Three-module coverage evidence

The 18 new cases in the three requested test files pass, and each fails under its
documented deliberate break and passes after exact byte restoration. The bounded
suite increased from 250 to 268 passing cases. All three production modules are
unchanged. No production defect was demonstrated or correction made.

Two requirements remain open: the first task's requested issue-format document
cannot be inspected because that path is absent, and full CI must pass. The
remaining preflight information was recorded before test edits in `preflight.md`.

The bounded before/after measurement is **21 → 0 missing units**. The full Gate
measurement is **2 → 0 missing units**. These are different populations and must not
be substituted for one another. Metrics already had 100% measured coverage; its
new test checks mixed escalation records sharing the same PR/follow-up identity,
without claiming a coverage reduction. There are no remaining locations in the
bounded final measurement that need an exercise-limitation explanation.

Baseline branch SHA: `b25657e57ec09b90f6bac8fa5d892f822b3bc34c`.
Current main at preflight: `e621d8f0ed8b83b9648b7fa8577b4f236bd57f1d`.
The three modules, original target test files, pyproject, and both relevant Gate
workflows are byte-identical between those SHAs. The complete repository trees
are not asserted identical. A final branch commit SHA is not available: Git
metadata is mounted read-only, and the connector rejected GitHub writes because
approval policy is `never`. Record that SHA in the PR body after committing the
prepared payload. The same approval block prevented a `needs-human` label and
blocker comment from being published.
Runtime: Python 3.14.10, pytest 9.2.0, pytest-cov 7.1.0, coverage 7.17.2,
pytest-xdist 3.8.0. Instrumentation uses the existing pyproject branch/source/
omit/exclude settings. No new exclusion or pragma was added.

| Target | Gate before statements / branches | Gate after statements / branches | Bounded before statements / branches | Bounded after statements / branches |
| --- | ---: | ---: | ---: | ---: |
| aggregate_agent_metrics.py | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| check_consumer_sync_drift.py | 2 / 0 | 0 / 0 | 2 / 0 | 0 / 0 |
| validate_run_contract.py | 0 / 0 | 0 / 0 | 12 / 7 | 0 / 0 |
| Combined | 2 | 0 | 21 | 0 |

Bounded missing statements before:

- `check_consumer_sync_drift.py`: 920, 921 (repository metadata transport failure).
- `validate_run_contract.py`: 148, 758–763, 775, 820, 824, 827, 828.
- `aggregate_agent_metrics.py`: none.

Bounded missing branches before, in `validate_run_contract.py`:
145→148, 326→328, 730→733, 755→758, 774→775, 819→820, 826→827.
Other targets have no missing branches. Full Gate before misses only drift
statements 920 and 921. The [Gate baseline inventory](gate-before/inventory.json)
and [shared final inventory](target-after/inventory.json) list each missing
statement and branch. The shared inventory is byte-identical to the
[original Gate final copy](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/gate-after/inventory.json).
Restore that path offline from the repository root with this command.

```bash
cp docs/evidence/issue-4502/target-after/inventory.json docs/evidence/issue-4502/gate-after/inventory.json
```

The historical 226-unit baseline is a separate historical observation from
#4423, not this branch's starting point. The bounded final count is 226 units
below that historical number, but only 21 units are attributable to this round
in the bounded comparison and two in Gate. Gate's before count was already 224
below 226. All final targets measure 100% statement and branch coverage in both
populations. There are no remaining missing units to explain.

## Commands and artifacts

See [preflight.md](preflight.md), created before test edits, for the concrete
Gate job, exact expanded pytest command, bounded acceptance command, current-main
SHA and missing-document/extractor recovery details. The extractor was restored
verbatim from #4423's recorded head: its Git blob remains
`9c2f2a054db24a0027d85bb89671bd49012325cb`.

The Gate observer can be prepared without editing workflow files:

```bash
mkdir -p /tmp/issue-4502-plugin
python - <<'PY'
from pathlib import Path
import yaml
workflow = yaml.safe_load(Path('.github/workflows/reusable-10-ci-python.yml').read_text())
step = next(s for s in workflow['jobs']['tests']['steps'] if s.get('id') == 'pytest')
plugin = step['run'].split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
Path('/tmp/issue-4502-plugin/ci_test_growth.py').write_text(plugin + '\n')
PY
export PYTHONPATH="/tmp/issue-4502-plugin:$PWD"
```

Use the full Gate command from preflight after that preparation. The local runs
redirect JUnit/XML/JSON/log output to `/tmp/issue-4502/gate-before` and `gate-after`;
test selection, worker count/distribution, observer and coverage config are the
configured Gate values. The first run additionally set an absolute COVERAGE_FILE,
which exposed the finalization problem described below; the final run uses
coverage's default data location.

Each `*.gz` is a complete file, not a target-only summary or reconstructed
term-report row. `artifact-manifest.json` records compressed and uncompressed
SHA-256 digests and original byte sizes. To reproduce the JSON extraction:

```bash
gzip -dc docs/evidence/issue-4502/target-after/coverage.json.gz > /tmp/issue-4502-coverage.json
gzip -dc docs/evidence/issue-4502/target-after/coverage.xml.gz > /tmp/issue-4502-coverage.xml
python docs/evidence/issue-4001/extract_target_coverage.py /tmp/issue-4502-coverage.json
```

Replace `target-after` with the desired phase. The full Gate artifacts are stored
under `gate-before` and `gate-after`. XML has less detail than JSON: it identifies
missing branch exits on source lines, while JSON retains destination arcs.
An independent count cross-check, after decompressing both files as above:

```bash
python - <<'PY'
import json
from pathlib import Path
from defusedxml import ElementTree as ET
data = json.loads(Path('/tmp/issue-4502-coverage.json').read_text())
root = ET.parse('/tmp/issue-4502-coverage.xml').getroot()
for name in ('aggregate_agent_metrics', 'check_consumer_sync_drift', 'validate_run_contract'):
    entry = data['files'][f'scripts/{name}.py']
    matches = [c for c in root.iter('class')
               if c.get('filename') in (f'{name}.py', f'scripts/{name}.py')]
    assert len(matches) == 1
    lines = list(matches[0].iter('line'))
    statements = sum(int(line.get('hits')) == 0 for line in lines)
    branches = 0
    for line in lines:
        if line.get('branch') == 'true':
            counts = line.get('condition-coverage').split('(')[1].rstrip(')')
            covered, total = map(int, counts.split('/'))
            branches += total - covered
    assert (statements, branches) == (
        entry['summary']['missing_lines'], entry['summary']['missing_branches']
    )
    print(name, statements, branches)
PY
```

## Deliberate-break evidence

The nine manifest-bound `.md.gz` files under `mutations/` hold the complete
deliberate diff, exact named pytest command, failing output, exact reverse
diff, restored SHA-256, and passing output for all 18 cases.

Read an original Markdown transcript on GitHub or recreate the same view
offline from its compressed file. The view removes trailing whitespace
from each line. The compressed original keeps it.

| Original Markdown view | Rendered SHA-256 |
| --- | --- |
| [`test_consumer_mirror_enforces_catalog_timestamp`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_consumer_mirror_enforces_catalog_timestamp.md) | `7e396290d97ed3bbb960b6f1831e7d4b7012675e33b11c25727d4e8a713dba98` |
| [`test_consumer_schema_fails_closed_without_required_format`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_consumer_schema_fails_closed_without_required_format.md) | `ed71c39e0b8cbde90aabe7bf523133f90433d63d95abcbc7bec975d87c7817e8` |
| [`test_main_caches_failed_blob_reads_by_repo_and_sha`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_main_caches_failed_blob_reads_by_repo_and_sha.md) | `92edd2c3af34862a34fdf1cef0738866f00547c779b7a095cdf7ad3f726d4e8f` |
| [`test_main_persists_valid_run_conformance`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_main_persists_valid_run_conformance.md) | `31c72d3e606b6f889f384361f8c95d57e575967223e9f565a7cafaf3c4f1527e` |
| [`test_main_rejects_unreadable_artifact_manifest`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_main_rejects_unreadable_artifact_manifest.md) | `2770e544c7f426b7518a4d03906927d0849f2129a8144f4b59bc5242821ec762` |
| [`test_mirror_cli_reports_without_optional_output_files`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_mirror_cli_reports_without_optional_output_files.md) | `891b071d2676a3f6680aa112a8ddc503b4593c7b617e42d8f3b305d03696073a` |
| [`test_remote_tree_transport_failure_preserves_unknown`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_remote_tree_transport_failure_preserves_unknown.md) | `1ba57188f10bd0a6dde3193fd4254579a1b0c0f3bca45706e49257605c4295a4` |
| [`test_self_smoke_rejects_incomplete_schema_inventory`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_self_smoke_rejects_incomplete_schema_inventory.md) | `78e405da97779bc0559476b67d7d4a7e09dd83bedfdee301d740c625b1c58a8b` |
| [`test_verifier_ledger_counts_escalations_without_duplicating_shared_followups`](https://github.com/stranske/Workflows/blob/49a88b3776e7cc60d13c670d52c81b8303dfec0a/docs/evidence/issue-4502/mutations/test_verifier_ledger_counts_escalations_without_duplicating_shared_followups.md) | `15f6bd737767aca7f0afd6d9fff23193aa391d8f70bc70c6965114d6d54316ee` |

From the repository root, set `transcript` to any one of the nine
`.md.gz` files. This example writes the restored view to a temporary file.

```bash
transcript=docs/evidence/issue-4502/mutations/test_consumer_mirror_enforces_catalog_timestamp.md.gz
view=$(mktemp "${TMPDIR:-/tmp}/issue-4502-view.XXXXXX")
python -c 'import gzip, sys; print("\n".join(line.rstrip() for line in gzip.open(sys.argv[1], "rt", encoding="utf-8").read().splitlines()))' "$transcript" > "$view"
shasum -a 256 "$view"
printf '%s\n' "$view"
```

To reproduce the original 18 fail/pass pairs, run
`python docs/evidence/issue-4502/run_mutation_probes.py` from a disposable
checkout of the [capture revision](https://github.com/stranske/Workflows/tree/49a88b3776e7cc60d13c670d52c81b8303dfec0a).
Run it without another pytest process using these modules. The probe driver
writes fresh compressed transcripts and restores the source bytes in `finally`.

Source SHA-256 before/after all probes:

- drift: `4a339397f54b680719432f7d2a4fd136d7bdd40b2ad3dd267170c61c7eeb26c5`
- contract: `5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa`
- metrics: `e03bd53293d5627de350405f9dcfdda966b9071c7954c59241ced4cbf12bd1df`

## Full-suite limitations

The baseline Gate invocation ran all 15,841 selected cases: **85 failed, 15,728
passed, 25 skipped, 3 xfailed**, in 364.12s. Its exit status was 3 because coverage
finalization subsequently hit `Can't combine branch coverage data with statement
data`. An inherited absolute COVERAGE_FILE allowed nested test invocations to
write statement-only data into the same location. The complete original log and
JUnit are retained; JUnit includes the failures omitted from pytest's interrupted
terminal summary.

The baseline JSON/XML were recovered from all five retained branch-data files
(controller plus four workers), without the separate two-file statement-only
database. Recovery used coverage 7.17.2 `Coverage(config_file='pyproject.toml')`,
`combine(data_paths=[all five branch files], keep=True)`, then `json_report` and
`xml_report`. This is a recovered measurement from a failing full-suite run,
not a passing hosted Gate receipt. No target counts were reconstructed from
rounded percentages. The final invocation drops the absolute data-file override.

Failures include read-only inherited GitHub output paths, denied socket/network
operations, and unrelated verifier/lifecycle assertions. They do not justify
changing protected workflows or unrelated production behavior in this coverage
task. No test was skipped, disabled or newly marked. CI success remains an open
acceptance requirement until the repository-configured jobs pass on the final
head in the supported runner.

The final full invocation completed normally with exit 1: **83 failed, 15,748
passed, 25 skipped, 3 xfailed**, in 420.20s. Its configured JSON/XML reports were
written directly by pytest-cov, with no recovery. All 18 new cases pass in that
run. Comparing complete JUnit inventories finds **no new failing nodes**; two
instrumentation tests and the baseline internal-error testcase are gone from the
failure inventory. `failure-comparison.json` retains every baseline/final failure
node. This confirms the scope of local regressions without asserting that the
83 pre-existing failures can be ignored by CI.

## Formatting validation

Black 26.10.1's concurrent dispatcher stalled in this sandbox: a diagnostic stack
showed an idle executor and the event loop waiting for completion notifications.
The required whole-repository command passed with a temporary sequential
dispatcher calling Black's own `reformat_one` for every discovered file. Its
parser, mode, AST safety check, exclusions and return-code reporting are unchanged.
The GitHub output path was redirected to writable temporary storage. Result:
**1,008 files would be left unchanged, exit 0**, retained in `black-check.log`.
Ruff passed on the three test files and the recovered extractor/probe script.

The temporary formatter adapter, outside the checkout, was:

```python
import black
import black.concurrency

def reformat_many(*, sources, fast, write_back, mode, report, workers,
                  no_cache=False, cache_dir=None):
    for src in sorted(sources):
        black.reformat_one(src=src, fast=fast, write_back=write_back, mode=mode,
                           report=report, no_cache=no_cache, cache_dir=cache_dir)

black.concurrency.reformat_many = reformat_many
```

Saved as `/tmp/issue-4502/black-serial/sitecustomize.py`, it was used with:

```bash
PYTHONPATH=/tmp/issue-4502/black-serial \
BLACK_CACHE_DIR=/tmp/issue-4502/black-cache \
GITHUB_OUTPUT=/tmp/issue-4502/black-output \
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```
