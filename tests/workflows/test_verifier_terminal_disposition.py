import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

MIN_CODEX_CLI_BY_MODEL = {
    "gpt-5.6-terra": (0, 144, 1),
    "gpt-5.5": (0, 125, 0),
}


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse_version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    assert match, f"Could not parse semantic version from: {value!r}"
    return tuple(int(part) for part in match.groups())


def _extract_codex_cli_pin() -> tuple[int, int, int]:
    package_root = ROOT / ".github/actions/verifier-codex-cli"
    package = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    lockfile = json.loads((package_root / "package-lock.json").read_text(encoding="utf-8"))
    declared = package["dependencies"]["@openai/codex"]
    locked = lockfile["packages"]["node_modules/@openai/codex"]["version"]
    assert (
        declared == locked
    ), "package.json and package-lock.json must agree on the Codex CLI version"
    return _parse_version_tuple(declared)


def _model_candidates(resolve_step: dict) -> list[str]:
    default_model = resolve_step["env"]["DEFAULT_CODEX_MODEL"]
    fallback_models = resolve_step["env"]["FALLBACK_CODEX_MODELS"].split()
    return [default_model, *fallback_models]


def test_reusable_verifier_uploads_terminal_disposition_artifact() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-agents-verifier.yml")
    steps = workflow["jobs"]["verifier"]["steps"]

    resolve_step = next(
        step for step in steps if step.get("name") == "Resolve Codex verifier model"
    )
    install_step = next(step for step in steps if step.get("name") == "Install Codex CLI")
    parse_step = next(
        step for step in steps if step.get("name") == "Parse verifier verdict (checkbox mode)"
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
    assert install_step.get("id") == "codex_cli"
    assert (
        resolve_step.get("if")
        == "steps.context.outputs.should_run == 'true' && inputs.mode != 'evaluate'"
    )
    assert install_step["env"]["CODEX_CLI_PACKAGE"] == "@openai/codex@0.144.1"
    assert (
        'npm ci --prefix "$codex_cli_prefix" --ignore-scripts' in install_step["run"]
        or "npm ci --prefix .workflows-lib/.github/actions/verifier-codex-cli --ignore-scripts"
        in install_step["run"]
    )
    assert ".workflows-lib/.github/actions/verifier-codex-cli" in install_step["run"]
    assert 'echo "$codex_bin_dir" >> "$GITHUB_PATH"' in install_step["run"]
    assert 'codex_bin_dir="${codex_cli_prefix}/node_modules/.bin"' in install_step["run"]
    assert 'codex_cli="${codex_bin_dir}/codex"' in install_step["run"]
    assert 'echo "CODEX_CLI=${codex_cli}" >> "$GITHUB_ENV"' in install_step["run"]
    assert "CODEX_CLI_PACKAGE" in install_step["run"]  # env used, not dead
    # Run verifier must invoke the pinned local binary, not bare `codex`.
    assert '"$CODEX_CLI" exec' in run_step["run"]
    assert "node_modules/.bin/codex" in run_step["run"]
    assert '[ -z "${CODEX_CLI:-}" ] || [ ! -x "${CODEX_CLI}" ]' in run_step["run"]
    assert re.search(r"(?m)^(?:\s*)codex exec\b", run_step["run"]) is None
    checkout_step = next(
        step
        for step in steps
        if step.get("name") == "Checkout Workflows scripts"
        or (
            isinstance(step.get("with"), dict)
            and step["with"].get("repository") == "stranske/Workflows"
            and "sparse-checkout" in step["with"]
        )
    )
    sparse = str((checkout_step.get("with") or {}).get("sparse-checkout", ""))
    assert ".github/actions/verifier-codex-cli" in sparse
    assert resolve_step["env"]["DEFAULT_CODEX_MODEL"] == "gpt-5.6-terra"
    assert resolve_step["env"]["FALLBACK_CODEX_MODELS"] == "gpt-5.5"
    assert resolve_step["env"]["VERIFIER_MODE"] == "${{ inputs.mode }}"
    assert "fallback-unsupported-chatgpt-codex-model" in resolve_step["run"]
    assert "*-codex*" in resolve_step["run"]
    assert '[ "$model" = "$DEFAULT_CODEX_MODEL" ]' in resolve_step["run"]
    assert 'candidates="$DEFAULT_CODEX_MODEL $FALLBACK_CODEX_MODELS"' in resolve_step["run"]
    assert "Candidate order" in resolve_step["run"]
    assert '[ "${VERIFIER_MODE:-}" = "checkbox" ]' in resolve_step["run"]
    assert "json.load(open(sys.argv[1]))" in parse_step["run"]
    assert "from pathlib import Path" not in parse_step["run"]
    assert "CODEX_MODEL_CANDIDATES" in run_step["env"]
    assert 'for codex_model in "${codex_models[@]}"; do' in run_step["run"]
    assert '--model "$codex_model"' in run_step["run"]
    assert "runtime-fallback-model-unavailable" in run_step["run"]
    assert "steps.unified_verdict.outputs.verdict" in collect_step["env"]["VERDICT"]
    assert collect_step["env"]["CODEX_MODEL"] == (
        "${{ steps.codex.outputs.model || steps.codex_model.outputs.model }}"
    )
    assert " ".join(collect_step["env"]["CODEX_MODEL_SELECTION_REASON"].split()) == (
        "${{ steps.codex.outputs.selection_reason || steps.codex_model.outputs.selection_reason }}"
    )
    assert collect_step["env"]["CODEX_CLI_VERSION"] == "${{ steps.codex_cli.outputs.version }}"
    assert '"codex_cli_version": codex_cli_version' in collect_step["run"]
    assert write_step.get("if") == "always()"
    assert write_step["env"]["CODEX_MODEL"] == (
        "${{ steps.codex.outputs.model || steps.codex_model.outputs.model }}"
    )
    assert " ".join(write_step["env"]["CODEX_MODEL_SELECTION_REASON"].split()) == (
        "${{ steps.codex.outputs.selection_reason || steps.codex_model.outputs.selection_reason }}"
    )
    assert write_step["env"]["CODEX_CLI_VERSION"] == "${{ steps.codex_cli.outputs.version }}"
    assert write_step["env"]["SOURCE_ISSUE_NUMBERS_JSON"] == (
        "${{ steps.context.outputs.issue_numbers || '[]' }}"
    )
    assert "verifier-terminal-disposition" in write_step["run"]
    assert "normalizeVerifierFollowupLedger" in write_step["run"]
    assert "verifier-followup-ledger.ndjson" in write_step["run"]
    assert "followup_policy" in write_step["run"]
    assert "policyAction" in write_step["run"]
    assert "depth_limit_exceeded" in write_step["run"]
    assert "concernsHash" in write_step["run"]
    assert "CHAIN_DEPTH" in write_step["env"]
    assert "llm_model" in write_step["run"]
    assert "model_selection_reason" in write_step["run"]
    assert "llm_cli_version" in write_step["run"]
    assert "source-issue" in write_step["run"]
    assert "pull-request" in write_step["run"]
    assert "verified-pass" in write_step["run"]
    assert "needs-human" in write_step["run"]
    assert upload_step.get("if") == "always()"
    assert upload_step.get("uses") == "actions/upload-artifact@v7"
    assert upload_step["with"]["name"] == "verifier-terminal-disposition-${{ github.run_id }}"
    assert "agent-metrics/verifier-terminal-disposition.ndjson" in upload_step["with"]["path"]
    assert "agent-metrics/verifier-followup-ledger.ndjson" in upload_step["with"]["path"]
    assert upload_step["with"]["if-no-files-found"] == "error"
    assert upload_step["with"]["retention-days"] == 14


def test_reusable_verifier_codex_model_cli_compatibility_contract() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-agents-verifier.yml")
    steps = workflow["jobs"]["verifier"]["steps"]
    resolve_step = next(
        step for step in steps if step.get("name") == "Resolve Codex verifier model"
    )
    install_step = next(step for step in steps if step.get("name") == "Install Codex CLI")

    installed_cli = _extract_codex_cli_pin()
    assert install_step["env"]["CODEX_CLI_PACKAGE"] == (
        "@openai/codex@" + ".".join(map(str, installed_cli))
    )
    candidates = _model_candidates(resolve_step)
    unreviewed_models = [model for model in candidates if model not in MIN_CODEX_CLI_BY_MODEL]
    assert not unreviewed_models, (
        "Verifier Codex model candidates need an explicit reviewed minimum CLI mapping: "
        + ", ".join(unreviewed_models)
    )

    for model in candidates:
        minimum_cli = MIN_CODEX_CLI_BY_MODEL[model]
        assert installed_cli >= minimum_cli, (
            f"Verifier model {model} requires @openai/codex >= {minimum_cli}, "
            f"but reusable-agents-verifier.yml installs {installed_cli}."
        )


def test_reusable_verifier_floors_ci_failure_comments_before_posting() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-agents-verifier.yml")
    steps = workflow["jobs"]["verifier"]["steps"]
    names = [step.get("name") for step in steps]

    eval_floor = next(
        step
        for step in steps
        if step.get("name") == "Apply CI failure hard gate to LLM evaluation comment"
    )
    compare_floor = next(
        step
        for step in steps
        if step.get("name") == "Apply CI failure hard gate to comparison comment"
    )

    assert names.index(eval_floor["name"]) < names.index("Post LLM evaluation comment")
    assert names.index(compare_floor["name"]) < names.index("Post comparison report comment")
    assert "steps.context.outputs.ci_failed == 'true'" in eval_floor["if"]
    assert "steps.llm_evaluate.outputs.verdict == 'PASS'" in eval_floor["if"]
    assert "evaluation-comment.md" in eval_floor["run"]
    assert "**Verdict:** CONCERNS (CI failure hard gate)" in eval_floor["run"]
    assert "steps.context.outputs.ci_failed == 'true'" in compare_floor["if"]
    assert "steps.llm_compare.outputs.verdict == 'PASS'" in compare_floor["if"]
    assert "comparison-comment.md" in compare_floor["run"]
    assert "Provider rows below are preserved for auditability" in compare_floor["run"]
