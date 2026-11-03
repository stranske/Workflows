# Acceptance evidence for stranske/Workflows#4063 (PR #4065)

PR #4065 (squash `7ccda2ad8`, head `117e1aa9a`) added 13 tests to
`tests/scripts/test_issue_optimizer.py` and two minimal production fixes in
`scripts/langchain/issue_optimizer.py`. This record covers what #4065's body did not prove:
a break-and-restore run for every added test, Gate baseline/head coverage measured the same
way on both sides, and the ranking evidence for the chosen target. Production code and tests are
unchanged by this record. All numbers below come from the commands and job logs named next to them.

## 1. Break-and-restore, one targeted defect per added test

#4065's body grouped its proof by behaviour ("1 selected test failed after disabling the cap")
without naming the test nodes or the failing assertions. Its two-regression RED run (2 failed /
56 passed on old production) covers only tests 1 and 10, and reverting the two fixes leaves the
other 11 tests passing. So all 13 were run again here, each against its own defect.

Interpreter: `/opt/anaconda3/bin/python3` (the repository pins no interpreter: it has no
`.python-version` and no local venv). Production source used was main `6cf49cb29`, blob
`c975efe88`, sha256 `ddc381066cbd...`. The harness applied one string mutation, ran only that
pytest node, wrote the original bytes back, checked the sha256, and ran the node again. Test line
numbers are current main's: later PRs #4074, #4183 and #4264 added tests to this file, and all 13
#4065 test names are unchanged.

### 1. `test_optimizer_helpers_preserve_usable_data_and_cap_overflow`
- mutation: _cap_checkbox_lines: keep nested lines of a dropped (over-cap) parent
  - `if indent and dropping_parent:` -> `if indent and dropping_parent and False:` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_optimizer_helpers_preserve_usable_data_and_cap_overflow`
- BROKEN: exit 1; `1 failed in 0.43s`
  - at `tests/scripts/test_issue_optimizer.py:991: AssertionError`
  - `E       AssertionError: assert '  - [ ] Nested detail' not in '## Tasks\n-... ] Check one'`
  - `E`
  - `E         '  - [ ] Nested detail' is contained here:`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.71s`

### 2. `test_fallback_paths_keep_structured_issue_when_llm_is_unavailable`
- mutation: _blocked_task_lines: stop skipping blocked entries with no task text
  - `if not task: continue` -> `if not task: pass` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_fallback_paths_keep_structured_issue_when_llm_is_unavailable`
- BROKEN: exit 1; `1 failed in 0.73s`
  - at `tests/scripts/test_issue_optimizer.py:1017: AssertionError`
  - `E       assert 'Deferred Tasks' not in '## Why\n\n_...zer"]} -->\n'`
  - `E`
  - `E         'Deferred Tasks' is contained here:`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.60s`

### 3. `test_provider_token_limit_falls_back_to_formatter_when_openai_is_unavailable`
- mutation: analyze_issue: never take the GitHub Models token-limit retry branch
  - `if _is_token_limit_error(e) and provider == "github-models":` -> `if _is_token_limit_error(e) and provider == "never":` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_provider_token_limit_falls_back_to_formatter_when_openai_is_unavailable`
- BROKEN: exit 1; `1 failed in 0.73s`
  - at `tests/scripts/test_issue_optimizer.py:1048: AssertionError`
  - `E       AssertionError: assert 'retrying with OpenAI API' in 'LLM analysis failed (RuntimeError: token limit), using fallback\n'`
  - `E        +  where 'LLM analysis failed (RuntimeError: token limit), using fallback\n' = CaptureResult(out='', err='LLM analysis failed (RuntimeError: token limit), using fallback\n').err`
  - `E        +    where CaptureResult(out='', err='LLM analysis failed (RuntimeError: token limit), using fallback\n') = readouterr()`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.50s`

