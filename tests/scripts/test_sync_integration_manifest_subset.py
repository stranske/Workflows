from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from scripts import sync_integration_manifest_subset as subset

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "sync-manifest.yml"
SYNC_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "maint-69-sync-integration-repo.yml"
HUB = REPO_ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
WIT = subset.DEFAULT_REPO


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def _entry(source: str, **extra: object) -> dict:
    return {"source": source, "description": "x", **extra}


def test_selects_only_script_files_and_the_coverage_guard() -> None:
    manifest = {
        "scripts": [
            _entry(".github/scripts/a.js"),
            _entry(".github/scripts/b.py"),
            _entry(".github/scripts/package.json"),
            _entry(".github/scripts/node_modules/x/index.js"),
            _entry(".github/scripts/dir", is_directory=True),
            _entry("scripts/not_under_github.py"),
        ],
        "workflows": [
            _entry(".github/workflows/maint-coverage-guard.yml"),
            _entry(".github/workflows/agents-80-pr-event-hub.yml"),
        ],
    }

    assert subset.select_copy_sources(manifest) == [
        ".github/scripts/a.js",
        ".github/scripts/b.py",
        ".github/scripts/package.json",
        ".github/workflows/maint-coverage-guard.yml",
    ]


def test_selection_honours_repo_scoping_and_delivery_mode() -> None:
    manifest = {
        "scripts": [
            _entry(".github/scripts/skipped.js", skip_repos=[WIT]),
            _entry(".github/scripts/mapped.js", skip_repos=[{"repo": WIT, "reason": "custom"}]),
            _entry(".github/scripts/elsewhere.js", include_repos=["stranske/Other"]),
            _entry(".github/scripts/here.js", include_repos=[WIT]),
            _entry(".github/scripts/seed.js", delivery="create_only"),
            _entry(".github/scripts/dup.js"),
            _entry(".github/scripts/dup.js"),
        ]
    }

    assert subset.select_copy_sources(manifest, WIT) == [
        ".github/scripts/here.js",
        ".github/scripts/dup.js",
    ]


def test_unsafe_manifest_paths_are_ignored() -> None:
    manifest = {
        "scripts": [_entry(".github/scripts/../../evil.js"), _entry("/abs/.github/scripts/a.js")],
        "removals": [
            {"target": ".github/workflows/../../evil.yml"},
            {"target": ".github/workflows/old.yml"},
            {"target": ".workflows-lib"},
            {"target": "scripts/other.py"},
        ],
    }

    assert subset.select_copy_sources(manifest) == []
    assert subset.select_removals(manifest) == [".github/workflows/old.yml"]


def test_apply_copies_updates_and_removes(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / ".github/scripts").mkdir(parents=True)
    (dst / ".github/scripts").mkdir(parents=True)
    (dst / ".github/workflows").mkdir(parents=True)
    (src / ".github/scripts/new.js").write_text("new\n")
    (src / ".github/scripts/stale.js").write_text("fresh\n")
    (src / ".github/scripts/same.js").write_text("same\n")
    (dst / ".github/scripts/stale.js").write_text("old\n")
    (dst / ".github/scripts/same.js").write_text("same\n")
    (dst / ".github/workflows/agents-autofix-loop.yml").write_text("retired\n")
    manifest = {
        "scripts": [_entry(f".github/scripts/{n}.js") for n in ("new", "stale", "same", "gone")],
        "removals": [
            {"target": ".github/workflows/agents-autofix-loop.yml"},
            {"target": ".github/workflows/agents-keepalive-loop.yml"},
        ],
    }

    result = subset.apply_subset(manifest, src, dst)

    assert result.copied == [".github/scripts/new.js", ".github/scripts/stale.js"]
    assert result.unchanged == [".github/scripts/same.js"]
    assert result.missing_sources == [".github/scripts/gone.js"]
    assert result.removed == [".github/workflows/agents-autofix-loop.yml"]
    assert result.absent == [".github/workflows/agents-keepalive-loop.yml"]
    assert result.ok is False
    assert (dst / ".github/scripts/new.js").read_text() == "new\n"
    assert (dst / ".github/scripts/stale.js").read_text() == "fresh\n"
    assert not (dst / ".github/workflows/agents-autofix-loop.yml").exists()


def test_dry_run_reports_without_touching_the_target(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / ".github/scripts").mkdir(parents=True)
    (dst / ".github/workflows").mkdir(parents=True)
    (src / ".github/scripts/new.js").write_text("new\n")
    (dst / ".github/workflows/old.yml").write_text("retired\n")
    manifest = {
        "scripts": [_entry(".github/scripts/new.js")],
        "removals": [{"target": ".github/workflows/old.yml"}],
    }

    result = subset.apply_subset(manifest, src, dst, dry_run=True)

    assert result.copied == [".github/scripts/new.js"]
    assert result.removed == [".github/workflows/old.yml"]
    assert not (dst / ".github/scripts/new.js").exists()
    assert (dst / ".github/workflows/old.yml").exists()


