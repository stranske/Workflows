from pathlib import Path

import yaml


def test_setup_api_client_emits_redacted_contract_output() -> None:
    action_path = Path(".github/actions/setup-api-client/action.yml")
    action = yaml.safe_load(action_path.read_text(encoding="utf-8"))

    outputs = action.get("outputs") or {}
    assert outputs["setup_contract"]["value"] == "${{ steps.export-tokens.outputs.setup_contract }}"

    export_step = next(
        step for step in action["runs"]["steps"] if step.get("id") == "export-tokens"
    )
    script = export_step["run"]

    assert "workflows-api-client-setup/v1" in script
    assert "available_token_names" in script
    assert "auth_modes" in script
    assert "dependency_state" in script
    assert "octokit_rest_ready" in script
    assert "octokit_auth_app_ready" in script
    assert "lru_cache_ready" in script
    assert "credential_names" in script
    assert "printf 'setup_contract=%s\\n'" in script

    template_text = Path(
        "templates/consumer-repo/.github/actions/setup-api-client/action.yml"
    ).read_text(encoding="utf-8")
    assert "workflows-api-client-setup/v1" in template_text
    assert "setup_contract" in template_text
