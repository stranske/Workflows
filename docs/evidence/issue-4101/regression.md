# Issue #4101: hosted Cursor startup recovery

## Observed failure

Read `gh run view 39140716928 -R stranske/Orchestrator --log-failed`
before changing the source. The failed `Cursor (keepalive)` job used Workflows
revision `6b3cf8015b48f60c64bcf538ce860d9967fa1e66`.
Its task-appendix download failed at 2026-10-18T15:30:51Z. Normal success-gated
Cursor cache/auth/install steps were skipped, but `Run Cursor` used `always()`.
The worker therefore expected `cursor-agent` on PATH without installing it and
reported exit 127, `cursor-agent: command not found`. The log does not demonstrate
a bad archive download or an incompatible Cursor binary.

The vendor installer at `https://cursor.com/install`, inspected on 2026-10-18,
uses the pinned `2026.10.16-e3cb207` archive under
`https://downloads.cursor.com/lab/<version>/linux/<arch>/agent-cli-package.tar.gz`
and exposes its `cursor-agent` through `$HOME/.local/bin`.
The reusable workflow retains that pinned archive and its bounded runner-temp
cache, exports the install directory, and adds a strict executable/version
preflight. Setup now explicitly handles earlier step failures.

## Initial implementation verification (before PR #4103 fix round)

- Full `pytest tests/workflows -q -x`: **2,821 passed, 10 skipped** in 321.50 seconds
  with the sandbox runtime adjustment documented below. Skips cover six
  GNU/Bash-only cases, three privilege-gated cases, and one live GitHub probe.
- Delegation, intake and keepalive JS regressions: 368 passed.
- Executed Cursor shell preflight and runner-cache regressions: 22 passed.
- Template sync: all files already in sync. Template completeness passed.
- Root/template copies of `agent_delegation_policy.js` and `keepalive_loop.js`
  are byte-identical. The sync manifest is unchanged.
- Workflow syntax/action checks passed with `actionlint -ignore SC2129`.
  Unfiltered actionlint reports the same five SC2129 redirect-grouping style
  warnings on both the starting main revision and this change.

Commands:

```sh
PYTHON=/opt/anaconda3/bin/python3 node --test \
  .github/scripts/agent_delegation_policy.test.js \
  .github/scripts/__tests__/agent-delegation-policy.test.js \
  .github/scripts/__tests__/agent-install-failure.test.js \
  .github/scripts/__tests__/keepalive-loop.test.js \
  tests/scripts/test_agent_delegation_policy_intake.js
/opt/anaconda3/bin/python3 -m pytest \
  tests/workflows/test_cursor_cli_preflight.py \
  tests/workflows/test_runner_cache_contract.py -q -x
PATH=/opt/anaconda3/bin:$PATH bash scripts/sync_templates.sh
/opt/anaconda3/bin/python3 scripts/validate_template_completeness.py
```

## macOS sandbox test runtime

The full workflow suite uses the selected `/opt/anaconda3/bin/python3` runtime.
For this sandbox, set `TMPDIR` to
`/Users/teacher/.codex/orchestrator/agent-runtime/codex/tmp` and prepend a
task-local `mktemp` wrapper to PATH. Native macOS `mktemp` without arguments
ignores the supplied temp directory and attempts a forbidden `/var/folders/...`
write. The wrapper uses the real utility with an explicit writable template:

```sh
#!/bin/sh
if [ "$#" -eq 0 ]; then
  exec /usr/bin/mktemp "${TMPDIR:-/tmp}/workflows-4101.XXXXXXXXXX"
fi
exec /usr/bin/mktemp "$@"
```

Full command (the wrapper above was installed at the indicated task-local path):

```sh
TMPDIR=/Users/teacher/.codex/orchestrator/agent-runtime/codex/tmp \
PATH=/tmp/workflows-4101-tools:/opt/anaconda3/bin:$PATH \
/opt/anaconda3/bin/python3 -m pytest tests/workflows -q -x
```

The 16 Gate dependency-isolation cases pass with this adjustment. No repository
or shared runtime shim was changed. Using `/tmp` as the Python test root also
picked up an unrelated pre-existing `/tmp/pyproject.toml`, so the dedicated
runtime temp directory avoids that configuration inheritance.

## Deliberate break

