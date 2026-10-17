# Uploader optional-mirror validation

The uploader now consults an available advisor once even when other mirror tools
are missing. Missing authoring/propensity tools preserve approved bodies, record
which tools are missing, and retain the decline result. Malformed capability
lists also preserve the baseline. Tests forbid unstubbed subprocesses.

Verified source tasks (these do not update the remote PR checklist):

- [x] Once-per-batch `repo-review-uploader` consult with missing-mirror fallback.
- [x] Offered three-item role batches retain manifests and fall back per item.
- [x] Experiment-bound trigger/decline evidence uses created issue identities.
- [x] Regression coverage includes missing/partial mirrors, validation failures,
  missing role bodies, filters, deduplication, priority labels, and upload holds.
- [x] Optional role and retained failure evidence documented in
  `docs/ops/REPO_REVIEW_PROCESS.md`.

`python -m pytest tests/scripts/test_upload_repo_review_issues.py -q -m 'not slow'
--basetemp=/tmp/repo-review-uploader-proof` passed **38 tests** (`pytest-green.txt`).
`ruff check scripts/upload_repo_review_issues.py
 tests/scripts/test_upload_repo_review_issues.py` passed.

The three `role-case-*` directories retain raw stub manifests, selected-body
receipts and generated Markdown. Absolute paths in these raw receipts refer to
the original pytest temporary directories; matching Markdown files are copied
alongside each manifest:

| Case | Role output | Filed bodies in stubbed upload |
| --- | --- | --- |
| 0 | All valid | Three role bodies |
| 1 | Middle body marked invalid, failed file retained | Two role bodies plus approved original |
| 2 | Middle body incorrectly claimed valid | Uploader rejects it; two role bodies plus approved original |

`partial-mirror-0.json` and `partial-mirror-1.json` retain both missing-tool
outcomes. A failed propensity invocation is retained locally and does not claim
that an experiment was updated remotely.

`fallback-proof.json` identifies the exact source digest and commands for the
requested deliberate break. Removing the approved per-item fallback yielded
**two assertion failures** (`fallback-red.txt`). The source was restored byte for
byte, then all **38 tests passed** (`fallback-restored-green.txt`).

The required repository formatting gate passed with **790 files unchanged**:

```sh
PYTHONPATH=/tmp/uploader-black-runtime BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

`black-runtime.txt` retains the temporary startup helper used by this sandbox:
it adds event-loop wakeups to Black; formatting rules and file selection remain
unchanged. The ordinary multiprocessing invocation could not bind its worker
socket, and the single-worker invocation needed these wakeups.
`black-check-responsive.txt` retains the successful result.

No live batch, advisor, role dispatch or issue creation was performed. Tests use
stubbed local tools and remote identities. Existing approval/hold/dedup gates
remain in force. Real `acted_on` and 20-body downstream outcomes remain post-merge
acceptance. No original watchdog/final dates have been changed.

GitHub API access failed (`error connecting to api.github.com`), so the remote PR
body/checklist and ready-state verification could not be updated. These receipts
are retained for attachment to that PR when connectivity is available.
Staging and committing were also blocked by this environment's read-only `.git`
mount: `git add` failed to create `.git/index.lock`. Changes remain in the working
tree; no commit or push is claimed.
