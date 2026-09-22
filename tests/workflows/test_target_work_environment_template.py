from pathlib import Path

import yaml
from scripts.list_registered_consumer_repos import extract_repos

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DOC = ROOT / "templates/consumer-repo/docs/TARGET_WORK_ENVIRONMENT.md"
DOC_PATH = "docs/TARGET_WORK_ENVIRONMENT.md"
DOC_FOCUS = "confirmed work-environment delivery constraints for fleet design"


def test_template_documents_hosting_block() -> None:
    text = TEMPLATE_DOC.read_text(encoding="utf-8")

    assert "## Blocked Without Redesign" in text
    assert "no server-hosted, database-backed application" in text


def test_webassembly_marked_unverified() -> None:
    text = TEMPLATE_DOC.read_text(encoding="utf-8")

    assert "## Unverified" in text
    assert "WebAssembly" in text
    assert "Pyodide" in text


def test_template_doc_is_linked_and_manifest_managed() -> None:
    for context_file in ("AGENTS.md", "CLAUDE.md"):
        context = (ROOT / "templates/consumer-repo" / context_file).read_text(encoding="utf-8")
        assert DOC_PATH in context

    manifest = yaml.safe_load((ROOT / ".github/sync-manifest.yml").read_text(encoding="utf-8"))
    matching_entries = [entry for entry in manifest["docs"] if entry.get("target") == DOC_PATH]
    assert matching_entries == [
        {
            "source": DOC_PATH,
            "target": DOC_PATH,
            "description": "Confirmed target work-environment capabilities and blocked delivery shapes",
        }
    ]


def test_every_registered_consumer_tracks_target_environment_doc() -> None:
    local_config = yaml.safe_load(
        (ROOT / "templates/consumer-repo/config/source_of_truth_docs.yml").read_text(
            encoding="utf-8"
        )
    )
    assert {entry["path"]: entry["focus"] for entry in local_config["consumer"]["docs"]}[
        DOC_PATH
    ] == DOC_FOCUS

    fleet_config = yaml.safe_load(
        (ROOT / "config/source_of_truth_docs.yml").read_text(encoding="utf-8")
    )
    registered = extract_repos(ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml")

    missing = []
    wrong_focus = []
    for repo in registered:
        repo_config = fleet_config["repos"].get(repo)
        if repo_config is None:
            missing.append(repo)
            continue
        docs = {entry["path"]: entry["focus"] for entry in repo_config.get("docs", [])}
        if DOC_PATH not in docs:
            missing.append(repo)
        elif docs[DOC_PATH] != DOC_FOCUS:
            wrong_focus.append(repo)

    assert not missing, f"registered consumers missing {DOC_PATH}: {missing}"
    assert not wrong_focus, f"registered consumers with wrong focus: {wrong_focus}"
