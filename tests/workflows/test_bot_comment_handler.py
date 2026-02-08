import yaml

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_reusable_bot_comment_handler_ignores_agents_paths() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-bot-comment-handler.yml")
    triggers = workflow.get("on") or workflow.get(True) or {}
    inputs = triggers.get("workflow_call", {}).get("inputs", {})

    ignored_paths = inputs.get("ignored_paths", {}).get("default")
    assert ignored_paths is not None
    assert ".agents/" in ignored_paths.split(",")

    bot_authors = inputs.get("bot_authors", {}).get("default", "")
    assert "chatgpt-codex-connector[bot]" in bot_authors


def test_template_bot_comment_handler_passes_agents_ignore() -> None:
    workflow = _load_yaml(
        ROOT / "templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml"
    )
    handle_job = workflow.get("jobs", {}).get("handle", {})
    inputs = handle_job.get("with", {})
    ignored_paths = inputs.get("ignored_paths", "")

    assert ".agents/" in ignored_paths.split(",")
