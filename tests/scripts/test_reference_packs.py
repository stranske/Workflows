"""Tests for scripts/reference_packs.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.reference_packs import (
    ReferencePackConfigError,
    load_reference_packs,
    parse_reference_packs,
    reference_pack_config_exists,
)


def test_reference_pack_config_exists_when_missing(tmp_path: Path) -> None:
    assert reference_pack_config_exists(tmp_path) is False


def test_reference_pack_config_exists_when_present(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("{}", encoding="utf-8")

    assert reference_pack_config_exists(tmp_path) is True


def test_load_reference_packs_returns_empty_when_file_absent(tmp_path: Path) -> None:
    snapshot = load_reference_packs(tmp_path)

    assert snapshot.exists is False
    assert snapshot.packs == []


def test_load_reference_packs_mapping_format(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "trend-streamlit": {
                    "repo": "trend/research",
                    "ref": "main",
                    "paths": ["apps/streamlit", "langchain"],
                }
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_reference_packs(tmp_path)

    assert snapshot.exists is True
    assert len(snapshot.packs) == 1
    pack = snapshot.packs[0]
    assert pack.name == "trend-streamlit"
    assert pack.repo == "trend/research"
    assert pack.ref == "main"
    assert pack.paths == ["apps/streamlit", "langchain"]


def test_parse_reference_packs_list_format() -> None:
    packs = parse_reference_packs(
        {
            "packs": [
                {
                    "name": "trend-streamlit",
                    "repo": "trend/research",
                    "ref": "main",
                    "paths": ["apps/streamlit"],
                }
            ]
        }
    )

    assert len(packs) == 1
    assert packs[0].name == "trend-streamlit"


def test_load_reference_packs_rejects_malformed_json(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"bad": ', encoding="utf-8")

    with pytest.raises(ReferencePackConfigError, match="Malformed JSON"):
        load_reference_packs(tmp_path)


def test_load_reference_packs_rejects_missing_required_fields(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "trend-streamlit": {
                    "repo": "trend/research",
                    "paths": ["apps/streamlit"],
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReferencePackConfigError, match="ref must be a non-empty string"):
        load_reference_packs(tmp_path)


def test_load_reference_packs_rejects_parent_directory_paths(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "trend-streamlit": {
                    "repo": "trend/research",
                    "ref": "main",
                    "paths": ["../secrets"],
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ReferencePackConfigError,
        match=r"paths\[\] must not traverse parent directories",
    ):
        load_reference_packs(tmp_path)


def test_cli_json_output_valid_config(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "trend-streamlit": {
                    "repo": "trend/research",
                    "ref": "main",
                    "paths": ["apps/streamlit"],
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/reference_packs.py", "--workspace", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["exists"] is True
    assert payload["packs"][0]["name"] == "trend-streamlit"


def test_cli_returns_error_for_invalid_config(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("[]", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/reference_packs.py", "--workspace", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Reference packs config error" in result.stderr
    assert "must contain a JSON object" in result.stderr
