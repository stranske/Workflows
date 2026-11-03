# Issue 4019 closer repair acceptance

Check date: 2026-11-03. Outcome 1 is a comparable real CI artifact baseline
above 90%, with the existing repair tests discriminating and both active review
threads resolved. No additional coverage targets are warranted if baseline >=90%.

Baseline input: Gate run 41557902073, artifact gate-coverage-3.14-1,
`runtimes/3.14/coverage.json`; head input: Gate 41572375259, same artifact/path.
Command that prints the baseline outcome (after `gh run download`):

```sh
/opt/anaconda3/bin/python3 -c 'import json; d=json.load(open("/tmp/4019-base-pr/runtimes/3.14/coverage.json"))["totals"]; n=d["num_statements"]+d["num_branches"]; c=d["covered_lines"]+d["covered_branches"]; print("OUTCOME_1", c/n >= .9, c, n, 100*c/n)'
```

Acceptance commands, recorded before test edits:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/tools/test_llm_provider.py
```

For changed targets, use Gate's coverage flags and marker, restricting selection
to the above three files: `-m 'not quarantine and not slow' --junitxml=... --cov
--cov-config=pyproject.toml --cov-report=xml:... --cov-report=term-missing
--cov-report=json:... -n 4 --dist=loadgroup`. Gate also supplies `-n auto --dist
load` before its final four-worker loadgroup override. Full repository collection
runs in hosted Gate only. Local focused coverage is diagnostic, never a substitute
for comparable whole-CI counts. Each added node is run under its own behavior
mutation and after exact-byte restoration, with a 120-second subprocess timeout.

Stop rule: two failed repair attempts per finding or 75 minutes elapsed. Stop at
the first broken step and report it. Blocking/drainable pair: unresolved review
blocks merge / fixing and proving each finding drains it while the PR stays open.
CI pending blocks delivery / hosted CI runs while evidence is prepared. No lock,
review hold, or permit is created by this document.