### 4. `test_analyze_issue_recovers_with_openai_after_github_models_token_limit`
- mutation: analyze_issue: discard a successful OpenAI retry result (invert the success check)
  - `if result is not None:` -> `if result is None:` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_analyze_issue_recovers_with_openai_after_github_models_token_limit`
- BROKEN: exit 1; `1 failed in 0.70s`
  - at `tests/scripts/test_issue_optimizer.py:1084: AssertionError`
  - `E       AssertionError: assert None == 'openai'`
  - `E        +  where None = IssueOptimizationResult(task_splitting=[], blocked_tasks=[], objective_criteria=[], missing_sections=['Why', 'Scope', ...ilable).', provider_used=None, guard_blocked=False, guard_reason='', langsmith_trace_id=None, langsmith_trace_url=None).provider_used`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.52s`

### 5. `test_apply_suggestions_recovers_with_openai_after_github_models_token_limit`
- mutation: apply_suggestions: report the primary provider instead of the OpenAI retry provider
  - `"provider_used": openai_provider,` -> `"provider_used": provider,` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_apply_suggestions_recovers_with_openai_after_github_models_token_limit`
- BROKEN: exit 1; `1 failed in 0.64s`
  - at `tests/scripts/test_issue_optimizer.py:1124: AssertionError`
  - `E       AssertionError: assert 'github-models' == 'openai'`
  - `E`
  - `E         - openai`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.49s`

### 6. `test_apply_suggestions_falls_back_when_openai_retry_fails`
- mutation: apply_suggestions: a failed OpenAI retry returns the raw body claiming the LLM was used
  - `err_type = type(openai_error).__name__` -> `return {"formatted_body": issue_body, "provider_used": openai_provider, "used_llm": True}` (occurrence 2)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_apply_suggestions_falls_back_when_openai_retry_fails`
- BROKEN: exit 1; `1 failed in 0.66s`
  - at `tests/scripts/test_issue_optimizer.py:1163: AssertionError`
  - `E       AssertionError: assert 'openai' is None`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.44s`

### 7. `test_cli_main_emits_plain_text_for_analysis_and_apply`
- mutation: main: plain-text analysis output drops the analysis payload
  - `print(json.dumps(result.to_dict(), ensure_ascii=True))` -> `print(json.dumps({}, ensure_ascii=True))` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_cli_main_emits_plain_text_for_analysis_and_apply`
- BROKEN: exit 1; `1 failed in 0.71s`
  - at `tests/scripts/test_issue_optimizer.py:1178: AssertionError`
  - `E       AssertionError: assert 'Fallback analysis used' in '{}\n'`
  - `E        +  where '{}\n' = CaptureResult(out='{}\n', err='').out`
  - `E        +    where CaptureResult(out='{}\n', err='') = readouterr()`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 2.59s`

### 8. `test_cli_loaders_and_main_handle_all_supported_suggestion_sources`
- mutation: _load_suggestions: discard a valid --suggestions-file payload
  - `return data if isinstance(data, dict) else None` -> `return None` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_cli_loaders_and_main_handle_all_supported_suggestion_sources`
- BROKEN: exit 1; `1 failed in 0.73s`
  - at `tests/scripts/test_issue_optimizer.py:1224: AssertionError`
  - `E       AssertionError: assert None == {'blocked_tasks': []}`
  - `E        +  where None = <function _load_suggestions at 0x106c580e0>(Namespace(suggestions_json=None, suggestions_file='/Users/teacher/.codex/orchestrator/agent-runtime/claude/tmp/pytest-...st-355/test_cli_loaders_and_main_hand0/suggestions.json', suggestions_comment_file=None, suggestions_comment_text=None))`
  - `E        +    where <function _load_suggestions at 0x106c580e0> = issue_optimizer._load_suggestions`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.29s`

### 9. `test_cli_main_emits_json_for_analysis_and_apply`
- mutation: main: JSON apply payload always claims used_llm=True
  - `"used_llm": result.get("used_llm", False),` -> `"used_llm": True,` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_cli_main_emits_json_for_analysis_and_apply`
- BROKEN: exit 1; `1 failed in 0.50s`
  - at `tests/scripts/test_issue_optimizer.py:1280: AssertionError`
  - `E       assert True is False`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.48s`

### 10. `test_structural_helpers_handle_empty_sections_sentinels_and_invalid_entries`
- mutation: _append_deferred_tasks: never merge new tasks into an existing Deferred section (the #4065 bug)
  - `if line.strip() not in existing:` -> `if False:` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_structural_helpers_handle_empty_sections_sentinels_and_invalid_entries`
- BROKEN: exit 1; `1 failed in 0.44s`
  - at `tests/scripts/test_issue_optimizer.py:1331: AssertionError`
  - `E       AssertionError: assert '- [ ] Different task' in '## Tasks\n- [ ] Parent task\n## Acceptance Criteria\n- [ ] pytest\n\n## Deferred Tasks (Requires Human)\n\n- [ ] Ask human\n\n## Notes\nPreserve this section'`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.33s`

### 11. `test_loaders_and_llm_response_errors_are_explicit`
- mutation: _load_suggestions: accept a non-dict --suggestions-json payload
  - `return data if isinstance(data, dict) else None` -> `return data` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_loaders_and_llm_response_errors_are_explicit`
- BROKEN: exit 1; `1 failed in 0.41s`
  - at `tests/scripts/test_issue_optimizer.py:1355: AssertionError`
  - `E       AssertionError: assert [] is None`
  - `E        +  where [] = <function _load_suggestions at 0x11240bf60>(Namespace(suggestions_json='[]', suggestions_file=None, suggestions_comment_file=None, suggestions_comment_text=None))`
  - `E        +    where <function _load_suggestions at 0x11240bf60> = issue_optimizer._load_suggestions`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.41s`

### 12. `test_local_prompt_fallbacks_work_without_optional_prompt_files`
- mutation: _build_llm_config inline fallback: ignore ISSUE_NUMBER from the environment
  - `else env_issue if env_issue.isdigit() else "unknown"` -> `else "unknown"` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_local_prompt_fallbacks_work_without_optional_prompt_files`
- BROKEN: exit 1; `1 failed in 0.50s`
  - at `tests/scripts/test_issue_optimizer.py:1421: AssertionError`
  - `E       AssertionError: assert 'unknown' == '42'`
  - `E`
  - `E         - 42`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.38s`

### 13. `test_parser_and_invoker_handle_code_blocks_and_legacy_chain_signature`
- mutation: _parse_checklist: treat checklist lines inside fenced code blocks as tasks
  - `if in_code_block:` -> `if in_code_block and False:` (occurrence 1)
- command: `/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py::test_parser_and_invoker_handle_code_blocks_and_legacy_chain_signature`
- BROKEN: exit 1; `1 failed in 0.53s`
  - at `tests/scripts/test_issue_optimizer.py:1441: AssertionError`
  - `E       AssertionError: assert ['Not a task'] == []`
  - `E`
  - `E         Left contains one more item: 'Not a task'`
- RESTORED (sha256 ddc381066cbd re-verified): exit 0; `1 passed in 0.39s`

### Full file after restoration

```
$ /opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/scripts/test_issue_optimizer.py
65 passed in 0.61s
$ git status --short scripts/ tests/      # (empty: no mutation retained)
```

## 2. Gate coverage: baseline vs head, measured the same way

The Gate coverage artifacts from 2026-10-18 have expired (`artifacts` lists 0 for run
39088380653, and artifact 12121084300 returns 404). The `python ci / python 3.14` job logs are
still available, and each prints the coverage.py term report (Stmts, Miss, Branch, BrPart, Cover).
The term report does not print missing branches directly. They are recovered as the one integer
that reproduces the printed blended percentage to 2 decimals, and each row below had exactly one
such integer. For the head run this gives 43, matching the coverage.json value quoted in #4065.

| Gate run (py3.14 job) | merge tested | Stmts | Miss | Branch | Missing branches | Cover | Uncovered units |
|---|---|---|---|---|---|---|---|
| 39088362357, baseline (PR #4062, release-please, no change to the target) | `a469096` into main `7e10b64ad` | 810 | 195 | 302 | 107 | 72.84% | **302** |
| 39088380653, #4065 head `117e1aa9` | `117e1aa9` into main `7e10b64ad` | 831 | 60 | 314 | 43 | 91.00% | **103** |
| 39079350563, autopilot payload behind the issue's "301" (PR for #4038, 2026-10-17T23:31Z) | older main | 810 | 195 | 302 | 106 | 72.93% | 301 |

Reconciliation:

- Both runs merge into the same main, `7e10b64ad`, so the comparable reduction is **302 to 103,
  that is 199 units**. The 198 that #4065 reported is the issue's recorded 301 minus 103. The 301
  is the autopilot's payload from an earlier Gate run, not a baseline on the same main.
- The gap between 301 and 302 is run-to-run variance in branch arcs: identical statement
  counts, BrPart 60 vs 61. Four other Gate runs between 23:25Z and 00:48Z (39078973035, 39081243555, 39082957933, 39084091313) read the same file as
  299 units (73.11%). The measurement therefore carries about ±3 units of noise. Both 198 and 199
  clear the ~180 goal by more than that.
- The two #4065 production fixes added 21 statements and 12 branches (1112 to 1145
  measurable units). Covered units rose from 810 to 1042 (**+232**). The reduction in uncovered
  units is the smaller and more conservative of the two figures.
- Repo-wide in the same two jobs: TOTAL 84.24% to 84.57%.

Limitations of the remaining 103 units (at the #4065 head): these are not dead code. They were
left uncovered after the ~180 goal was met:

- `ModuleNotFoundError` import fallbacks for direct script invocation (lines 33-36, 1220-1221,
  1455-1456). They are reachable only when run outside the package, which the suite never does.
- `apply_suggestions` retry side branches: OpenAI unavailable, duplicated-section rejection
  after retry, and non-token-limit errors (around 1368-1448). The equivalent `analyze_issue`
  branches are covered.
- CLI JSON guard and trace fields (1542-1547), malformed `--suggestions-json` (1481-1482),
  and scattered partial branches in dedup and decomposition.

## 3. Ranking evidence for the chosen target

The issue names the target as ranked by the Orchestrator's `escaped_defect_priority.py`
(`~/.codex/orchestrator-mirror`), which coverage-autopilot runs via `rank_targets()`. The
ranker's tier 1 counts fix and revert commits that touched the file. Tier 2 counts non-merge
commits. Both use `git log --since=180.days.ago`. Tier 3 counts missing statements. Results are
ordered lexicographically by tier. The issue records `issue_optimizer.py` as "2 escaped-defect
signal(s), churn 6, fix commit touched this file", with 301 units.

The ranker reads `git log` from the HEAD of its clone, `~/.codex/orchestrator/repos/stranske__Workflows`.
coverage-autopilot only runs `git fetch` on that clone, and fetch never moves HEAD. The clone's
HEAD is `401260e4a` (2026-06-28). It has no reflog, so its HEAD on 2026-10-18 is inferred, not
read. The tiers were replayed with the ranker's own `FIX_SUBJECT`/`REVERT_SUBJECT` regexes, a
window anchored at the issue's open time (`--since=2026-04-21T01:02:04Z`), and tier 3 from the
payload run 39079350563:

- **On the clone's HEAD `401260e4a`**, `issue_optimizer.py` scores tier1 2 and churn 6, as the
  issue records, and **ranks 24th**. All 23 rows above it are accounted for:
  - 7 are the files #4063 lists as in flight or reserved;
  - 15 were targets of earlier rounds (#3956, #3964, #3995, #3998, #4001, #4005, #4013,
    #4018-#4020, #4054, #4055), whose remaining units the autopilot ledger and skip memory had
    reduced or zeroed;
  - 1 (`scripts/state_fingerprint.py`) had 0 uncovered statements.

  The first eligible row is therefore `issue_optimizer.py`, which matches the issue.
- **On the issue-time main `08ad16ec7`** (what the ranker would have read if its clone were current), the
  same target still scores tier1 2 and churn 6, but ranks **55th**. 27 files that no round had
  ever targeted, all with real uncovered units, rank above it. Examples are
  `scripts/check_deliberate_break.py` (73 fix-commit signals, 9 units), `tools/llm_registry.py`
  (22, 34 units) and `scripts/docs_drift_fix_agent.py` (11, 79 units).

Conclusion: the target was correctly the first eligible row of the ranking the autopilot
actually computed. That ranking, however, came from history that ended 2026-06-28, not the
180 days before the issue. **The escaped-defect priority was stale by about 3.5 months**, and a
current-history ranking would have picked other files first. That is a defect in the
Orchestrator's ranker clone (`rank_targets()`/`repo_clone()`), not in this repository. It is
reported here and not fixed, because it is out of this PR's scope.

Replay scripts used, outside the repo (they read only git history and the downloaded job logs):
`rerank.py <repo> <commit> <since> <gate-log>` and `classify.py`. The commands were:

```
gh api repos/stranske/Workflows/actions/jobs/<python-3.14 job id>/logs > gate.log
python3 rerank.py ~/.codex/orchestrator/repos/stranske__Workflows 401260e4a 2026-04-21T01:02:04Z g_39079350563.log
python3 rerank.py . 08ad16ec7 2026-04-21T01:02:04Z gate_base_314.log
```
