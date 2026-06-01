"""JSON/API response snapshot glue over pytest-regressions ("api-snapshot").

The ``golden`` module golden-masters a *flat* dict of scalar metrics via the
``num_regression`` fixture (which pulls in numpy/pandas). API responses are
instead *nested* JSON -- dicts, lists, strings, mixed scalars -- so this module
uses pytest-regressions' ``data_regression`` fixture, which snapshots arbitrary
YAML-able data and needs **no** numpy/pandas. That keeps it ideal for
lightweight services (e.g. a FastAPI app snapshotting ``GET /managers``).

The contract mirrors the rest of the kit: the app hands over a JSON-able payload
(typically a parsed response body), and the helper produces a stable golden
snapshot. "Stable" is the hard part for real responses, so normalization does
two things before the payload reaches disk:

  * **Redaction** -- volatile fields (autoincrement ids, timestamps, UUIDs)
    named by ``exclude`` are removed recursively, so they never spuriously diff.
  * **Determinism** -- dict keys are sorted recursively, and lists may be sorted
    via an optional ``sort_key`` so order-unstable record lists snapshot stably.

Re-bless an intended change with ``--force-regen`` (a pytest-regressions flag).

Exclude path syntax
-------------------
``exclude`` is an iterable of string paths. Each path is matched against the
payload tree; matched nodes are dropped. Segments are split on ``.`` and a
segment may be the wildcard ``*``:

  * A **bare key** (no ``.``) such as ``"id"`` or ``"created_at"`` matches that
    key wherever it appears, at *any* depth. This is the common case: drop every
    ``id``/``updated_at`` in the tree regardless of nesting.
  * A **dotted path** such as ``"meta.request_id"`` is anchored at the root and
    matches only that exact location.
  * ``*`` matches one level of any list index or any dict key. So
    ``"items.*.updated_at"`` drops ``updated_at`` from every element of the
    top-level ``items`` list, and ``"data.*"`` drops every direct child of
    ``data``. ``*`` only ever consumes a single level.

Redaction is applied first, then ``sort_key`` reordering, then recursive key
sorting -- so sort keys may reference fields that survive redaction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

JSONValue = Any  # a JSON-able value: dict | list | str | int | float | bool | None

# A sort_key maps a path (same syntax as exclude, but pointing at a *list*) to a
# callable producing an order-stable sort key for that list's elements.
SortKeys = Mapping[str, Callable[[Any], Any]]


def _split(path: str) -> list[str]:
    """Split a dotted path into its segments."""
    return path.split(".")


def _match_paths(exclude: Iterable[str]) -> tuple[list[list[str]], frozenset[str]]:
    """Partition exclude paths into anchored dotted paths and bare-key names.

    Returns ``(anchored, bare)`` where ``anchored`` is the list of multi-segment
    (and wildcard) paths matched from the root, and ``bare`` is the set of
    single-segment plain keys matched at any depth.
    """
    anchored: list[list[str]] = []
    bare: set[str] = set()
    for raw in exclude:
        segs = _split(raw)
        if len(segs) == 1 and segs[0] != "*":
            bare.add(segs[0])
        else:
            anchored.append(segs)
    return anchored, frozenset(bare)


def _seg_matches(seg: str, key: str) -> bool:
    """Return True if path segment ``seg`` matches dict/list key token ``key``."""
    return seg == "*" or seg == key


def _redact(node: JSONValue, anchored: list[list[str]], bare: frozenset[str]) -> JSONValue:
    """Recursively drop nodes matched by ``bare`` keys or ``anchored`` paths.

    ``anchored`` paths are consumed one segment per level of descent; a path is
    "active" at the current node if its first segment matches the token leading
    here. Bare keys are matched against dict keys at every depth.
    """
    if isinstance(node, Mapping):
        out: dict[str, JSONValue] = {}
        for key, value in node.items():
            # Bare-key redaction: drop this key anywhere it appears.
            if key in bare:
                continue
            # Anchored redaction: an anchored path whose first segment matches
            # this key and that is fully consumed (length 1) drops the node;
            # otherwise its tail is carried into the recursion.
            child_anchored: list[list[str]] = []
            dropped = False
            for path in anchored:
                if _seg_matches(path[0], key):
                    if len(path) == 1:
                        dropped = True
                        break
                    child_anchored.append(path[1:])
            if dropped:
                continue
            out[key] = _redact(value, child_anchored, bare)
        return out
    if isinstance(node, (list, tuple)):
        out_list: list[JSONValue] = []
        for index, value in enumerate(node):
            token = str(index)
            child_anchored = []
            dropped = False
            for path in anchored:
                if _seg_matches(path[0], token):
                    if len(path) == 1:
                        dropped = True
                        break
                    child_anchored.append(path[1:])
            if dropped:
                continue
            out_list.append(_redact(value, child_anchored, bare))
        return out_list
    return node


def _apply_sort_keys(
    node: JSONValue, sort_keys: list[tuple[list[str], Callable[[Any], Any]]]
) -> JSONValue:
    """Recursively reorder lists whose anchored path has a registered sort_key.

    A sort_key whose path is consumed down to an empty tail ``[]`` at a list
    node sorts that list; non-empty tails are carried into the recursion.
    """
    if isinstance(node, Mapping):
        out: dict[str, JSONValue] = {}
        for key, value in node.items():
            child = [(p[1:], fn) for p, fn in sort_keys if p and _seg_matches(p[0], key)]
            out[key] = _apply_sort_keys(value, child)
        return out
    if isinstance(node, list):
        # A sort_key registered at exactly this list's path has an empty tail.
        here = [fn for p, fn in sort_keys if not p]
        descended = []
        for index, value in enumerate(node):
            token = str(index)
            child = [(p[1:], fn) for p, fn in sort_keys if p and _seg_matches(p[0], token)]
            descended.append(_apply_sort_keys(value, child))
        if here:
            descended = sorted(descended, key=here[0])
        return descended
    return node


def _sort_keys_recursive(node: JSONValue) -> JSONValue:
    """Recursively sort dict keys so serialized output is order-independent."""
    if isinstance(node, Mapping):
        return {k: _sort_keys_recursive(node[k]) for k in sorted(node, key=str)}
    if isinstance(node, list):
        return [_sort_keys_recursive(v) for v in node]
    return node


def normalize_response(
    payload: JSONValue,
    *,
    exclude: Iterable[str] = (),
    sort_key: SortKeys | None = None,
) -> JSONValue:
    """Return a normalized, snapshot-stable copy of a JSON-able ``payload``.

    Normalization, in order: redact fields named by ``exclude`` (see module
    docstring for the path syntax), reorder any lists named in ``sort_key``, then
    recursively sort all dict keys. The input is not mutated. ``tuple`` is
    coerced to ``list`` so YAML serialization is stable. Scalars and ``None`` pass
    through unchanged.
    """
    anchored, bare = _match_paths(exclude)
    redacted = _redact(payload, anchored, bare)
    if sort_key:
        prepared = [(_split(path), fn) for path, fn in sort_key.items()]
        redacted = _apply_sort_keys(redacted, prepared)
    return _sort_keys_recursive(redacted)


def check_snapshot(
    data_regression,
    payload: JSONValue,
    *,
    exclude: Iterable[str] = (),
    sort_key: SortKeys | None = None,
    basename: str | None = None,
) -> None:
    """Golden-master a nested JSON ``payload`` via the data_regression fixture.

    ``payload`` is normalized (redaction + deterministic ordering -- see
    :func:`normalize_response`) and handed to ``data_regression.check``. Pass
    ``basename`` to control the snapshot filename when a single test produces
    several snapshots. Re-bless an intended change with ``--force-regen``.
    """
    normalized = normalize_response(payload, exclude=exclude, sort_key=sort_key)
    if basename is None:
        data_regression.check(normalized)
    else:
        data_regression.check(normalized, basename=basename)


def response_to_payload(response: Any) -> dict[str, JSONValue]:
    """Adapt a TestClient/httpx-style response to a snapshot-able payload.

    Duck-typed (no fastapi/httpx dependency): ``response`` only needs a callable
    ``.json()`` and a ``.status_code`` attribute, as provided by Starlette's /
    FastAPI's ``TestClient`` and by ``httpx.Response``. Returns
    ``{"status_code": ..., "json": <parsed body>}`` so the snapshot also pins the
    HTTP status alongside the body.
    """
    return {"status_code": response.status_code, "json": response.json()}


__all__ = [
    "normalize_response",
    "check_snapshot",
    "response_to_payload",
]
