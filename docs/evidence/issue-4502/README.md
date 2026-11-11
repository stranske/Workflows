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
statements 920 and 921. The per-phase `inventory.json` files enumerate every
missing statement and branch, with the original coverage summary counts.

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

`python docs/evidence/issue-4502/run_mutation_probes.py` reproduces all 18 cases.
Run it without another pytest process using these modules. Each of the nine
transcripts under `mutations/` contains the complete deliberate diff, exact named
pytest command, all failing output, exact reverse diff, restored SHA-256, and
the same command's passing output. The matching `.md.gz` retains the complete
byte-for-byte transcript; Markdown removes trailing whitespace for lint only.
Every parameter case fails, not just
one case in each function. Restorations run in `finally` and preserve bytes.

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
