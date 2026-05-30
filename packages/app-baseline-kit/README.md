# app-baseline-kit

The shared, app-agnostic core of the "app behavior baseline" harness:
scenario-driven **wiring**, **economic sensibility**, and **regression**
testing, reusable across apps.

## The one contract

Each app writes a small **adapter** that reduces a run to a flat dict of named
scalar metrics (`dict[str, float | int]`). Everything else is generic and lives
here:

| Module | What it gives you |
|---|---|
| `directional` | `evaluate_direction(direction, left, right)` — metamorphic comparisons. Works for both control-vs-variant (temporal) and entity-vs-entity (ordering) framings. |
| `invariants` | `InvariantResult` + `assert_invariants` — error severity fails, warn severity reports. |
| `manifest` | `CoverageManifest` — input-parameter → scenario coverage, typo/priority-gap detection, markdown report. |
| `golden` | `check_metrics(num_regression, metrics)` — golden masters via pytest-regressions, float tolerance, `--force-regen` to re-bless. |
| `catalog` | `load_catalog(path)` — YAML scenario catalog loader. |

## Proven consumers

- **Trend_Model_Project** (`tests/baseline/`) — config-patch adapter over a
  Streamlit/CLI quant model; golden masters of metrics/weights, directional
  control-vs-variant checks, economic invariants, Streamlit AppTest smoke.
- **trip-planner** (`tests/baseline/`) — fixture-compute adapter over
  deterministic transport-option evaluation; golden masters per fixture,
  cross-option ordering checks, signal/cost invariants.

## Install

This package lives as a subdirectory of `stranske/Workflows`. Consumers install
it as a normal pip dependency pinned to a git ref:

```bash
pip install "app-baseline-kit @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit"
```

(Pin to a tag/SHA in `requirements`/`pyproject` for reproducibility.) Local
development: `pip install -e packages/app-baseline-kit` from a Workflows checkout.

It is **not** distributed via the sync-manifest — a Python library is installed,
not copied into consumer trees. If/when independent release cadence matters, it
can be promoted to its own repo without changing this contract.

## Writing an adapter (sketch)

```python
def metrics_for(case) -> dict[str, float]:
    out = run_my_app(case)          # call the LOGIC layer, not the UI
    return {"sharpe": out.sharpe, "max_weight": out.weights.max(), ...}
```

Then a catalog of orderings/scenarios + a few `InvariantResult`-returning
checks, and the generic test modules drive golden/directional/invariant/manifest.
