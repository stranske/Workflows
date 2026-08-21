from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

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


def test_findings_from_scan_json_rejects_non_mapping_payload() -> None:
    with pytest.raises(ValueError, match="top-level mapping"):
        fix_agent.findings_from_scan_json([], repo="stranske/Workflows")  # type: ignore[arg-type]


def test_docs_arg_quotes_shell_sensitive_paths() -> None:
    docs = ["docs/plain.md", "docs/my guide.md", "docs/$(unsafe).md", "docs/a'b.md"]

    command = "python3 scripts/check_docs_drift.py" + fix_agent._docs_arg(docs)

    assert shlex.split(command) == ["python3", "scripts/check_docs_drift.py", "--docs", *docs]


def test_verification_commands_are_bounded_to_deterministic_batch_targets() -> None:
    findings = [
        fix_agent.Finding(
            source="deterministic",
            kind="dangling_reference",
            doc_path="AGENTS.md",
            target="docs/z path.md",
            detail="missing",
        ),
        fix_agent.Finding(
            source="deterministic",
            kind="dangling_reference",
            doc_path="AGENTS.md",
            target="docs/a.md",
            detail="missing",
        ),
    ]

    commands = fix_agent.verification_commands(["AGENTS.md"], findings)

    assert shlex.split(commands[0]) == [
        "python3",
        "scripts/check_docs_drift.py",
        "--json",
        "--docs",
        "AGENTS.md",
        "--only",
        "docs/a.md",
        "docs/z path.md",
    ]


def test_verification_commands_reject_semantic_only_batch() -> None:
    finding = fix_agent.Finding(
        source="semantic-scan",
        kind="stale_claim",
        doc_path="AGENTS.md",
        target="a claim",
        detail="stale",
    )

    with pytest.raises(ValueError, match="bounded semantic verifier"):
        fix_agent.verification_commands(["AGENTS.md"], [finding])


def test_verification_commands_reject_mixed_semantic_batch() -> None:
    findings = [
        fix_agent.Finding(
            source="deterministic",
            kind="dangling_reference",
            doc_path="AGENTS.md",
            target="scripts/missing.py",
            detail="missing",
        ),
        fix_agent.Finding(
            source="semantic-scan",
            kind="semantic_drift",
            doc_path="AGENTS.md",
            target="stale claim",
            detail="stale",
        ),
    ]

    with pytest.raises(ValueError, match="bounded semantic verifier"):
        fix_agent.verification_commands(["AGENTS.md"], findings)


def test_build_plan_propagates_selected_docs_to_every_batch_artifact(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root / "AGENTS.md", "Missing `scripts/missing.py`.\n")

    plan = fix_agent.build_plan(
        repo_root=root,
        repo="stranske/consumer",
        docs=["AGENTS.md"],
    )

    batch = plan["batches"][0]
    expected_check = (
        "python3 scripts/check_docs_drift.py --json --docs AGENTS.md --only scripts/missing.py"
    )
    expected_refresh = (
        "python3 scripts/docs_drift_fix_agent.py --repo-root . --json --docs AGENTS.md"
    )
    assert expected_check in batch["repair_prompt"]
    assert expected_check in batch["issue_body"]
    assert expected_check in batch["pr_plan"]
    assert expected_refresh in batch["repair_prompt"]
    assert expected_refresh in batch["issue_body"]
    assert expected_refresh in batch["pr_plan"]


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
    assert "python3 scripts/check_docs_drift.py --json --only new.yml" in body
    assert (
        "python3 -m py_compile scripts/check_docs_drift.py scripts/docs_drift_fix_agent.py" in body
    )
    assert "## Informational Checks" in body
    assert "was reviewed for remaining non-batch findings" in body
    assert "python3 scripts/docs_drift_fix_agent.py --repo-root . --json" in body
    assert "workflow-inventory verification" not in body


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
    assert "python3 scripts/check_docs_drift.py --json --only old.yml" in prompt
    assert (
        "python3 -m py_compile scripts/check_docs_drift.py scripts/docs_drift_fix_agent.py"
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
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        if list(args)[:3] == ["gh", "issue", "list"]:
            return Result("[]")
        return Result("https://github.com/stranske/Workflows/issues/1\n")

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

    assert exit_code == 0
    capsys.readouterr()
    issue_calls = [call for call in calls if call[:3] == ["gh", "issue", "create"]]
    assert len(issue_calls) == 2
    assert all(
        "<!-- docs-drift-fix-agent:" in call[call.index("--body") + 1] for call in issue_calls
    )


def test_apply_issues_reuses_matching_open_issue(monkeypatch) -> None:
    plan = {
        "repo": "stranske/Workflows",
        "batches": [
            {
                "batch_id": "docs-drift-01",
                "issue_title": "[Docs Drift] Repair docs-drift-01",
                "issue_body": "Repair the drift.\n",
            }
        ],
    }
    digest = fix_agent.hashlib.sha256(
        b"[Docs Drift] Repair docs-drift-01\0Repair the drift.\n"
    ).hexdigest()[:16]
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        return Result(
            json.dumps(
                [
                    {
                        "body": f"Repair the drift.\n\n<!-- docs-drift-fix-agent:{digest} -->\n",
                        "url": "https://github.com/stranske/Workflows/issues/1",
                    }
                ]
            )
        )

    monkeypatch.setattr(fix_agent.subprocess, "run", fake_run)

    result = fix_agent.apply_issues(plan)

    assert result[0]["disposition"] == "already-open"
    assert result[0]["stdout"].endswith("/issues/1")
    assert [call[:3] for call in calls] == [["gh", "issue", "list"]]
    assert "--search" in calls[0]
    assert calls[0][calls[0].index("--limit") + 1] == "1"
    assert "1000" not in calls[0]


def test_apply_issues_queries_exact_marker_instead_of_capped_inventory(monkeypatch) -> None:
    plan = {
        "repo": "stranske/Workflows",
        "batches": [
            {
                "batch_id": "docs-drift-01",
                "issue_title": "[Docs Drift] Repair docs-drift-01",
                "issue_body": "Repair item beyond the first thousand issues.\n",
            }
        ],
    }
    digest = fix_agent.hashlib.sha256(
        b"[Docs Drift] Repair docs-drift-01\0Repair item beyond the first thousand issues.\n"
    ).hexdigest()[:16]
    marker = f"<!-- docs-drift-fix-agent:{digest} -->"
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        assert list(args)[:3] == ["gh", "issue", "list"]
        search = list(args)[list(args).index("--search") + 1]
        assert marker in search
        return Result(
            json.dumps(
                [
                    {
                        "body": f"Older issue.\n\n{marker}\n",
                        "url": "https://github.com/stranske/Workflows/issues/1001",
                    }
                ]
            )
        )

    monkeypatch.setattr(fix_agent.subprocess, "run", fake_run)

    result = fix_agent.apply_issues(plan)

    assert result[0]["disposition"] == "already-open"
    assert result[0]["stdout"].endswith("/issues/1001")
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("- not-a-mapping\n", "top-level mapping"),
        ("repos: []\n", "'repos' must be a mapping"),
        ("repos:\n  stranske/Workflows: []\n", "entry for 'stranske/Workflows'"),
    ],
)
def test_default_docs_from_config_rejects_invalid_mapping_shapes(
    tmp_path: Path, content: str, message: str
) -> None:
    root = tmp_path / "repo"
    _write(root / fix_agent.DEFAULT_DOCS_CONFIG, content)

    with pytest.raises(ValueError, match=message):
        fix_agent.default_docs_from_config(root)
