# LangChain LLM Task Analysis

The Codex reusable runner calls [the session analysis CLI](../scripts/analyze_codex_session.py)
when its analysis prerequisites are satisfied. It supplies a session file and
PR body and writes JSON; failed or unavailable analysis is reported as skipped
rather than automatically proving task completion. See the
[reusable runner](../.github/workflows/reusable-codex-run.yml) and
[keepalive contract](keepalive/GoalsAndPlumbing.md) for the current call and
completion rules.

## Usage

```sh
python scripts/analyze_codex_session.py \
  --session-file /path/to/session.jsonl \
  --pr-body-file /path/to/pr-body.md \
  --output json
```

Use `--help` for the supported options. For a local offline control,
`--provider regex-fallback` avoids an LLM API call. The
[model selection policy](MODEL_SELECTION_POLICY.md) and
[model management guide](MODEL_MANAGEMENT.md) own current model decisions.

The [original January 2026 guide](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/llm-task-analysis.md) and the
[earlier standalone heuristic analyzer](https://github.com/stranske/Workflows/blob/a5126c655597da7234616061c452b80f4ce8960f/tools/codex_log_analyzer.py)
remain available as historical references.
