# Silent API failure triage

A required GitHub API write must fail the job when it cannot complete. For example, the label sync collects errors across repositories, reports the affected targets and calls `core.setFailed`. An ancillary operation may carry an inline `# best-effort:` annotation explaining which result remains authoritative if the request fails. [Label sync implementation](../../.github/workflows/maint-69-sync-labels.yml)

## Inspect this checkout

From the repository root, use the repository Python environment to list each matching workflow, job, step and recorded rationale. The same scanner serves the hosted sources and consumer templates. It checks inline `actions/github-script` steps that catch a REST or request error without calling `core.setFailed`. Review each rationale when its operation changes.

```bash
python - <<'PY'
import re
from runpy import run_path

guard = run_path("tests/workflows/test_no_silent_api_failures.py")
for path, job, step, body in guard["_candidate_steps"]():
    reasons = re.findall(r"#[ \t]*best-effort:[ \t]*(\S[^\n]*)", body)
    print(f"{path} | {job} | {step} | {' / '.join(reasons) or 'MISSING RATIONALE'}")
PY

python -m pytest -q tests/workflows/test_no_silent_api_failures.py::test_scripted_api_blocks_either_fail_or_are_annotated
```

The original issue audit records the workflow, block, classification and rationale at its reviewed revision. It includes entries for workflows subsequently retired. [Original triage table](https://github.com/stranske/Workflows/blob/00f43f81e51c4f8b9a057ac51f7e3c2d870d7769/docs/workflows/silent-api-failure-triage.md) · [Issue #3017](https://github.com/stranske/Workflows/issues/3017)
