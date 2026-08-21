from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_docs_drift import (  # noqa: E402
    check_dangling_references,
    check_docs_drift,
    check_workflow_inventory,
    main,
)


def _load_consumer_checker():
    consumer_path = ROOT / "templates/consumer-repo/scripts/check_docs_drift.py"
    spec = importlib.util.spec_from_file_location("consumer_check_docs_drift", consumer_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CONSUMER_CHECKER = _load_consumer_checker()


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(
    root: Path,
    *,
    workflows: Iterable[str] = (),
    workflows_doc: str = "",
    extra_files: Iterable[str] = (),
) -> Path:
    _write(root / "docs/ci/WORKFLOWS.md", workflows_doc)
    for workflow in workflows:
        _write(root / ".github/workflows" / workflow, "name: test\n")
    for extra_file in extra_files:
        _write(root / extra_file, "")
    return root


def test_clean_tree_reports_zero_drift_and_cli_exit_zero(tmp_path: Path, capsys) -> None:
    root = _repo(
        tmp_path,
        workflows=("alpha.yml", "beta.yaml"),
        workflows_doc="""
Active workflows include `alpha.yml` and
[Beta](../../.github/workflows/beta.yaml).

Existing repo paths: `scripts/existing.py`, `tests/test_existing.py`,
`docs/ci/WORKFLOWS.md`.

Ignored non-path tokens: `alpha`, `scripts/no extension`, `scripts/*.py`.
""",
        extra_files=("scripts/existing.py", "tests/test_existing.py"),
    )

    assert check_workflow_inventory(root) == []
    assert check_dangling_references(root) == []
    assert check_docs_drift(root) == []

    exit_code = main(["--repo-root", str(root), "--json"])

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {"summary": {"drift": 0, "by_type": {}}, "drift": []}


def test_workflow_on_disk_absent_from_docs_is_undocumented(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("extra.yml",),
        workflows_doc="This doc intentionally names no workflow files.\n",
    )

    drift = check_workflow_inventory(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("undocumented_workflow", "extra.yml")
    ]


def test_workflow_mentioned_in_docs_but_missing_on_disk(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows_doc="The retired `missing.yml` workflow is still listed.\n",
    )

    drift = check_docs_drift(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("documented_but_missing", "missing.yml")
    ]


def test_dotted_and_slash_workflow_refs_count_but_template_refs_do_not(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        workflows=("release.pipeline.v2.yml", "health-72-template-sync.yml"),
        workflows_doc="""
Root workflow link: [Release](../../.github/workflows/release.pipeline.v2.yml).
Root inline workflow: `health-72-template-sync.yml`.
Consumer-template examples use `agents-80-pr-event-hub.yml` and
[Template](../../templates/consumer-repo/.github/workflows/template-only.yml).
Opt-in consumer `cross-repo-smoke.yml` callers are not Workflows inventory.
Config names such as sync-manifest.yml and labels-core.yml are not workflows.
""",
    )

    drift = check_workflow_inventory(root)

    assert drift == []


def test_bare_root_workflow_ref_counts_in_root_context(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("health-72-template-sync.yml",),
        workflows_doc="""
The `health-72-template-sync.yml` workflow validates synchronization.
""",
    )

    drift = check_workflow_inventory(root)

    assert drift == []


def test_bare_root_filename_in_consumer_template_context_does_not_count(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        workflows=("health-72-template-sync.yml",),
        workflows_doc="""
The consumer-template workflow `health-72-template-sync.yml` is copied to consumers.
""",
    )

    drift = check_workflow_inventory(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("undocumented_workflow", "health-72-template-sync.yml")
    ]


def test_missing_workflow_inventory_doc_is_not_applicable_in_consumer(tmp_path: Path) -> None:
    root = tmp_path
    _write(root / ".github/workflows/build.yml", "name: Build\n")

    drift = check_workflow_inventory(root)

    assert drift == []


def test_explicit_same_line_workflows_reference_is_not_a_consumer_dangling_path(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, workflows=(), workflows_doc="")
    _write(
        root / "AGENTS.md",
        "Read `docs/missing.md` from stranske/Workflows before editing.\n"
        "A local `docs/missing.md` reference remains checked.\n",
    )

    drift = check_dangling_references(root, ["AGENTS.md"])

    assert [(record["type"], record["path"]) for record in drift] == [
        ("dangling_reference", "docs/missing.md")
    ]


def test_workflows_qualified_agents_section_skips_unqualified_upstream_paths(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, workflows=(), workflows_doc="")
    _write(
        root / "AGENTS.md",
        """## Source Of Truth

Most workflow logic lives in `stranske/Workflows`.

1. `stranske/Workflows` root docs: `README.md`, `docs/WORKFLOW_GUIDE.md`
2. `stranske/Workflows/docs/INTEGRATION_GUIDE.md` and
   `docs/ops/CONSUMER_REPO_MAINTENANCE.md`

## Local Notes

`docs/missing.md` is a local reference.
""",
    )

    drift = check_dangling_references(root, ["AGENTS.md"])

    assert [(record["type"], record["path"]) for record in drift] == [
        ("dangling_reference", "docs/missing.md")
    ]


@pytest.mark.parametrize(
    "checker",
    [
        check_dangling_references,
        CONSUMER_CHECKER.check_dangling_references,
    ],
    ids=["workflows-root", "consumer-template"],
)
def test_source_of_truth_checker_implementations_share_upstream_behavior(
    tmp_path: Path, checker
) -> None:
    root = _repo(tmp_path, workflows=(), workflows_doc="")
    _write(
        root / "AGENTS.md",
        """## Source Of Truth

1. `stranske/Workflows` root docs: `README.md`, `docs/WORKFLOW_GUIDE.md`
2. `stranske/Workflows/docs/INTEGRATION_GUIDE.md` and
   `docs/ops/CONSUMER_REPO_MAINTENANCE.md`
3. The consumer sync source in `stranske/Workflows/templates/consumer-repo/`
4. Local runbook: `docs/local-runbook.md`
""",
    )

    drift = checker(root, ["AGENTS.md"])

    assert [(record["type"], record["path"]) for record in drift] == [
        ("dangling_reference", "docs/local-runbook.md")
    ]


def test_mixed_source_of_truth_section_keeps_local_paths_checked(tmp_path: Path) -> None:
    root = _repo(tmp_path, workflows=(), workflows_doc="")
    _write(
        root / "AGENTS.md",
        """## Source Of Truth

For infrastructure work, follow this order:

1. `stranske/Workflows` root docs: `README.md`, `docs/WORKFLOW_GUIDE.md`, `docs/ci/WORKFLOWS.md`
2. `stranske/Workflows/docs/INTEGRATION_GUIDE.md` and `docs/ops/CONSUMER_REPO_MAINTENANCE.md`
3. The consumer sync source in `stranske/Workflows/templates/consumer-repo/`
4. This repo's local repo-specific files: `docs/local-runbook.md`
""",
    )

    drift = check_dangling_references(root, ["AGENTS.md"])

    assert [(record["type"], record["path"]) for record in drift] == [
        ("dangling_reference", "docs/local-runbook.md")
    ]


def test_cli_skips_missing_default_workflow_inventory_in_consumer(tmp_path: Path, capsys) -> None:
    root = tmp_path
    _write(root / ".github/workflows/build.yml", "name: Build\n")
    _write(root / "AGENTS.md", "Consumer guidance.\n")

    exit_code = main(["--repo-root", str(root), "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["drift"] == []


def test_cli_only_limits_exit_status_to_selected_batch(tmp_path: Path, capsys) -> None:
    root = _repo(
        tmp_path,
        workflows=("build.yml", "later.yml"),
        workflows_doc="Active workflows: `build.yml`. Missing `scripts/target.py`.\n",
    )

    exit_code = main(["--repo-root", str(root), "--json", "--only", "scripts/target.py"])

    assert exit_code == 1
    report = json.loads(capsys.readouterr().out)
    assert [record["path"] for record in report["drift"]] == ["scripts/target.py"]


def test_missing_backtick_repo_path_is_dangling_reference(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("build.yml",),
        workflows_doc="`build.yml` cites `scripts/does_not_exist.py`.\n",
    )

    drift = check_docs_drift(root)

    assert len(drift) == 1
    assert drift[0]["type"] == "dangling_reference"
    assert drift[0]["path"] == "scripts/does_not_exist.py"
    assert "docs/ci/WORKFLOWS.md" in drift[0]["detail"]


def test_consumer_workflow_destination_path_is_not_dangling_reference(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("build.yml",),
        workflows_doc=(
            "Install the consumer workflow at `.github/workflows/ci.yml`, "
            "using the template source `templates/consumer-repo/.github/workflows/ci.yml`.\n"
            "The Workflows inventory still lists `build.yml`.\n"
        ),
    )

    assert check_dangling_references(root) == []
    assert check_docs_drift(root) == []


def test_consumer_context_does_not_suppress_known_root_workflow_mention(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        workflows=("health-68-consumer-sync-drift.yml",),
        workflows_doc=(
            "Consumer sync drift is covered by "
            "[Health 68 Consumer Sync Drift](../../.github/workflows/"
            "health-68-consumer-sync-drift.yml).\n"
        ),
    )

    assert check_workflow_inventory(root) == []


def test_repo_path_glob_tokens_are_ignored(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("build.yml",),
        workflows_doc="""
`build.yml` cites glob-style paths `scripts/*.py`, `scripts/file?.py`,
`scripts/[abc].py`, `docs/{old,new}.md`, and `tests/!excluded.py`.
It also cites a real missing file: `scripts/does_not_exist.py`.
""",
    )

    drift = check_dangling_references(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("dangling_reference", "scripts/does_not_exist.py")
    ]


@pytest.mark.parametrize(
    "checker",
    [
        check_dangling_references,
        CONSUMER_CHECKER.check_dangling_references,
    ],
    ids=["workflows-root", "consumer-template"],
)
def test_gitignored_generated_doc_output_is_not_dangling(tmp_path: Path, checker) -> None:
    root = _repo(tmp_path, workflows_doc="")
    _write(root / ".gitignore", "docs/_build/\n")
    _write(
        root / "README.md",
        "Run `make docs`, then open `docs/_build/html/index.html`.\n",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)

    assert checker(root, ["README.md"]) == []


def test_dangling_reference_ties_preserve_scan_order(tmp_path: Path) -> None:
    root = _repo(tmp_path, workflows_doc="")
    _write(root / "docs/a.md", "`scripts/missing.py`\n")
    _write(root / "docs/b.md", "`scripts/missing.py`\n")

    drift = check_dangling_references(root, ["docs/b.md", "docs/a.md"])

    assert [record["detail"] for record in drift] == [
        "Referenced in docs/b.md",
        "Referenced in docs/a.md",
    ]


def test_template_workflow_is_not_part_of_runtime_inventory(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows_doc="Template workflows are not runtime workflow inventory.\n",
    )
    _write(
        root / "templates/consumer-repo/.github/workflows/template-only.yml",
        "name: Template only\n",
    )

    drift = check_workflow_inventory(root)

    assert drift == []


def test_cli_report_write_io_error_returns_two(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path / "repo", workflows=("build.yml",), workflows_doc="`build.yml`\n")
    report_dir = tmp_path / "report-dir"
    report_dir.mkdir()

    exit_code = main(["--repo-root", str(root), "--report", str(report_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "error:" in captured.err


def test_cli_json_orders_mixed_drift_records(tmp_path: Path, capsys) -> None:
    root = _repo(
        tmp_path / "repo",
        workflows=("zeta.yml", "alpha.yml"),
        workflows_doc="""
Retired workflow: `beta.yml`.
Path drift: `scripts/missing.py`.
""",
    )
    report_path = tmp_path / "drift.json"

    exit_code = main(
        [
            "--repo-root",
            str(root),
            "--json",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(capsys.readouterr().out)
    assert [(record["type"], record["path"]) for record in report["drift"]] == [
        ("dangling_reference", "scripts/missing.py"),
        ("documented_but_missing", "beta.yml"),
        ("undocumented_workflow", "alpha.yml"),
        ("undocumented_workflow", "zeta.yml"),
    ]
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
