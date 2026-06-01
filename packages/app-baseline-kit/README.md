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
| `golden` | `check_metrics(num_regression, metrics)` — golden masters of a **flat** scalar-metrics dict via pytest-regressions (`num_regression`, float tolerance, `--force-regen` to re-bless). |
| `snapshot` | `check_snapshot(data_regression, payload)` — golden masters of **nested JSON** (API responses) via pytest-regressions `data_regression`. No numpy/pandas. Redacts volatile fields + deterministic ordering. See [api-snapshot modality](#api-snapshot-modality). |
| `catalog` | `load_catalog(path)` — YAML scenario catalog loader. |

## Proven consumers

- **Trend_Model_Project** (`tests/baseline/`) — config-patch adapter over a
  Streamlit/CLI quant model; golden masters of metrics/weights, directional
  control-vs-variant checks, economic invariants, Streamlit AppTest smoke.
- **trip-planner** (`tests/baseline/`) — fixture-compute adapter over
  deterministic transport-option evaluation; golden masters per fixture,
  cross-option ordering checks, signal/cost invariants.

## api-snapshot modality

`golden.check_metrics` golden-masters a **flat** `dict[str, float|int]` and uses
the `num_regression` fixture (which pulls in numpy/pandas). API responses are
**nested** JSON, so `snapshot.check_snapshot` uses pytest-regressions'
`data_regression` fixture instead — it snapshots arbitrary YAML-able data and
needs **no** numpy/pandas, which keeps it cheap for lightweight services (e.g. a
FastAPI app snapshotting `GET /managers`).

```python
from baseline_kit import check_snapshot, response_to_payload

def test_list_managers(client, data_regression):     # client = FastAPI/Starlette TestClient
    resp = client.get("/managers")
    payload = response_to_payload(resp)               # {"status_code": ..., "json": <body>}
    check_snapshot(
        data_regression,
        payload,
        exclude=("id", "created_at", "json.meta.request_id"),
        sort_key={"json.managers": lambda m: m["name"]},
    )
```

Public API:

- `normalize_response(payload, *, exclude=(), sort_key=None)` — return a
  snapshot-stable copy (redaction + deterministic ordering); call it directly to
  inspect/assert structure without writing a golden.
- `check_snapshot(data_regression, payload, *, exclude=(), sort_key=None, basename=None)`
  — normalize `payload` then `data_regression.check(...)`. Re-bless with
  `--force-regen`.
- `response_to_payload(response)` — duck-typed adapter for any object with
  `.json()` + `.status_code` (Starlette/FastAPI `TestClient`, `httpx.Response`);
  returns `{"status_code": ..., "json": <body>}`. No fastapi/httpx dependency.

### Normalization

Real responses carry non-deterministic fields (autoincrement ids, timestamps,
UUIDs) and order-unstable record lists. `normalize_response` (applied by
`check_snapshot`) handles both, in order: **redact** → **sort_key reorder** →
**recursive key sort**. The input is never mutated; `tuple` is coerced to `list`.

**`exclude` path syntax.** Each entry is a string path; matched nodes are
dropped:

| Form | Example | Matches |
|---|---|---|
| Bare key (no `.`) | `"id"`, `"created_at"` | that key at **any depth** |
| Dotted path | `"meta.request_id"` | that exact location, **anchored at the root** |
| Wildcard `*` | `"items.*.updated_at"` | `updated_at` in every element of the top-level `items` list |
| Wildcard `*` | `"data.*"` | every direct child of `data` |

`*` consumes exactly one level (a list index or a dict key).

**List ordering.** Lists keep their input order by default. For order-unstable
record lists, pass `sort_key={<path-to-the-list>: <key-fn>}` (path uses the same
syntax, pointing at the list) — the helper sorts that list by the key function
before snapshotting. Alternatively, pre-sort in the app/adapter.

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
