# Module operand boundary coverage for #3743

This is the next test-only chunk after merged #3814. The broader coverage issue remains open. Production root and consumer helper bytes are unchanged and identical.

The last 400 scripts-touching commits rank `check_deliberate_break.py` first: 73 repair-subject matches and 82 touches. This is a churn/repair proxy, not a verified escaped-defect count. A fresh baseline identifies uncovered operand boundaries at lines 551, 615 and 617–618.

The six root/consumer cases prove that `uv run -- python -m pytest` probes its selected Python runtime and imports a private YAML module, while `uv run --module python -m pytest` and `python -m compileall -m pytest` never launch a probe. Each new case fails under its own corresponding production mutation and passes after byte-identical restoration. There is no package installation or network access.

## Observed validation

- Matched existing helper suites: 294 baseline PASS, 300 candidate PASS; exactly six new JUnit nodes, zero changed old outcomes.
- Root helper coverage: 570/591 to 576/591 statements; 243/262 to 248/262 branches; zero exclusions and zero covered-line regressions.
- Six individual production mutations: RED exit 1, restored GREEN exit 0. Both production hashes remain `cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`.
- Reusing the replay output path fails before mutation and preserves all existing evidence/source hashes.
- Full Black check (680 files), focused Ruff, template completeness and `git diff --check` pass.

Coverage metrics deliberately describe only the root helper. Repository `.coveragerc` source selection overrides the collection include option; the raw warning and full original reports are retained. Consumer behavior has direct paired tests and mutation proof, but no separately measured consumer coverage is claimed. Neither these metrics nor CI establishes repository-wide 90%, native provider PASS or source completion.

## Reproduce

Use Python 3.12 or newer with pytest installed. Replay mutates only a private temporary copy of the two sources and test module, then removes it; caller edits are never restored or overwritten.

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break_module_boundaries.py -q -o addopts=
python3 docs/evidence/issue-3743/module-boundaries/replay.py --output /tmp/fresh-module-boundary-proof
```

`validation.tar.gz` preserves all six RED/GREEN consoles and JUnit reports, complete matched coverage JSON/JUnit/consoles, argv/cwd/exits and validation logs. `manifest.json` binds every archive member and source/test/replay/summary file by SHA256. `summary.json` records the exact base, ranking, added nodes and covered-line/branch delta. Ordinary main already implements this behavior; explicit production mutation is the sensitivity control, not a claim that tests should fail on unchanged main.
