# Current shebang-rejection validation receipts

Current validation receipts for full-repository Black, focused Ruff, strict template completeness, and git diff --check. Historical README.md, summary.json, proof.tar.gz, path-lookup/, and replay-validation/ are earlier receipts. acceptance-run/ retains the eight-case pytest and replay commands.

Check date: 2026-11-06
cwd: `/Users/teacher/.codex/orchestrator/worktrees/stranske__Workflows__4472__closer`
Python: `/opt/anaconda3/bin/python3` (3.12.2 | packaged by conda-forge | (main, Feb 16 2024, 20:54:21) [Clang 16.0.6 ])
Black: `/opt/anaconda3/bin/black`
Ruff: `/opt/anaconda3/bin/ruff`

Measured file counts:
- Black files left unchanged: 928
- Focused Ruff paths: 15
- Workflow directory YAML files: 130
- Template workflow YAML files: 35
- Manifest workflow targets: 35
- Strict validation input files: 166

Commands and exits:
- `/opt/anaconda3/bin/black --check --line-length 100 --exclude (\.workflows-lib|node_modules) .` exit 0
- `/opt/anaconda3/bin/ruff check docs/evidence/issue-3743/shebang-rejection/capture_acceptance_run.py docs/evidence/issue-3743/shebang-rejection/capture_validation_run.py docs/evidence/issue-3743/shebang-rejection/compare_matched.py docs/evidence/issue-3743/shebang-rejection/inspect_main_acceptance.py docs/evidence/issue-3743/shebang-rejection/replay.py docs/evidence/issue-3743/shebang-rejection/verify_archives.py scripts/check_deliberate_break.py templates/consumer-repo/scripts/check_deliberate_break.py tests/scripts/test_check_deliberate_break_shebang_rejection.py tests/scripts/test_shebang_rejection_acceptance_inspection.py tests/scripts/test_shebang_rejection_acceptance_run.py tests/scripts/test_shebang_rejection_archive_bindings.py tests/scripts/test_shebang_rejection_matched_comparison.py tests/scripts/test_shebang_rejection_replay.py tests/scripts/test_shebang_rejection_validation_run.py` exit 0
- `/opt/anaconda3/bin/python3 scripts/validate_template_completeness.py --workflows-dir .github/workflows --template-dir templates/consumer-repo/.github/workflows --manifest .github/sync-manifest.yml --source sync-manifest --strict` exit 0
- `git diff --check` exit 0

Health 70 (.github/workflows/health-70-validate-sync-manifest.yml) documents scripts/validate_template_completeness.py --workflows-dir .github/workflows --template-dir templates/consumer-repo/.github/workflows --manifest .github/sync-manifest.yml --source sync-manifest --strict. docs/orchestrator/consumer-sync-contract-map.md also documents --strict --source sync-manifest. Health 73 documents --strict with the script defaults for those paths.
