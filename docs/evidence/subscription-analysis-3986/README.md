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
