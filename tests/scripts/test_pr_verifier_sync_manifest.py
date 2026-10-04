"""Regression coverage for synced pr_verifier dependencies."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml
from scripts.langchain import pr_verifier

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github" / "sync-manifest.yml"
PR_VERIFIER = ROOT / "scripts" / "langchain" / "pr_verifier.py"
API_CLIENT = ROOT / "scripts" / "api_client.py"
TEMPLATE_API_CLIENT = ROOT / "templates" / "consumer-repo" / "scripts" / "api_client.py"


def _manifest_sources() -> set[str]:
    sources: set[str] = set()
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- source: "):
            sources.add(stripped.removeprefix("- source: ").strip())
    return sources


def test_pr_verifier_imports_api_client_from_synced_manifest() -> None:
    tree = ast.parse(PR_VERIFIER.read_text(encoding="utf-8"))

    imports_api_client = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "scripts"
        and any(alias.name == "api_client" for alias in node.names)
        for node in ast.walk(tree)
    )

    assert imports_api_client, "pr_verifier.py should continue importing scripts.api_client"

    sources = _manifest_sources()
    assert "scripts/langchain/pr_verifier.py" in sources
    assert "scripts/api_client.py" in sources


def test_pr_verifier_api_client_is_available_in_consumer_template() -> None:
    assert TEMPLATE_API_CLIENT.exists()
    assert TEMPLATE_API_CLIENT.read_text(encoding="utf-8") == API_CLIENT.read_text(encoding="utf-8")


def test_pr_verifier_copy_delivery_includes_doc_lineage() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entry = next(
        entry
        for entry in manifest["scripts"]
        if entry["source"] == "scripts/langchain/pr_verifier.py"
    )
    assert entry["delivery"] == "copy"
    assert entry.get("source_tree", "root") == "root"
    assert entry.get("target", entry["source"]) == "scripts/langchain/pr_verifier.py"
    consumer = "stranske/Doc-Lineage"
    assert not entry.get("include_repos") or consumer in entry["include_repos"]
    assert consumer not in {rule["repo"] for rule in entry.get("skip_repos", [])}
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml").read_text(encoding="utf-8")
    )
    assert consumer in workflow["env"]["REGISTERED_CONSUMER_REPOS"].splitlines()


def _text_diff(path: str, added: str = "new") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+{added}\n"
    )


@pytest.mark.parametrize(
    "binary_marker", ["Binary files a/logo.png and b/logo.png differ", "GIT binary patch"]
)
def test_doc_lineage_binary_finding_blocks_pass(binary_marker: str) -> None:
    diff = f"diff --git a/logo.png b/logo.png\n{binary_marker}\n"
    inputs = pr_verifier.build_prompt_inputs("Review changed files.", diff)
    assert not inputs.coverage.sufficient
    assert inputs.coverage.files[0].status == "omitted"
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True), inputs.coverage
    )
    assert result.verdict == "CONCERNS"


def test_doc_lineage_summary_finding_blocks_pass() -> None:
    inputs = pr_verifier.build_prompt_inputs(
        "Review changed files.", "1 file changed, 2 insertions(+)"
    )
    assert inputs.coverage.code == "unavailable"
    assert not inputs.coverage.sufficient
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True), inputs.coverage
    )
    assert result.verdict == "CONCERNS"


@pytest.mark.parametrize("budget", [0, 1, 40, 512, 4096])
@pytest.mark.parametrize("binary", [False, True])
def test_doc_lineage_omission_note_stays_within_diff_budget(budget: int, binary: bool) -> None:
    paths = [f"src/{'long_directory/' * 30}module_{index}.py" for index in range(30)]
    diff = "".join(
        (
            f"diff --git a/{path} b/{path}\nBinary files a/{path} and b/{path} differ\n"
            if binary
            else _text_diff(path, "x" * 2000)
        )
        for path in paths
    )
    block, status, files, included, total = pr_verifier._build_code_block(diff, budget)
    assert len(block) <= budget
    assert status == "truncated"
    assert len(files) == len(paths)
    assert all(item.status == "omitted" for item in files)
    assert included == 0
    assert total == len(diff)
    if budget >= 512:
        assert "30 changed file(s) omitted entirely" in block
        assert paths[0] not in block


def test_doc_lineage_omission_note_keeps_reviewable_text_within_budget() -> None:
    text = _text_diff("src/app.py")
    binary = "diff --git a/logo.png b/logo.png\nBinary files a/logo.png and b/logo.png differ\n"
    diff = text + binary
    block, status, files, included, total = pr_verifier._build_code_block(diff, len(diff))
    assert len(block) <= len(diff)
    assert text.strip() in block
    assert "1 changed file(s) omitted entirely" in block
    assert status == "truncated"
    assert [item.status for item in files] == ["complete", "omitted"]
    assert included == len(text)
    assert total == len(diff)


def test_truncated_line_separator_is_charged_to_excerpt_budget() -> None:
    text = _text_diff("src/app.py", "x" * 1000)
    note = "[... remaining lines of src/app.py omitted: verifier prompt budget ...]\n"
    budget = len(note) + text.index("\n@@") + 6
    block, coverage = pr_verifier._excerpt_file("src/app.py", text, budget)
    assert len(block) <= budget
    assert coverage.status == "truncated"


def test_complete_text_diff_uses_entire_budget() -> None:
    diff = _text_diff("src/app.py")
    block, status, files, included, total = pr_verifier._build_code_block(diff, len(diff))
    assert block == diff.rstrip("\n")
    assert status == "complete"
    assert files[0].status == "complete"
    assert included == total == len(diff)


def test_short_path_binary_note_does_not_displace_fitting_text() -> None:
    text = _text_diff("x", "b")
    binary = "diff --git a/y b/y\nBinary files a/y and b/y differ\n"
    diff = text + binary
    block, status, files, included, total = pr_verifier._build_code_block(diff, len(diff))
    assert text.strip() in block
    assert len(block) <= len(diff)
    assert [item.status for item in files] == ["complete", "omitted"]
    assert status == "truncated"
    assert included == len(text)
    assert total == len(diff)
