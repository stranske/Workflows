"""Lock the recovered #3998 contract into the issue #4426 evidence record.

The record must keep the original baseline, ranking method, 90% coverage
exception, exclusion rule, and about-180 numerical threshold. Quotes are
checked against the retrieved issue body and the format document the sync
manifest actually resolves.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.sync_manifest_compiler import compile_manifest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
RECORD_PATH = EVIDENCE / "contract-3998.json"
BODY_PATH = EVIDENCE / "issue-3998.body.md"
README_PATH = EVIDENCE / "README.md"
CITED_FORMAT_PATH = "docs/AGENT_ISSUE_FORMAT.md"


def _record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def _verbatim_quotes(node: object) -> list[str]:
    quotes: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "binding_quotes" and isinstance(value, list):
                quotes.extend(value)
            elif key.endswith("verbatim") and isinstance(value, str):
                quotes.append(value)
            else:
                quotes.extend(_verbatim_quotes(value))
    elif isinstance(node, list):
        for item in node:
            quotes.extend(_verbatim_quotes(item))
    return quotes


def test_format_document_resolution_matches_sync_manifest() -> None:
    record = _record()
    format_document = record["format_document"]
    compiled = compile_manifest(ROOT / ".github/sync-manifest.yml", repo_root=ROOT)
    entry = next(item for item in compiled.section("docs") if item.target == CITED_FORMAT_PATH)

    assert format_document["cited_path"] == CITED_FORMAT_PATH
    assert entry.source == CITED_FORMAT_PATH
    assert entry.source_tree == "template"
    assert entry.resolved_source == format_document["resolved_path"]
    resolved = ROOT / entry.resolved_source
    assert resolved.is_file()
    assert not (ROOT / CITED_FORMAT_PATH).exists()
    assert format_document["root_path_present"] is False
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    assert format_document["sha256"] == digest
    assert entry.content_sha256 == f"sha256:{digest}"
    text = resolved.read_text(encoding="utf-8")
    for quote in format_document["binding_quotes"]:
        assert quote in text


def test_contract_record_preserves_issue_3998_verbatim() -> None:
    record = _record()
    body = BODY_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    issue = record["issue"]

    assert issue["number"] == 3998
    assert issue["state"] == "CLOSED"
    assert issue["url"] == "https://github.com/stranske/Workflows/issues/3998"
    assert hashlib.sha256(body.encode()).hexdigest() == issue["body_sha256"]
    assert "gh issue view 3998 --repo stranske/Workflows" in record["retrieval_command"]

    format_text = (ROOT / record["format_document"]["resolved_path"]).read_text(encoding="utf-8")
    for quote in _verbatim_quotes(record):
        assert quote in readme
        assert quote in body or quote in format_text

    assert record["baseline_definition"]["opening_blended_line_branch_percent"] == 82.29
    assert record["baseline_definition"]["statements_plus_branches_to_reach_90_percent"] == 4488
    assert record["ranking_method"]["sort_keys"] == [
        "escaped_defect_signals",
        "churn",
        "uncovered_statements_and_branches",
    ]
    assert record["ranking_method"]["not_by"] == "file size"
    assert record["coverage_exception"]["threshold_percent"] == 90
    assert record["numerical_rule"]["about_units"] == 180
    assert record["numerical_rule"]["unit"] == "uncovered statements+branches"
    assert "about 180" in record["numerical_rule"]["scope_verbatim"]
    assert "about 180 or more" in record["numerical_rule"]["acceptance_verbatim"]
    assert "does not replace" in record["numerical_rule"]["replacement_forbidden"]


def test_ranked_targets_and_exclusions_follow_the_issue_body() -> None:
    record = _record()
    body = BODY_PATH.read_text(encoding="utf-8")
    targets = record["ranking_method"]["targets"]
    expected = [
        ("scripts/sync_test_dependencies.py", 6, 15, 16),
        ("scripts/langchain/issue_pr_context.py", 30, 7, 9),
        ("scripts/langchain/verifier_config.py", 16, 6, 8),
        ("tools/langchain_client.py", 29, 6, 7),
        ("scripts/langchain/task_validator.py", 36, 5, 8),
        ("scripts/langchain/pr_verifier.py", 281, 4, 8),
    ]

    assert [item["rank"] for item in targets] == [1, 2, 3, 4, 5, 6]
    assert record["ranking_method"]["listed_uncovered_statements_and_branches"] == 398
    assert sum(item["uncovered_statements_and_branches"] for item in targets) == 398
    for target, (path, uncovered, signals, churn) in zip(targets, expected, strict=True):
        assert target["path"] == path
        assert target["uncovered_statements_and_branches"] == uncovered
        assert target["escaped_defect_signals"] == signals
        assert target["churn"] == churn
        assert f"`{path}`" in body

    exclusions = record["exclusion_requirements"]
    assert exclusions["allowed_skip_reasons"] == [
        "dead code",
        "an external service you cannot fake",
    ]
    assert "terminal local receipt" in exclusions["disallowed_skip_reason"]
    assert exclusions["reserved_files"] == [
        "scripts/aggregate_agent_metrics.py",
        "scripts/check_consumer_sync_drift.py",
        "scripts/langchain/followup_issue_generator.py",
        "scripts/runner_lib/core.py",
    ]
    for path in exclusions["reserved_files"]:
        assert path in body
    for forbidden in exclusions["forbids"]:
        assert forbidden in README_PATH.read_text(encoding="utf-8")
