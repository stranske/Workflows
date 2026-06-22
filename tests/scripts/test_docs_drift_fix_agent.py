from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import docs_drift_fix_agent as fix_agent  # noqa: E402
from scripts.repo_review_issue_quality import issue_body_is_agent_ready  # noqa: E402


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(root: Path, *, workflows: tuple[str, ...], workflows_doc: str) -> Path:
    _write(root / "docs/ci/WORKFLOWS.md", workflows_doc)
    for workflow in workflows:
        _write(root / ".github/workflows" / workflow, "name: test\n")
    return root


def test_findings_from_scan_json_filters_accurate_instances() -> None:
    payload = {
        "by_repo": [
            {
                "repo": "stranske/Workflows",
                "drift_instances": [
                    {
                        "doc_path": "README.md",
                        "claim": "Old command",
                        "authoritative_source": "scripts/new.py:1",
                        "classification": "stale",
                    },
                    {
                        "doc_path": "README.md",
                        "claim": "Verified",
                        "classification": "accurate-no-drift",
                    },
                ],
            }
        ]
    }

    findings = fix_agent.findings_from_scan_json(payload, repo="stranske/Workflows")

    assert len(findings) == 1
    assert findings[0].source == "semantic-scan"
    assert findings[0].classification == "stale"


def test_batch_findings_respects_max_per_batch() -> None:
    findings = [
        fix_agent.Finding(
            source="deterministic",
            kind="dangling_reference",
            doc_path=f"docs/{index}.md",
            target=f"scripts/missing_{index}.py",
            detail="missing",
        )
        for index in range(10)
    ]

    batches = fix_agent.batch_findings(findings, max_per_batch=8)

    assert [len(batch.findings) for batch in batches] == [8, 2]
    assert [batch.batch_id for batch in batches] == ["docs-drift-01", "docs-drift-02"]


def test_dedupe_prefers_deterministic_finding() -> None:
    semantic = fix_agent.Finding(
        source="semantic-scan",
        kind="dangling_reference",
        doc_path="docs/ci/WORKFLOWS.md",
        target="scripts/missing.py",
        detail="semantic",
    )
    deterministic = fix_agent.Finding(
        source="deterministic",
        kind="dangling_reference",
        doc_path="docs/ci/WORKFLOWS.md",
        target="scripts/missing.py",
        detail="deterministic",
    )

    assert fix_agent.dedupe_findings([semantic, deterministic]) == [deterministic]


def test_issue_body_is_agent_ready() -> None:
    batch = fix_agent.RepairBatch(
        batch_id="docs-drift-01",
        findings=(
            fix_agent.Finding(
                source="deterministic",
                kind="undocumented_workflow",
                doc_path="docs/ci/WORKFLOWS.md",
                target="new.yml",
                detail="Exists in .github/workflows/ but is not mentioned",
            ),
        ),
    )

    body = fix_agent.build_issue_body(batch)

    assert issue_body_is_agent_ready(body)
    assert "## Why" in body
    assert "python3 scripts/check_docs_drift.py --json" in body
    assert "## Informational Checks" in body
    assert "was reviewed for remaining non-batch findings" in body
    assert "python3 scripts/docs_drift_fix_agent.py --repo-root . --json" in body


def test_repair_prompt_includes_required_verification() -> None:
    batch = fix_agent.RepairBatch(
        batch_id="docs-drift-01",
        findings=(
            fix_agent.Finding(
                source="deterministic",
                kind="documented_but_missing",
                doc_path="docs/ci/WORKFLOWS.md",
                target="old.yml",
                detail="missing from .github/workflows",
            ),
        ),
    )

    prompt = fix_agent.build_repair_prompt(batch)

    assert "open one focused docs-only fix PR" in prompt
    assert (
        "pytest tests/workflows/test_workflow_naming.py::test_inventory_docs_list_all_workflows -q"
        in prompt
    )
    assert "Informational full-plan refresh" in prompt
    assert "python3 scripts/docs_drift_fix_agent.py --repo-root . --json" in prompt
    assert "Do not change workflows" in prompt


def test_cli_clean_repo_exit_zero(tmp_path: Path, capsys) -> None:
    root = _repo(
        tmp_path / "repo",
        workflows=("build.yml",),
        workflows_doc="Active workflows: `build.yml`.\n",
    )

    exit_code = fix_agent.main(["--repo-root", str(root), "--docs", "docs/ci/WORKFLOWS.md"])

    assert exit_code == 0
    assert "0 finding(s)" in capsys.readouterr().out


def test_cli_drift_fixture_exit_one_and_writes_outputs(tmp_path: Path, capsys) -> None:
    root = _repo(
        tmp_path / "repo",
        workflows=("build.yml", "new.yml"),
        workflows_doc="Active workflows: `build.yml`.\nMissing path: `scripts/missing.py`.\n",
    )
    out_dir = tmp_path / "out"

    exit_code = fix_agent.main(
        [
            "--repo-root",
            str(root),
            "--docs",
            "docs/ci/WORKFLOWS.md",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 1
    stdout = capsys.readouterr().out
    assert "2 finding(s)" in stdout
    plan = json.loads((out_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["finding_count"] == 2
    assert (out_dir / "docs-drift-01-repair-prompt.md").is_file()
    assert (out_dir / "docs-drift-01-issue-body.md").is_file()
    assert (out_dir / "docs-drift-01-pr-plan.md").is_file()


def test_cli_apply_creates_one_issue_per_batch(tmp_path: Path, monkeypatch, capsys) -> None:
    root = _repo(
        tmp_path / "repo",
        workflows=("a.yml", "b.yml"),
        workflows_doc="No workflows listed.\n",
    )
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "https://github.com/stranske/Workflows/issues/1\n"
        stderr = ""

    def fake_run(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        return Result()

    monkeypatch.setattr(fix_agent.subprocess, "run", fake_run)

    exit_code = fix_agent.main(
        [
            "--repo-root",
            str(root),
            "--docs",
            "docs/ci/WORKFLOWS.md",
            "--max-per-batch",
            "1",
            "--apply",
        ]
    )

    assert exit_code == 1
    capsys.readouterr()
    issue_calls = [call for call in calls if call[:3] == ["gh", "issue", "create"]]
    assert len(issue_calls) == 2
