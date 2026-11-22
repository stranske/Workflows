# Module-identity QA records

The 29 receipts below remain browsable at the original Git revision. The
[historical phase guide](README.md), [phase manifest](manifest.json),
[parent manifest](../manifest.json), and
[earlier replay archive](replay-artifacts.json.gz) remain at their original paths.

## Restore the original file layout offline

From the repository root, with the repository-selected Python active, run this
command. Set `WORKFLOWS_PYTHON` to the interpreter path if you use a separate
environment.

```sh
(
  output=$(mktemp -d "${TMPDIR:-/tmp}/module-identity.XXXXXXXX") || exit 1
  "${WORKFLOWS_PYTHON:-python}" docs/evidence/issue-3743/runtime-probes/recover-module-identity.py "$output/module-identity-validation" &&
    printf '%s\n' "$output/module-identity-validation"
)
```

The [recovery script](../recover-module-identity.py) combines the
[29-member archive](../module-identity-metadata.tar.gz) with the 41 loose files.
It checks all 70 original paths and SHA-256 digests against the unchanged parent
manifest and also checks sizes and digests for 68 files listed in the phase
manifest. It restores into a new directory and leaves the checkout untouched.
The restored directory contains the original filenames, including the intact
earlier replay archive. The recovery reads the outer archive only.

## Original files

- [baseline.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/baseline.command.json)
- [baseline.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/baseline.json)
- [baseline.xml](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/baseline.xml)
- [black-all.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/black-all.command.json)
- [black-focused-driver.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/black-focused-driver.command.json)
- [black-focused-tests.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/black-focused-tests.command.json)
- [black-format-driver.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/black-format-driver.command.json)
- [black-format-tests.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/black-format-tests.command.json)
- [black-serial.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/black-serial.command.json)
- [candidate.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/candidate.command.json)
- [candidate.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/candidate.json)
- [candidate.xml](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/candidate.xml)
- [comparison.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/comparison.json)
- [diff-check.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/diff-check.command.json)
- [driver-suite.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/driver-suite.command.json)
- [driver-suite.xml](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/driver-suite.xml)
- [module-control.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/module-control.json)
- [module-green.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/module-green.command.json)
- [module-green.xml](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/module-green.xml)
- [module-red.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/module-red.command.json)
- [pr-readiness.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/pr-readiness.json)
- [production-replay.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/production-replay.command.json)
- [ruff.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/ruff.command.json)
- [runtime-suite.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/runtime-suite.command.json)
- [runtime-suite.xml](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/runtime-suite.xml)
- [source-provenance.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/source-provenance.json)
- [staged-diff-check.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/staged-diff-check.command.json)
- [template-completeness.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/template-completeness.command.json)
- [template-sync.command.json](https://github.com/stranske/Workflows/blob/9a0219f361e4ba4b9072a554362ef378ff47ec4c/docs/evidence/issue-3743/runtime-probes/module-identity-validation/template-sync.command.json)
