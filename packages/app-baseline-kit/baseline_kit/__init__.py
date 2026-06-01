"""app-baseline-kit: the generic, app-agnostic core of the baseline harness.

The kit splits cleanly into:

  * GENERIC (this package) -- the catalog format, directional ("metamorphic")
    comparison engine, invariant result type + assertion helper, the
    coverage-manifest, and golden-master glue. Identical across apps.

  * APP-SPECIFIC (each consuming repo) -- an "adapter" that turns an input
    (a config patch, a fixture, a request) into a flat ``metrics`` dict
    (``dict[str, float | int]``), plus the catalog content and invariant bounds.

The contract between them is just the metrics dict: every app reduces its run
to named scalars, and the generic machinery compares, bounds, baselines, and
reports those scalars.

Proven on two consumers: a Streamlit/CLI quant model (config-patch adapter) and
a trip-planner (fixture-compute adapter).
"""

from .catalog import load_catalog
from .directional import DIRECTIONS, evaluate_direction
from .golden import DEFAULT_TOLERANCE, check_metrics
from .invariants import InvariantResult, assert_invariants, split_results
from .manifest import CoverageManifest
from .snapshot import check_snapshot, normalize_response, response_to_payload

__all__ = [
    "load_catalog",
    "DIRECTIONS",
    "evaluate_direction",
    "DEFAULT_TOLERANCE",
    "check_metrics",
    "InvariantResult",
    "assert_invariants",
    "split_results",
    "CoverageManifest",
    "check_snapshot",
    "normalize_response",
    "response_to_payload",
]
