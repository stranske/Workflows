# Source3986 validation

Base: af60a4aee (current main at implementation start).

- `python -m pytest tests/workflows/test_no_api_keys_in_keepalive.py -q`: 17 passed.
- Deliberately restore OPENAI_API_KEY to the actual Codex analysis step: gate fails naming reusable-codex-run.yml; exact workflow bytes restored, 17 passed.
- Focused provider, session analyzer, progress reviewer, CLI-client and workflow tests: 156 passed.
- `node --test --test-name-pattern='autoReconcileTasks|LLM provider analysis details' .github/scripts/__tests__/keepalive-loop.test.js`: 6 passed, including already-complete task exclusion and rendered nonzero counter.
- Actionlint with external shellcheck/pyflakes disabled: all seven touched workflow files pass. Ruff, Black, template completeness/sync validation and git diff whitespace pass.

These are local fixture and wiring checks. No provider CLI was invoked by the tests; process fixtures verify command shape, registry selection, credential filtering, final-message extraction and failure isolation. They do not establish provider identity, live subscription billing or deployment.

Post-merge acceptance still requires one hosted keepalive round showing analysis-run=true, codex provider and registry cheap model, plus the 48-hour OpenAI/Anthropic usage-console observation. Keep the source issue open through those boundaries.

The Codex command follows the [official noninteractive contract](https://developers.openai.com/codex/noninteractive) and [saved account authentication](https://developers.openai.com/codex/auth). No API-key fallback is selected in the opt-in analysis path.

Tool-free Codex analysis: `--disable shell_tool` (and related tools), `--ephemeral`, empty temp cwd; Claude keeps `--tools ""`.

## Owner-requested credential canary — 2026-10-28

The pure `SubscriptionClient.build_command` and `build_environment` builders
expose the exact argv and environment used by `invoke`, without launching a CLI.
The subprocess boundary also checks the exact stdin and temporary cwd.
Both source and consumer-template copies use the same implementation and remain
covered by the existing manifest-driven template sync validator.

`tests/workflows/test_subscription_llm_credential_canary.py` exercises both
transports and both copies, with injection in a task, an acceptance criterion,
and a session transcript through the two production prompt builders. A temporary
HOME/CODEX_HOME contains fake credential files with a unique canary. The test
intercepts the actual subprocess boundary, compares it with the pure builders,
checks the complete independent Codex disable list and exact provider argv,
verifies an empty temporary cwd outside the checkout and credential directories,
and checks credential/instruction environment filtering and stdin/argv for leaks.
HOME/CODEX_HOME (or Claude's config directory) remain explicit authentication
locators, not instruction-bearing environment. Their paths are excluded from all
other forwarded environment values and from argv/stdin; the credential canary
and seeded provider/job keys are excluded from the entire child environment.

- Negative control: remove `shell_tool` from the disable list in **both** copies;
  the six Codex cases fail on the missing flag, while six Claude cases pass.
  [Exact red output](canary-red.txt), exit 1.
- Restore the original bytes in both copies; all 12 cases pass.
  [Exact green output](canary-green.txt), exit 0.
- Deleted `cursor-output-4139.md` and `cursor-prompt-4139.md`.

Validation used `/opt/anaconda3/bin/python3` (Python 3.12):

```sh
python -m pytest tests/workflows/test_no_api_keys_in_keepalive.py tests/workflows/test_subscription_llm_credential_canary.py tests/tools/test_llm_provider.py tests/tools/test_llm_provider_tracing_opt_out.py tests/tools/test_codex_session_analyzer.py tests/scripts/test_analyze_codex_session.py tests/scripts/test_progress_reviewer.py tests/scripts/test_llm_client_shared.py tests/scripts/test_sync_manifest_compiler.py tests/scripts/test_validate_template_sync.py -q
# 283 passed in 5.85s

node --test --test-name-pattern='autoReconcileTasks|LLM provider analysis details' .github/scripts/__tests__/keepalive-loop.test.js
# 6 passed, 0 failed

python scripts/validate_template_sync.py
# All template files in sync
python scripts/validate_template_completeness.py
# All consumer workflows are properly templated and manifested

python -m ruff check tools/subscription_llm.py templates/consumer-repo/tools/subscription_llm.py tests/workflows/test_subscription_llm_credential_canary.py
# All checks passed
python -m black --check --target-version py312 tools/subscription_llm.py templates/consumer-repo/tools/subscription_llm.py tests/workflows/test_subscription_llm_credential_canary.py
# 3 files would be left unchanged

actionlint -shellcheck='' -pyflakes='' .github/workflows/reusable-codex-run.yml .github/workflows/reusable-claude-run.yml .github/workflows/reusable-cursor-run.yml .github/workflows/reusable-gemini-run.yml .github/workflows/reusable-muse-run.yml .github/workflows/agents-keepalive-loop.yml templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml
# exit 0 (seven workflow files)

git diff --check
# exit 0
```

The canary is an offline configuration regression, including the deliberate
failure required by the owner. No provider CLI, model, network request, hosted
round or billing observation is exercised. Effective CLI runtime enforcement
remains outside this evidence. The P1 thread remains for owner-side disposition;
this follow-up does not resolve it or establish merge acceptance.

Post-push scanner follow-up: the first pure builder returned argv and environment
in one tuple, which coupled the environment-tainted result to command argv in
Semgrep. Replaced that combined return with separate pure command/environment
builders and an explicit `subprocess.run(..., shell=False)` call. No scanner
suppression was added. The exact
`python.lang.security.audit.dangerous-subprocess-use-tainted-env-args` rule was
run locally against both final copies: two files scanned, zero findings.
The canary red/green evidence above was regenerated after this correction.

After that scanner correction, the same focused pytest command above passed
again: **283 passed in 5.93s**. Template sync/completeness, Ruff, Black and
whitespace checks also passed again. Local scanner command (one downloaded
upstream rule, metrics and version checks disabled):

```sh
semgrep scan --metrics=off --disable-version-check --config <downloaded-rule.yml> tools/subscription_llm.py templates/consumer-repo/tools/subscription_llm.py
# 1 rule, 2 targets scanned, 0 findings
```

Rule source: https://raw.githubusercontent.com/semgrep/semgrep-rules/develop/python/lang/security/audit/dangerous-subprocess-use-tainted-env-args.yaml
Downloaded rule SHA256: `0f3f3f8fafef5b828a15253585e4c6648c46c6fd1cca4b0ae8c70a9399def44d`.
