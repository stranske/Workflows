"""Directional ("metamorphic") comparison engine.

A directional check compares two metric values -- a ``left`` and a ``right`` --
and asserts the relationship a domain expert expects. The same comparison serves
two framings:

  * temporal (one app, two configs): left=variant, right=control
    e.g. "raising target vol INCREASEs realized vol"
  * ordering (two entities): left vs right
    e.g. "a car costs LESS_THAN a flight"

Both reduce to comparing two numbers, so both naming sets map to one engine.
"""

from __future__ import annotations

DEFAULT_TOL = 1e-9

# direction name -> comparator(left, right, tol) -> bool
DIRECTIONS = {
    # temporal framing (variant vs control)
    "increase": lambda l, r, t: l > r + t,
    "decrease": lambda l, r, t: l < r - t,
    "increase_or_equal": lambda l, r, t: l >= r - t,
    "decrease_or_equal": lambda l, r, t: l <= r + t,
    "change": lambda l, r, t: abs(l - r) > t,
    "unchanged": lambda l, r, t: abs(l - r) <= t,
    # ordering framing (entity vs entity) -- aliases of the same logic
    "less_than": lambda l, r, t: l < r - t,
    "greater_than": lambda l, r, t: l > r + t,
    "less_or_equal": lambda l, r, t: l <= r + t,
    "greater_or_equal": lambda l, r, t: l >= r - t,
}


def evaluate_direction(direction: str, left: float, right: float, tol: float = DEFAULT_TOL) -> bool:
    """Return True if (left, right) satisfy ``direction``.

    Non-finite inputs always fail (a NaN/inf result is never "sensible").
    """
    import math

    if direction not in DIRECTIONS:
        raise KeyError(f"unknown direction {direction!r}; known: {sorted(DIRECTIONS)}")
    if not (math.isfinite(left) and math.isfinite(right)):
        return False
    return bool(DIRECTIONS[direction](left, right, tol))