def test_second_run_is_drained_and_says_so(tmp_path: Path) -> None:
    """The zero case: a fully drained run must print the drained line, not stay silent."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / ".github/scripts").mkdir(parents=True)
    dst.mkdir()
    (src / ".github/scripts/a.js").write_text("a\n")
    manifest = {"scripts": [_entry(".github/scripts/a.js")]}

    first = subset.apply_subset(manifest, src, dst)
    second = subset.apply_subset(manifest, src, dst)

    assert "fully drained" not in subset.render_summary(first)
    summary = subset.render_summary(second)
    assert second.copied == [] and second.removed == [] and second.ok
    assert "copied=0 unchanged=1 removed=0" in summary
    assert "fully drained" in summary


def test_missing_source_is_a_failure_exit(tmp_path: Path) -> None:
    manifest_file = tmp_path / "m.yml"
    manifest_file.write_text(yaml.safe_dump({"scripts": [_entry(".github/scripts/nope.js")]}))
    (tmp_path / "dst").mkdir()

    code = subset.main(
        [
            "--manifest", str(manifest_file),
            "--source-root", str(tmp_path),
            "--target-root", str(tmp_path / "dst"),
        ]
    )  # fmt: skip

    assert code == 1


def test_real_manifest_sources_all_exist(manifest: dict) -> None:
    sources = subset.select_copy_sources(manifest)

    assert sources, "the real manifest must select hub scripts"
    assert [
        s
        for s, tree in subset._select_copy_entries(manifest, WIT)
        if not (REPO_ROOT / ("templates/consumer-repo" if tree == "template" else "") / s).is_file()
    ] == []


@pytest.mark.parametrize("section", ["scripts", "workflows"])
@pytest.mark.parametrize("source_tree", [None, "root", "template"])
def test_apply_honours_source_tree(tmp_path: Path, section: str, source_tree: str | None) -> None:
    source = (
        ".github/scripts/a.js"
        if section == "scripts"
        else ".github/workflows/maint-coverage-guard.yml"
    )
    src, dst = tmp_path / "src", tmp_path / "dst"
    for prefix, content in [("", "root"), ("templates/consumer-repo", "template")]:
        path = src / prefix / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    entry = _entry(source, **({"source_tree": source_tree} if source_tree else {}))

    result = subset.apply_subset({section: [entry]}, src, dst)

    expected = source_tree or ("root" if section == "scripts" else "template")
    assert result.ok
    assert (dst / source).read_text() == expected


def test_template_source_never_falls_back_to_root(tmp_path: Path) -> None:
    source = ".github/workflows/maint-coverage-guard.yml"
    path = tmp_path / "src" / source
    path.parent.mkdir(parents=True)
    path.write_text("wrong root workflow")
    result = subset.apply_subset(
        {"workflows": [_entry(source)]}, tmp_path / "src", tmp_path / "dst"
    )
    assert result.missing_sources == [source]
    assert not (tmp_path / "dst" / source).exists()


def test_real_manifest_delivers_loadable_keepalive_graph(manifest: dict, tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node, "Node is required to validate the delivered runtime dependency graph"
    result = subset.apply_subset(manifest, REPO_ROOT, tmp_path)
    assert result.ok
    assert (tmp_path / ".github/scripts/rate_limit_receipt.json").is_file()
    subprocess.run(
        [node, "-e", "require('./.github/scripts/keepalive_loop.js')"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    guard = ".github/workflows/maint-coverage-guard.yml"
    assert (tmp_path / guard).read_bytes() == (
        REPO_ROOT / "templates/consumer-repo" / guard
    ).read_bytes()


def test_real_manifest_delivers_every_script_the_gate_hub_requires(manifest: dict) -> None:
    """The failing WIT run needed runtime_ac_merge_guard.js; every hub dependency must ship."""
    delivered = set(subset.select_copy_sources(manifest))
    hub_text = HUB.read_text(encoding="utf-8")
    needed = set(re.findall(r"\.github/scripts/[A-Za-z0-9_.-]+\.(?:js|py)", hub_text))

    assert ".github/scripts/runtime_ac_merge_guard.js" in needed
    assert sorted(needed - delivered) == []


def test_real_manifest_removes_the_retired_autofix_loop(manifest: dict) -> None:
    assert ".github/workflows/agents-autofix-loop.yml" in subset.select_removals(manifest)


def test_maint_69_runs_the_helper_and_sees_untracked_files() -> None:
    workflow = yaml.safe_load(SYNC_WORKFLOW.read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["sync"]["steps"]}
    apply_script = steps["Apply template updates"]["run"]
    changes_script = steps["Check for changes"]["run"]
    commit_script = steps["Commit and push changes"]["run"]
    sparse = steps["Checkout Workflows repo"]["with"]["sparse-checkout"]

    assert "sync_integration_manifest_subset.py" in apply_script
    assert "git status --porcelain" in changes_script
    assert "git diff --quiet" not in changes_script
    assert ".github/scripts/" in commit_script
    for needed in (
        ".github/sync-manifest.yml",
        ".github/scripts",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
        "scripts/sync_integration_manifest_subset.py",
    ):
        assert needed in sparse
    assert "schedule" in workflow[True]  # PyYAML parses the bare `on:` key as boolean True


def test_maint_69_checkout_excludes_the_scripts_package_manifest() -> None:
    """A synced .github/scripts/package.json made `Setup API client` run npm against a missing
    node_modules (file:node_modules/minimatch), failing every sync run after the push."""
    workflow = yaml.safe_load(SYNC_WORKFLOW.read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["sync"]["steps"]}
    patterns = steps["Checkout Workflows repo"]["with"]["sparse-checkout"].split()

    assert ".github/scripts" in patterns
    assert "!/.github/scripts/package.json" in patterns
    assert "!/.github/scripts/package-lock.json" in patterns
    # Exclusions only win when they come after the directory include.
    assert patterns.index("!/.github/scripts/package.json") > patterns.index(".github/scripts")
    assert steps["Setup API client"]["with"]["install_dir"] == "workflows/.github/scripts"
