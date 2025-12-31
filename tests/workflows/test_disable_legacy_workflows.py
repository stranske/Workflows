from __future__ import annotations

from pathlib import Path

import pytest

from tests.workflows.test_workflow_naming import EXPECTED_NAMES
from tools.disable_legacy_workflows import (
    CANONICAL_WORKFLOW_FILES,
    CANONICAL_WORKFLOW_NAMES,
    WorkflowAPIError,
    _extract_next_link,
    _extract_workflow_name,
    _http_request,
    _list_all_workflows,
    _normalize_allowlist,
    _normalized_slug,
    disable_legacy_workflows,
)


def test_canonical_workflow_files_match_inventory() -> None:
    on_disk = {path.name for path in Path(".github/workflows").glob("*.yml")}
    assert (
        on_disk == CANONICAL_WORKFLOW_FILES
    ), "Canonical workflow file allowlist drifted; update tools/disable_legacy_workflows.py."


def test_canonical_workflow_names_match_expected_mapping() -> None:
    assert (
        set(EXPECTED_NAMES) == CANONICAL_WORKFLOW_FILES
    ), "Workflow naming expectations drifted; keep EXPECTED_NAMES in sync with the allowlist."
    assert (
        set(EXPECTED_NAMES.values()) == CANONICAL_WORKFLOW_NAMES
    ), "Workflow display-name allowlist drifted; synchronize EXPECTED_NAMES in tests/test_workflow_naming.py."


def test_disable_handles_non_disableable_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = {
        "id": 172852138,
        "name": "Codespaces Prebuilds",
        "path": "dynamic/codespaces/create_codespaces_prebuilds",
        "state": "active",
    }

    def fake_list_all_workflows(base_url: str, headers: dict[str, str]) -> list[dict[str, object]]:
        return [target]

    def fake_http_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        data: bytes | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        raise WorkflowAPIError(
            status_code=422,
            reason="Unprocessable Entity",
            url="https://api.github.com/repos/stranske/Workflows/actions/workflows/172852138/disable",
            body='{"message":"Unable to disable this workflow."}',
        )

    monkeypatch.setattr(
        "tools.disable_legacy_workflows._list_all_workflows",
        fake_list_all_workflows,
        raising=True,
    )
    monkeypatch.setattr(
        "tools.disable_legacy_workflows._http_request",
        fake_http_request,
        raising=True,
    )

    summary = disable_legacy_workflows(
        repository="stranske/Workflows",
        token="dummy-token",
        dry_run=False,
        extra_allow=(),
    )

    assert summary["disabled"] == []
    assert summary["kept"] == []
    assert summary["skipped"] == [
        "(unsupported) Codespaces Prebuilds (create_codespaces_prebuilds)"
    ]


def test_extract_next_link_handles_missing_header() -> None:
    assert _extract_next_link(None) is None
    assert _extract_next_link("") is None


def test_extract_next_link_scans_all_params_for_next_relation() -> None:
    header = '<https://api.github.com?page=2>; foo="bar"; rel="next"'
    assert _extract_next_link(header) == "https://api.github.com?page=2"


def test_extract_next_link_ignores_non_next_relations() -> None:
    header = ", ".join(
        [
            '<https://api.github.com?page=2>; rel="prev"',
            '<https://api.github.com?page=3>; rel="last"',
        ]
    )
    assert _extract_next_link(header) is None


def test_extract_next_link_handles_multiple_segments() -> None:
    header = ", ".join(
        [
            '<https://api.github.com?page=2>; rel="prev"',
            '<https://api.github.com?page=3>; type="json"; rel="next"',
        ]
    )
    assert _extract_next_link(header) == "https://api.github.com?page=3"


def test_normalize_allowlist_trims_and_splits_values() -> None:
    values = [" foo , bar", "baz", "", "bar"]
    assert _normalize_allowlist(values) == {"foo", "bar", "baz"}


def test_normalize_allowlist_skips_empty_tokens() -> None:
    assert _normalize_allowlist([" , , ", " "]) == set()


def test_normalized_slug_handles_disabled_suffix() -> None:
    assert _normalized_slug(Path("ci.yml")) == "ci.yml"
    assert _normalized_slug(Path("ci.yml.disabled")) == "ci.yml"


def test_extract_workflow_name_prefers_yaml_name(tmp_path: Path) -> None:
    path = tmp_path / "workflow.yml"
    path.write_text("name: Example Workflow\non: push\n", encoding="utf-8")

    assert _extract_workflow_name(path) == "Example Workflow"


def test_extract_workflow_name_falls_back_on_parse_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "workflow.yml"
    path.write_text("name: 'Fallback Workflow'\n::\n", encoding="utf-8")

    class FakeYamlError(Exception):
        pass

    def raise_error(_: str) -> None:
        raise FakeYamlError("bad yaml")

    monkeypatch.setattr("tools.disable_legacy_workflows.yaml.safe_load", raise_error)
    monkeypatch.setattr("tools.disable_legacy_workflows.yaml.YAMLError", FakeYamlError)

    assert _extract_workflow_name(path) == "Fallback Workflow"


def test_http_request_and_list_all_workflows_stubs_return_empty() -> None:
    assert _list_all_workflows("https://example.com", headers={}) == []
    body, headers = _http_request("GET", "https://example.com", headers={})
    assert body == b""
    assert headers == {}
