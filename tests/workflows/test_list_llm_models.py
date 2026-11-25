"""Exercise the shipped catalog shell without contacting a provider."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

TEMPLATE = Path("templates/consumer-repo")
WORKFLOW = yaml.safe_load((TEMPLATE / ".github/workflows/list-llm-models.yml").read_text())
STEPS = WORKFLOW["jobs"]["list-models"]["steps"]
REGISTRY = TEMPLATE / "config/model_registry.json"
PRIVATE_ID = "ft:private-provider-test:never-print"
PRIVATE_OWNER = "private-provider-owner-never-print"


@pytest.fixture
def catalog(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        """#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >> "$REQUESTS"
while (($#)); do
  if [[ "$1" == '--output' ]]; then
    cp "$RESPONSE" "$2"
    exit "$CURL_STATUS"
  fi
  shift
done
exit 99
"""
    )
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >> "$REQUESTS"
printf '%s\n' "$REPO_VISIBILITY"
exit "$GH_STATUS"
"""
    )
    for stub in (curl, gh):
        stub.chmod(0o700)
    config = tmp_path / "config"
    config.mkdir()
    shutil.copyfile(REGISTRY, config / "model_registry.json")
    return tmp_path


def run_step(catalog: Path, step_id: str, response="", **settings):
    script = next(step["run"] for step in STEPS if step.get("id") == step_id)
    (catalog / "response").write_text(response)
    env = {
        **os.environ,
        "PATH": f"{catalog / 'bin'}:{os.environ['PATH']}",
        "REQUESTS": str(catalog / "requests"),
        "RESPONSE": str(catalog / "response"),
        "RUNNER_TEMP": str(catalog),
        "GITHUB_WORKSPACE": str(catalog),
        "GITHUB_REPOSITORY": "stranske/trip-planner",
        "GITHUB_OUTPUT": str(catalog / "output"),
        "GITHUB_STEP_SUMMARY": str(catalog / "summary"),
        "OPENAI_API_KEY": "test-fixture-key",
        "PRIVATE_CATALOG": "false",
        "CURL_STATUS": "0",
        **settings,
    }
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)


def test_legacy_github_choice_is_explicit_and_calls_no_provider(catalog):
    result = run_step(catalog, "provider", PROVIDER="github-models", ON_DEFAULT_BRANCH="true")
    assert result.returncode == 1
    assert "retired on July 30, 2026" in result.stdout
    assert not (catalog / "requests").exists()
    assert run_step(catalog, "provider", PROVIDER="both", ON_DEFAULT_BRANCH="true").returncode == 0
    assert (
        run_step(catalog, "provider", PROVIDER="openai", ON_DEFAULT_BRANCH="false").returncode == 1
    )
    assert all("models.inference.ai.azure.com" not in step.get("run", "") for step in STEPS)


@pytest.mark.parametrize(
    ("event_private", "live_visibility", "gh_status", "expected_private"),
    [
        ("false", "public", "0", "false"),
        ("true", "private", "0", "true"),
        ("true", "internal", "0", "false"),
        ("true", "public", "0", "false"),
        ("true", "private", "1", "false"),
    ],
)
def test_full_catalog_requires_confirmed_private_visibility(
    catalog, event_private, live_visibility, gh_status, expected_private
):
    result = run_step(
        catalog,
        "visibility",
        EVENT_PRIVATE=event_private,
        REPO_VISIBILITY=live_visibility,
        GH_STATUS=gh_status,
    )
    assert result.returncode == 0
    assert (catalog / "output").read_text() == f"private={expected_private}\n"
    assert (catalog / "requests").exists() == (event_private == "true")
    upload = next(step for step in STEPS if "upload-artifact" in step.get("uses", ""))
    assert "github.event.repository.private == true" in upload["if"]
    assert "steps.visibility.outputs.private == 'true'" in upload["if"]
    assert "steps.openai.outputs.artifact == 'true'" in upload["if"]


@pytest.mark.parametrize("private", [False, True])
def test_catalog_visibility_controls_rows_and_artifact(catalog, private):
    models = json.loads(REGISTRY.read_text())["models"]
    model_ids = dict.fromkeys(row["model_id"] for row in models if row["provider"] == "openai")
    known_id, not_returned = list(model_ids)[:2]
    rows = [
        {"id": known_id, "owned_by": PRIVATE_OWNER},
        {"id": PRIVATE_ID, "owned_by": PRIVATE_OWNER},
    ]
    payload = {"data": rows}
    result = run_step(catalog, "openai", json.dumps(payload), PRIVATE_CATALOG=str(private).lower())
    assert result.returncode == 0, result.stderr
    publication = result.stdout + result.stderr + (catalog / "summary").read_text()
    assert PRIVATE_ID not in publication and PRIVATE_OWNER not in publication
    assert f"`{not_returned}`" not in publication
    assert "https://api.openai.com/v1/models" in (catalog / "requests").read_text()
    artifact = catalog / "openai-model-catalog.json"
    if private:
        assert json.loads(artifact.read_text()) == payload
        assert (catalog / "output").read_text() == "artifact=true\n"
        assert known_id not in publication
    else:
        assert "public verifier subset" in publication
        assert f"`{known_id}`" in publication
        assert not artifact.exists()
        assert not (catalog / "output").exists()


@pytest.mark.parametrize(
    ("key", "endpoint_exit", "response", "exit_code", "message"),
    [
        ("", "0", "{}", 1, "Configure the OPENAI_API_KEY secret"),
        ("fake", "22", PRIVATE_ID, 1, "OpenAI model lookup failed"),
        ("fake", "0", '{"data":[{}]}', 1, "invalid model catalog response"),
        ("fake", "0", '{"data":[]}', 0, "returned no models for the configured key"),
        ("fake", "0", json.dumps({"data": [{"id": PRIVATE_ID}]}), 0, "no models that match"),
    ],
)
def test_openai_reports_distinct_no_rows_outcomes(
    catalog, key, endpoint_exit, response, exit_code, message
):
    result = run_step(catalog, "openai", response, OPENAI_API_KEY=key, CURL_STATUS=endpoint_exit)
    assert result.returncode == exit_code
    assert message in result.stdout
    assert PRIVATE_ID not in result.stdout + result.stderr + (catalog / "summary").read_text()
    assert (catalog / "requests").exists() == bool(key)
    assert not (catalog / "openai-model-catalog.json").exists()
