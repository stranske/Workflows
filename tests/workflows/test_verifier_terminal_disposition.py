from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_reusable_verifier_uploads_terminal_disposition_artifact() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-agents-verifier.yml")
    steps = workflow["jobs"]["verifier"]["steps"]

    resolve_step = next(
        step for step in steps if step.get("name") == "Resolve Codex verifier model"
    )
    run_step = next(step for step in steps if step.get("name") == "Run verifier (checkbox mode)")
    collect_step = next(step for step in steps if step.get("name") == "Collect verifier metrics")
    write_step = next(
        step for step in steps if step.get("name") == "Write verifier terminal disposition"
    )
    upload_step = next(
        step for step in steps if step.get("name") == "Upload verifier terminal disposition"
    )

    assert resolve_step.get("id") == "codex_model"
    assert (
        resolve_step.get("if")
        == "steps.context.outputs.should_run == 'true' && inputs.mode != 'evaluate'"
    )
    assert resolve_step["env"]["DEFAULT_CODEX_MODEL"] == "gpt-5.5"
    assert resolve_step["env"]["FALLBACK_CODEX_MODELS"] == "gpt-5.4 gpt-5.3-codex"
    assert resolve_step["env"]["VERIFIER_MODE"] == "${{ inputs.mode }}"
    assert "fallback-unsupported-chatgpt-codex-model" in resolve_step["run"]
    assert "gpt-5.2-codex" in resolve_step["run"]
    assert 'candidates="$DEFAULT_CODEX_MODEL $FALLBACK_CODEX_MODELS"' in resolve_step["run"]
    assert "Candidate order" in resolve_step["run"]
    assert '[ "${VERIFIER_MODE:-}" = "checkbox" ]' in resolve_step["run"]
    assert "CODEX_MODEL_CANDIDATES" in run_step["env"]
    assert 'for codex_model in "${codex_models[@]}"; do' in run_step["run"]
    assert '--model "$codex_model"' in run_step["run"]
    assert "runtime-fallback-model-unavailable" in run_step["run"]
    assert "steps.unified_verdict.outputs.verdict" in collect_step["env"]["VERDICT"]
    assert collect_step["env"]["CODEX_MODEL"] == (
        "${{ steps.codex.outputs.model || steps.codex_model.outputs.model }}"
    )
    assert collect_step["env"]["CODEX_MODEL_SELECTION_REASON"] == (
        "${{ steps.codex.outputs.selection_reason || "
        "steps.codex_model.outputs.selection_reason }}"
    )
    assert write_step.get("if") == "always()"
    assert write_step["env"]["CODEX_MODEL"] == (
        "${{ steps.codex.outputs.model || steps.codex_model.outputs.model }}"
    )
    assert write_step["env"]["CODEX_MODEL_SELECTION_REASON"] == (
        "${{ steps.codex.outputs.selection_reason || "
        "steps.codex_model.outputs.selection_reason }}"
    )
    assert write_step["env"]["SOURCE_ISSUE_NUMBERS_JSON"] == (
        "${{ steps.context.outputs.issue_numbers || '[]' }}"
    )
    assert "verifier-terminal-disposition" in write_step["run"]
    assert "llm_model" in write_step["run"]
    assert "model_selection_reason" in write_step["run"]
    assert "source-issue" in write_step["run"]
    assert "pull-request" in write_step["run"]
    assert "verified-pass" in write_step["run"]
    assert "needs-human" in write_step["run"]
    assert upload_step.get("if") == "always()"
    assert upload_step.get("uses") == "actions/upload-artifact@v7"
    assert upload_step["with"]["name"] == "verifier-terminal-disposition-${{ github.run_id }}"
    assert "agent-metrics/verifier-terminal-disposition.ndjson" in upload_step["with"]["path"]
    assert upload_step["with"]["if-no-files-found"] == "error"
    assert upload_step["with"]["retention-days"] == 14
