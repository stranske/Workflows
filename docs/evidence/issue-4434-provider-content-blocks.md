# Provider content block regression evidence

Source PR: https://github.com/stranske/Workflows/pull/4438

- [x] The named formatter tests accept list-valued text blocks and fall back for
  responses containing only non-text blocks (19 parameterized cases passed).
- [x] Temporarily restoring `formatted = content.strip()` makes
  `test_format_issue_body_accepts_list_content_blocks[dict]` fail with
  `AttributeError: 'list' object has no attribute 'strip'`. The formatter was
  restored byte-for-byte before final validation.
- [ ] After merge, the existing source owner reruns auto-pilot on issue #4364
  and confirms the Format step succeeds and the step-2 comment appears.
- [ ] Live acceptance: remove and re-add `agents:auto-pilot` on issue #4364,
  then inspect the resulting job and issue comment.

The fallback regression now includes valid formatted issue Markdown inside
tool, reasoning, and media blocks, including dictionary and object `content`
fields. These cases establish that block-type filtering rejects the response
even when its text could pass formatted-output validation.

## Validation on 2026-11-04

```bash
python -m pytest -q tests/scripts/test_issue_formatter.py \
  tests/scripts/test_pr_verifier_structured_output.py -m 'not slow' \
  -o $'filterwarnings=error\nignore:.*asyncio.iscoroutinefunction.*:DeprecationWarning'
```

Result: **137 passed**. The installed LangSmith plugin emits this Python 3.14
deprecation warning during pytest startup. The command filters only that warning;
other warnings remain errors. Installing the lockfile's LangSmith version was
blocked by unavailable network access.

`ruff check tests/scripts/test_issue_formatter.py` and `git diff --check` passed.

```bash
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/workflows-black-cache \
  black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Result: **888 files would be left unchanged**. Sandbox restrictions blocked the
default process pool and stalled event-loop completion delivery with one worker.
An in-process periodic wakeup allowed Black to check the files and populate its
normal cache; the command above then passed without that workaround.

The live steps remain pending: PR #4438 was open, unmerged, and ready for review
when inspected. Its pre-merge unit results do not establish hosted recovery.
The environment mounts `.git` read-only, blocking staging and committing.
The GitHub tool also blocked the PR checkbox update because it requires approval
and this run's approval policy is `never`.
