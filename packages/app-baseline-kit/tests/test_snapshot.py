"""Tests for baseline_kit.snapshot (api-snapshot modality)."""

from __future__ import annotations

from baseline_kit import check_snapshot, normalize_response, response_to_payload


def test_bare_key_redaction_at_any_depth() -> None:
    payload = {
        "id": 1,
        "name": "alpha",
        "owner": {"id": 99, "email": "a@b.c"},
        "items": [{"id": 7, "v": 1}, {"id": 8, "v": 2}],
    }
    out = normalize_response(payload, exclude=("id",))
    assert "id" not in out
    assert "id" not in out["owner"]
    assert all("id" not in item for item in out["items"])
    # non-excluded fields survive
    assert out["name"] == "alpha"
    assert out["owner"]["email"] == "a@b.c"
    assert [i["v"] for i in out["items"]] == [1, 2]


def test_dotted_path_is_anchored_at_root() -> None:
    payload = {
        "request_id": "top-level-keep-if-not-excluded",
        "meta": {"request_id": "drop-me"},
        "nested": {"meta": {"request_id": "survives-anchored"}},
    }
    out = normalize_response(payload, exclude=("meta.request_id",))
    # anchored path only removes meta.request_id at the root
    assert "request_id" not in out["meta"]
    assert out["request_id"] == "top-level-keep-if-not-excluded"
    assert out["nested"]["meta"]["request_id"] == "survives-anchored"


def test_wildcard_path_redacts_each_list_element() -> None:
    payload = {
        "items": [
            {"name": "a", "updated_at": "2020-01-01"},
            {"name": "b", "updated_at": "2020-02-02"},
        ]
    }
    out = normalize_response(payload, exclude=("items.*.updated_at",))
    assert all("updated_at" not in item for item in out["items"])
    assert [i["name"] for i in out["items"]] == ["a", "b"]


def test_wildcard_drops_all_direct_children() -> None:
    payload = {"data": {"a": 1, "b": 2}, "keep": "yes"}
    out = normalize_response(payload, exclude=("data.*",))
    assert out["data"] == {}
    assert out["keep"] == "yes"


def test_key_sorting_is_deterministic() -> None:
    a = normalize_response({"b": 1, "a": 2, "c": {"z": 1, "y": 2}})
    b = normalize_response({"c": {"y": 2, "z": 1}, "a": 2, "b": 1})
    assert list(a.keys()) == ["a", "b", "c"]
    assert list(a["c"].keys()) == ["y", "z"]
    assert a == b


def test_list_order_is_preserved_without_sort_key() -> None:
    payload = {"xs": [3, 1, 2]}
    out = normalize_response(payload)
    assert out["xs"] == [3, 1, 2]


def test_sort_key_reorders_record_list() -> None:
    payload = {
        "managers": [
            {"name": "Charlie", "id": 3},
            {"name": "Alice", "id": 1},
            {"name": "Bob", "id": 2},
        ]
    }
    out = normalize_response(payload, sort_key={"managers": lambda m: m["name"]})
    assert [m["name"] for m in out["managers"]] == ["Alice", "Bob", "Charlie"]


def test_sort_key_runs_before_redaction_target_is_fine() -> None:
    # sort by a field, then redact a different (volatile) field
    payload = {
        "rows": [
            {"key": "b", "ts": "2020-02-02"},
            {"key": "a", "ts": "2020-01-01"},
        ]
    }
    out = normalize_response(payload, exclude=("rows.*.ts",), sort_key={"rows": lambda r: r["key"]})
    assert [r["key"] for r in out["rows"]] == ["a", "b"]
    assert all("ts" not in r for r in out["rows"])


def test_tuple_is_coerced_to_list() -> None:
    out = normalize_response({"xs": (1, 2, 3)})
    assert out["xs"] == [1, 2, 3]
    assert isinstance(out["xs"], list)


def test_input_is_not_mutated() -> None:
    payload = {"id": 1, "name": "x"}
    normalize_response(payload, exclude=("id",))
    assert payload == {"id": 1, "name": "x"}


def test_top_level_list_payload() -> None:
    payload = [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]
    out = normalize_response(payload, exclude=("id",))
    assert out == [{"v": "a"}, {"v": "b"}]


def test_scalar_and_none_pass_through() -> None:
    assert normalize_response(None) is None
    assert normalize_response(42) == 42
    assert normalize_response("x") == "x"


class _FakeResponse:
    """Duck-typed stand-in for a TestClient/httpx response."""

    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body


def test_response_to_payload_duck_typed() -> None:
    resp = _FakeResponse(200, {"managers": [{"id": 1, "name": "Alice"}]})
    payload = response_to_payload(resp)
    assert payload == {
        "status_code": 200,
        "json": {"managers": [{"id": 1, "name": "Alice"}]},
    }


def test_check_snapshot_round_trip(data_regression: object) -> None:
    # Mirrors a FastAPI GET /managers response with volatile fields redacted.
    resp = _FakeResponse(
        200,
        {
            "managers": [
                {"id": 7, "name": "Bravo", "created_at": "2026-05-31T00:00:00Z"},
                {"id": 3, "name": "Alpha", "created_at": "2026-05-30T00:00:00Z"},
            ],
            "meta": {"request_id": "abc-123", "count": 2},
        },
    )
    payload = response_to_payload(resp)
    check_snapshot(
        data_regression,
        payload,
        exclude=("id", "created_at", "json.meta.request_id"),
        sort_key={"json.managers": lambda m: m["name"]},
    )
