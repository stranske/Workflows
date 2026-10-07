# Zero-selected scenario topology recovery

Workflows#3786 at5a0ccc5332ec2d39455172ac7848b197b1cc73d7 completed Gate37554734403 successfully. The approved shared reporter nevertheless returnsUNKNOWN: `selftest-reusable-ci.yml: invalid include-only matrix on scenarios`. Its own independently verified actual scenario producer receipt from run37554734623 recomputes `{"include":[]}`; GitHub reports `Scenario - ${{ matrix.name }}` as skipped. The reporter rejected that legitimate empty selection before consulting the skipped caller.

Handle only the existing supported dynamic scenario producer after all immutable helper/workflow/run/attempt/path-input witnesses and independent recomputation have passed. Require exactly one skipped caller with the authored unexpanded name, current run/attempt, and check-run URL; retain that check in the expected set and record its absence witness. Empty literal matrices and unverified, forged, missing, duplicate, successful or mismatched skipped-caller witnesses remainUNKNOWN. No general matrix relaxation or merge waiver.

The actual regression fails on incumbent source at `invalid include-only matrix on scenarios`, then228reporter tests pass with the repair. `before-red.txt` and `green.txt` retain complete command output. Commands:

```sh
python -m pytest tests/test_check_checks_reported.py -q -k empty_witnessed
python -m pytest tests/test_check_checks_reported.py -q
python -m black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
python -m ruff check scripts/check_checks_reported.py tests/test_check_checks_reported.py
```

Black left664files unchanged; Ruff passed. This follow-up addresses merged reporter#3791 completion debt and unblocks #3786 topology interpretation. It does not reopen broad issue3757, change workflow execution or assert that an unmerged candidate reporter authorizes merging another PR. Full expected/required checks, zero active threads, unchanged head and seven-minute review floor remain mandatory.
