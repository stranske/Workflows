Added a metrics aggregation script to summarize agent NDJSON metrics into a markdown report and covered it with pytest so the weekly workflow can call a tested, repo‑native helper. Changes are in `scripts/aggregate_agent_metrics.py` (parser/summary formatter) and `tests/scripts/test_aggregate_agent_metrics.py` (summary + main path coverage).

AGENTS.md note: no `AGENTS.md` found under `/home/runner/work/Workflows/Workflows`.

Tests run:
- `python -m pytest tests/scripts/test_aggregate_agent_metrics.py`

Next steps you may want:
1) Wire `scripts/aggregate_agent_metrics.py` into the weekly workflow and metrics upload steps (requires workflow edits I can’t make here).
2) Define/standardize the NDJSON schema keys in the emitting workflows so the classifier doesn’t need heuristics.