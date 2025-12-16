from __future__ import annotations

from pathlib import Path

import pytest
from tools.disable_legacy_workflows import (
    CANONICAL_WORKFLOW_FILES,
    CANONICAL_WORKFLOW_NAMES,
    WorkflowAPIError,
    _extract_next_link,
    _normalize_allowlist,
    disable_legacy_workflows,
)

from tests.workflows.test_workflow_naming import EXPECTED_NAMES


def test_canonical_workflow_files_match_inventory() -> None:
    on_disk = {path.name for path in Path(".github/workflows").glob("*.yml")}
    assert (
        on_disk == CANONICAL_WORKFLOW_FILES
    ), "Canonical workflow file allowlist drifted; update tools/disable_legacy_workflows.py."


def test_canonical_workflow_names_match_expected_mapping() -> None:
    assert (
        set(EXPECTED_NAMES) == CANONICAL_WORKFLOW_FILES
    ), "Workflow naming expectations drifted; keep EXPECTED_NAMES in sync with the allowlist."
    assert CANONICAL_WORKFLOW_NAMES == set(
        EXPECTED_NAMES.values()
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
            url="https://api.github.com/repos/stranske/Trend_Model_Project/actions/workflows/172852138/disable",
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
        repository="stranske/Trend_Model_Project",
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