Copied the policy test, both policy modules and their rate-limit dependencies
into an isolated temporary tree. Ran the following command against that copy:

```sh
node --test --test-name-pattern='recent install failure skips weighted target' \
  .github/scripts/__tests__/agent-install-failure.test.js
```

1. Original guard: exit 0, 2 passed (root and consumer).
2. Removed exactly ` && !installFailures.has(key)` from both policies' candidate
   filters: exit 1, 2 assertion failures. Both selected `cursor` instead of the
   expected `claude`; neither failure was a collection/import error.
3. Restored both source copies: exit 0, 2 passed.

The checkout was never mutated for this proof. Broader tests cover explicit
routes, cooldown bypass, retention across another provider's completion,
expiry, successful recovery, no available replacement, and failed label updates.

## External acceptance still pending

- A live Cursor keepalive round must pass preflight **after merge**; record its
  run ID on issue #4101. No such run is claimed here.
- The issue's separate 48-hour observation must show zero Cursor startup
  command-not-found/exit-127 failures and recovery within one sweep when an
  eligible replacement exists. If every runner is unavailable, evaluation waits
  rather than dispatching the failed provider.

## PR #4103 fix round — 2026-10-18

Merged current `origin/main` before the repair. The sweep root/template pair
was reviewed in full: root dispatches `agents-keepalive-loop.yml`; consumers
have explicit consolidated/non-consolidated modes dispatching
`agents-81-gate-followups.yml`, plus claim reclaim otherwise supplied by root
Health 40. All three sweep paths recover install failures. The allowlist now
records this actual review and the current normalized fingerprints.

Startup exclusion now requires an explicit CLI startup/preflight diagnostic.
The completion writer no longer turns any exit 127 into a startup diagnosis;
inner-tool `command not found` and exit-127 summaries do not exclude providers.
Cursor setup fallbacks use the same `Cursor CLI preflight failed:` diagnostic.
A newer successful completion from the same provider drains the exclusion;
older, same-time, future-dated, and other-provider successes do not. The trusted,
PR-bound completion reader preserves successful receipts even when another
provider has the latest completion. Root and consumer script copies match.

Validation on the repaired source:

- `TMPDIR=/Users/teacher/.codex/orchestrator/agent-runtime/codex/tmp PATH=/tmp/workflows-4103-tools:/opt/anaconda3/bin:$PATH /opt/anaconda3/bin/python3 -m pytest tests/workflows -q -x` — **2,821 passed, 10 skipped** in 286.46 seconds. The task-local `mktemp` wrapper follows the sandbox adjustment documented above; no shared launcher changed.
- `PYTHON=/opt/anaconda3/bin/python3 node --test .github/scripts/agent_delegation_policy.test.js .github/scripts/__tests__/agent-delegation-policy.test.js .github/scripts/__tests__/agent-install-failure.test.js .github/scripts/__tests__/keepalive-loop.test.js tests/scripts/test_agent_delegation_policy_intake.js` — **374 passed**.
- `/opt/anaconda3/bin/python3 scripts/check_template_drift.py --allowlist config/template-drift-allowlist.txt` — exit 0.
- `PATH=/opt/anaconda3/bin:$PATH bash scripts/sync_templates.sh`, `/opt/anaconda3/bin/python3 scripts/validate_template_sync.py`, and `/opt/anaconda3/bin/python3 scripts/validate_template_completeness.py` — passed; no extra files changed.
- `actionlint -ignore SC2129` on the three workflows changed in this fix round — passed; the initial verification above explains the pre-existing SC2129 warnings.
- `ruff check`, `ruff format --check` for `tests/workflows/test_cursor_cli_preflight.py`, and `git diff --check` — passed.

Regression control: copied the new policy tests into an isolated tree with the
pre-fix policy modules from Git. Running
`node --test --test-name-pattern='inner tool failures|only newer same-provider success' .github/scripts/__tests__/agent-install-failure.test.js`
failed with four behavioral assertions (`claude` instead of `cursor`, both
surfaces and both new behaviors), exit 1. The repaired source passes those tests
in the full 374-test JS run. No live agent invocation or CI wait was used.

Post-push handoff: hosted CI and delayed bot/inline review remain for the next
closer pass on the pushed head. This fix round does not wait for CI or merge.
