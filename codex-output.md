Removed the extra blank line between the import block and constants so ruff/isort treats the imports as properly formatted in `scripts/keepalive_metrics_collector.py`.

Details: ruff’s I001 wanted the import block to end with a single blank line, so I tightened that spacing in `scripts/keepalive_metrics_collector.py`.

Next steps:
1. Run `python -m ruff check .` to confirm the lint job passes locally.
2. If you want, run the full CI lint task to match the pipeline.