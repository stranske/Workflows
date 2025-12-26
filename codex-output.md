Wrapped the long argparse line to match Black’s 100‑char limit so the format check should pass in CI. This targets the only new >100‑char line added in `scripts/keepalive_metrics_dashboard.py`.

Details:
- `scripts/keepalive_metrics_dashboard.py`: split `argparse.ArgumentParser(...)` into a multi-line call.

If you want to verify locally, run:
1. `black --check scripts/keepalive_metrics_dashboard.py`
2. `scripts/validate_fast.sh`