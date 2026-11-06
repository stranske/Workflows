# Current shebang-rejection validation receipts

Current validation receipts for full-repository Black, focused Ruff, strict template completeness, and git diff --check. Historical README.md, summary.json, proof.tar.gz, path-lookup/, and replay-validation/ are earlier receipts. acceptance-run/ retains the eight-case pytest and replay commands.

Check date: 2026-11-06
cwd: `/home/runner/work/Workflows/Workflows`
Python: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3` (3.14.10 (main, Oct 26 2026, 14:17:03) [GCC 15.2.0])
Black: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/black`
Ruff: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/ruff`

Measured file counts:
- Black files left unchanged: 923
- Focused Ruff paths: 11
- Workflow directory YAML files: 130
- Template workflow YAML files: 35
- Manifest workflow targets: 35
- Strict validation input files: 166

Commands and exits:
- `/opt/hostedtoolcache/Python/3.14.10/x64/bin/black --check --line-length 100 --exclude (\.workflows-lib|node_modules) .` exit 0
- `/opt/hostedtoolcache/Python/3.14.10/x64/bin/ruff check docs/evidence/issue-3743/shebang-rejection/capture_acceptance_run.py docs/evidence/issue-3743/shebang-rejection/capture_validation_run.py docs/evidence/issue-3743/shebang-rejection/inspect_main_acceptance.py docs/evidence/issue-3743/shebang-rejection/replay.py scripts/check_deliberate_break.py templates/consumer-repo/scripts/check_deliberate_break.py tests/scripts/test_check_deliberate_break_shebang_rejection.py tests/scripts/test_shebang_rejection_acceptance_inspection.py tests/scripts/test_shebang_rejection_acceptance_run.py tests/scripts/test_shebang_rejection_replay.py tests/scripts/test_shebang_rejection_validation_run.py` exit 0
- `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3 scripts/validate_template_completeness.py --workflows-dir .github/workflows --template-dir templates/consumer-repo/.github/workflows --manifest .github/sync-manifest.yml --source sync-manifest --strict` exit 0
- `git diff --check` exit 0

Health 70 (.github/workflows/health-70-validate-sync-manifest.yml) documents scripts/validate_template_completeness.py --workflows-dir .github/workflows --template-dir templates/consumer-repo/.github/workflows --manifest .github/sync-manifest.yml --source sync-manifest --strict. docs/orchestrator/consumer-sync-contract-map.md also documents --strict --source sync-manifest. Health 73 documents --strict with the script defaults for those paths.
