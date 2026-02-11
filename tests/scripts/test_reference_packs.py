"""Tests for scripts/reference_packs.py."""

from __future__ import annotations

import json
import subprocess
import sys
from base64 import b64decode
from pathlib import Path

import pytest
from scripts.reference_packs import (
    ReferencePackConfigError,
    build_checkout_plan,
    load_reference_packs,
    parse_reference_pack_config_text,
    parse_reference_packs,
    read_reference_pack_config_text,
    reference_pack_config_exists,
)


def _decode_github_output_value(value: str) -> str:
    return value.replace("%0D", "\r").replace("%0A", "\n").replace("%25", "%")


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
    assert snapshot.config_text is None
    assert snapshot.packs == []


def test_read_reference_pack_config_text_returns_none_when_missing(tmp_path: Path) -> None:
    config_path, config_text = read_reference_pack_config_text(tmp_path)

    assert config_path == tmp_path / ".github" / "reference_packs.json"
    assert config_text is None


def test_load_reference_packs_mapping_format(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_payload = {
        "trend-streamlit": {
            "repo": "trend/research",
            "ref": "main",
            "paths": ["apps/streamlit", "langchain"],
        }
    }
    config_text = json.dumps(config_payload)
    config_file.write_text(config_text, encoding="utf-8")

    snapshot = load_reference_packs(tmp_path)

    assert snapshot.exists is True
    assert snapshot.config_text == config_text
    assert len(snapshot.packs) == 1
    pack = snapshot.packs[0]
    assert pack.name == "trend-streamlit"
    assert pack.repo == "trend/research"
    assert pack.ref == "main"
    assert pack.paths == ["apps/streamlit", "langchain"]


def test_read_reference_pack_config_text_reads_present_file(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"packs":[]}', encoding="utf-8")

    config_path, config_text = read_reference_pack_config_text(tmp_path)

    assert config_path == config_file
    assert config_text == '{"packs":[]}'


def test_parse_reference_pack_config_text_valid() -> None:
    packs = parse_reference_pack_config_text(
        json.dumps(
            {
                "trend-streamlit": {
                    "repo": "trend/research",
                    "ref": "main",
                    "paths": ["apps/streamlit"],
                }
            }
        ),
        Path("/tmp/workspace/.github/reference_packs.json"),
    )

    assert len(packs) == 1
    assert packs[0].name == "trend-streamlit"


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


def test_build_checkout_plan_sets_reference_paths() -> None:
    packs = parse_reference_packs(
        {
            "packs": [
                {
                    "name": "trend-streamlit",
                    "repo": "trend/research",
                    "ref": "main",
                    "paths": ["apps/streamlit"],
                },
                {
                    "name": "baseline",
                    "repo": "trend/baseline",
                    "ref": "v1.2.3",
                    "paths": ["src", "README.md"],
                },
            ]
        }
    )

    plan = build_checkout_plan(packs)
    assert plan[0].checkout_path == ".reference/trend-streamlit"
    assert plan[1].checkout_path == ".reference/baseline"


def test_parse_reference_packs_rejects_extra_top_level_keys_in_list_format() -> None:
    with pytest.raises(
        ReferencePackConfigError,
        match=r"when using 'packs' format, no additional top-level keys are allowed",
    ):
        parse_reference_packs(
            {
                "packs": [
                    {
                        "name": "trend-streamlit",
                        "repo": "trend/research",
                        "ref": "main",
                        "paths": ["apps/streamlit"],
                    }
                ],
                "metadata": {"owner": "trend"},
            }
        )


def test_load_reference_packs_rejects_malformed_json(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"bad": ', encoding="utf-8")

    with pytest.raises(ReferencePackConfigError, match="Malformed JSON"):
        load_reference_packs(tmp_path)


def test_parse_reference_pack_config_text_rejects_malformed_json() -> None:
    with pytest.raises(ReferencePackConfigError, match="Malformed JSON in"):
        parse_reference_pack_config_text(
            '{"packs": [',
            Path("/tmp/workspace/.github/reference_packs.json"),
        )


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

    with pytest.raises(
        ReferencePackConfigError,
        match=r"Invalid config in .*reference_packs\.json: ref must be a non-empty string",
    ):
        load_reference_packs(tmp_path)


def test_parse_reference_pack_config_text_rejects_invalid_structure() -> None:
    with pytest.raises(
        ReferencePackConfigError,
        match=r"Invalid config in .*reference_packs\.json: paths must be a non-empty array of strings",
    ):
        parse_reference_pack_config_text(
            json.dumps(
                {
                    "trend-streamlit": {
                        "repo": "trend/research",
                        "ref": "main",
                        "paths": [],
                    }
                }
            ),
            Path("/tmp/workspace/.github/reference_packs.json"),
        )


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
        match=r"Invalid config in .*reference_packs\.json: paths\[\] must not traverse parent directories",
    ):
        load_reference_packs(tmp_path)


def test_load_reference_packs_rejects_non_utf8_config(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_bytes(b"\x80\x81")

    with pytest.raises(
        ReferencePackConfigError,
        match=r"Malformed text in .*reference_packs\.json: file must be valid UTF-8",
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
    assert payload["checkout_plan"][0]["name"] == "trend-streamlit"
    assert payload["checkout_plan"][0]["checkout_path"] == ".reference/trend-streamlit"


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
    assert f"Invalid config in {config_file}" in result.stderr
    assert "must contain a JSON object" in result.stderr


def test_cli_returns_malformed_json_location_details(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"packs": [', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/reference_packs.py", "--workspace", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Reference packs config error: Malformed JSON in" in result.stderr
    assert str(config_file) in result.stderr
    assert "line " in result.stderr
    assert "column " in result.stderr


def test_cli_github_output_includes_presence_and_path(tmp_path: Path) -> None:
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
    github_output = tmp_path / "github_output.txt"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/reference_packs.py",
            "--workspace",
            str(tmp_path),
            "--format",
            "github-output",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"GITHUB_OUTPUT": str(github_output)},
    )

    assert result.returncode == 0
    output_lines = github_output.read_text(encoding="utf-8")
    assert "reference_packs_exists=true" in output_lines
    assert f"reference_packs_path={config_file}" in output_lines
    assert "reference_packs_count=1" in output_lines
    assert "reference_packs_payload_json=" in output_lines
    assert "reference_packs_checkout_plan_json=" in output_lines
    assert "reference_packs_config_text=" in output_lines
    assert "reference_packs_config_text_b64=" in output_lines

    line_map = dict(
        line.split("=", 1)
        for line in output_lines.splitlines()
        if "=" in line and line.startswith("reference_packs_")
    )
    payload_json = _decode_github_output_value(line_map["reference_packs_payload_json"])
    parsed_payload = json.loads(payload_json)
    assert parsed_payload["exists"] is True
    assert parsed_payload["packs"][0]["name"] == "trend-streamlit"
    assert parsed_payload["checkout_plan"][0]["checkout_path"] == ".reference/trend-streamlit"

    checkout_plan_json = _decode_github_output_value(line_map["reference_packs_checkout_plan_json"])
    checkout_plan = json.loads(checkout_plan_json)
    assert checkout_plan[0]["name"] == "trend-streamlit"
    assert checkout_plan[0]["checkout_path"] == ".reference/trend-streamlit"

    config_text_direct = _decode_github_output_value(line_map["reference_packs_config_text"])
    assert json.loads(config_text_direct)["trend-streamlit"]["repo"] == "trend/research"

    config_b64 = line_map["reference_packs_config_text_b64"]
    config_text = b64decode(config_b64.encode("ascii")).decode("utf-8")
    assert json.loads(config_text)["trend-streamlit"]["repo"] == "trend/research"


def test_cli_github_output_absent_config_reports_false(tmp_path: Path) -> None:
    github_output = tmp_path / "github_output.txt"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/reference_packs.py",
            "--workspace",
            str(tmp_path),
            "--format",
            "github-output",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"GITHUB_OUTPUT": str(github_output)},
    )

    assert result.returncode == 0
    output_lines = github_output.read_text(encoding="utf-8")
    assert "reference_packs_exists=false" in output_lines
    assert "reference_packs_count=0" in output_lines
    assert "reference_packs_config_text=" in output_lines
    assert "reference_packs_config_text_b64=" in output_lines


def test_cli_github_output_config_text_preserves_percent_and_newline(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "reference_packs.json"
    config_file.parent.mkdir(parents=True)
    config_text = (
        "{\n"
        '  "trend-streamlit": {\n'
        '    "repo": "trend/research",\n'
        '    "ref": "release%2Fmain",\n'
        '    "paths": ["apps/streamlit"]\n'
        "  }\n"
        "}"
    )
    config_file.write_text(config_text, encoding="utf-8")
    github_output = tmp_path / "github_output.txt"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/reference_packs.py",
            "--workspace",
            str(tmp_path),
            "--format",
            "github-output",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"GITHUB_OUTPUT": str(github_output)},
    )

    assert result.returncode == 0
    line_map = dict(
        line.split("=", 1)
        for line in github_output.read_text(encoding="utf-8").splitlines()
        if "=" in line and line.startswith("reference_packs_")
    )
    decoded = _decode_github_output_value(line_map["reference_packs_config_text"])
    assert decoded == config_text
