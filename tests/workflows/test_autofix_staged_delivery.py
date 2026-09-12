"""Run the reusable workflow's delivery shell against real Git repositories."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/reusable-18-autofix.yml"
VENDOR_PATHS = (
    "node_modules/pkg/index.js",
    "packages/frontend/node_modules/pkg/index.js",
    "packages/space name/node_modules/[pkg]/index.js",
    "workflows-lib/.github/scripts/node_modules/pkg/index.js",
    "workflows-lib/helper.py",
    ".github/scripts/node_modules/pkg/index.js",
    ".workflows-lib/.github/scripts/node_modules/pkg/index.js",
)


def git(repo: Path, *args: str) -> str:
    """Run a Git command in the isolated consumer fixture."""
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def step(name: str) -> str:
    """Read the actual workflow shell instead of duplicating its logic."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return next(
        item["run"]
        for job in workflow["jobs"].values()
        for item in job.get("steps", [])
        if item.get("name") == name
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Create a committed source tree with tracked installation churn."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    for name in (*VENDOR_PATHS, "src/example.py"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "baseline")
    return repo


def run_step(
    repo: Path, name: str, *, clean: bool = False, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Execute a complete Actions run body with the runner's fail-fast flags."""
    env = {
        **os.environ,
        "MODE_ENABLED": str(clean).lower(),
        "TRIGGER_CONCLUSION": "",
        "TRIGGER_CLASS": "",
        "TRIGGER_REASON": "",
        "TRIGGER_HEAD": "",
        "AUTO_CHANGED": "true",
        "CLEAN_CHANGED": "true",
        "AUTO_FILE_LIST": "stale-vendor-list",
        "CLEAN_FILE_LIST": "stale-vendor-list",
        "AUTOFIX_COMMIT_PREFIX": "chore(autofix):",
        "GITHUB_OUTPUT": str(repo.parent / "outputs"),
        "GITHUB_ENV": str(repo.parent / "env"),
    }
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step(name)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize("vendor", VENDOR_PATHS)
@pytest.mark.parametrize("clean", [False, True])
def test_vendor_only_churn_is_not_deliverable(repository: Path, vendor: str, clean: bool) -> None:
    """Dependency-only changes never publish deliverable work in either mode."""
    before = git(repository, "rev-parse", "HEAD")
    (repository / vendor).write_text("installed dependency\n")
    result = run_step(repository, "Consolidate fix mode outputs", clean=clean)
    assert result.returncode == 0, result.stderr
    outputs = (repository.parent / "outputs").read_text()
    assert "changed=false\n" in outputs
    assert "file_list" not in outputs
    assert git(repository, "diff", "--cached", "--name-only") == ""
    assert git(repository, "rev-parse", "HEAD") == before
    assert (repository / vendor).read_text() == "installed dependency\n"


@pytest.mark.parametrize(
    "delivery", ["Commit changes (push path)", "Create patch artifact (fallback)"]
)
def test_source_fix_commits_without_vendor_churn(repository: Path, delivery: str) -> None:
    """A valid fix commits and produces a source-only fallback patch."""
    (repository / VENDOR_PATHS[0]).write_text("installed dependency\n")
    (repository / "src/example.py").write_text("fixed\n")
    result = run_step(repository, "Consolidate fix mode outputs")
    assert result.returncode == 0, result.stderr
    assert "changed=true\n" in (repository.parent / "outputs").read_text()
    result = run_step(repository, delivery)
    assert result.returncode == 0, result.stderr
    assert (
        git(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        == "src/example.py"
    )
    assert git(repository, "show", f"HEAD:{VENDOR_PATHS[0]}") == "original"
    if delivery == "Create patch artifact (fallback)":
        patch = (repository / "autofix.patch").read_text()
        assert "+fixed" in patch
        assert "node_modules" not in patch


@pytest.mark.parametrize(
    "delivery", ["Commit changes (push path)", "Create patch artifact (fallback)"]
)
def test_real_commit_failure_is_not_hidden(repository: Path, delivery: str) -> None:
    """A rejected commit neither changes HEAD nor invents a patch in finalization."""
    before = git(repository, "rev-parse", "HEAD")
    (repository / "src/example.py").write_text("fixed\n")
    assert run_step(repository, "Consolidate fix mode outputs").returncode == 0
    hook = repository / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = run_step(repository, delivery)
    assert result.returncode != 0
    assert git(repository, "rev-parse", "HEAD") == before
    assert not (repository / "autofix.patch").exists()

    result = run_step(repository, "Finalize outputs", extra_env={"CHANGED": "true"})
    assert result.returncode == 0, result.stderr
    assert "patch_available=false" in (repository.parent / "outputs").read_text()


def outputs(repository: Path) -> dict[str, str]:
    """Parse runner outputs, including multiline file lists."""
    lines = iter((repository.parent / "outputs").read_text().splitlines())
    values = {}
    for line in lines:
        if "<<" in line:
            key, delimiter = line.split("<<", 1)
            payload = []
            for value in lines:
                if value == delimiter:
                    break
                payload.append(value)
            values[key] = "\n".join(payload)
        else:
            key, value = line.split("=", 1)
            values[key] = value
    return values


@pytest.mark.parametrize("clean", [False, True])
def test_source_only_repository_has_no_reset_matches(repository: Path, clean: bool) -> None:
    """The vendor filter must not fail when no vendor path is tracked."""
    git(repository, "rm", "-r", "--", *VENDOR_PATHS)
    git(repository, "commit", "-qm", "source-only baseline")
    (repository / "src/example.py").write_text("fixed\n")
    result = run_step(repository, "Consolidate fix mode outputs", clean=clean)
    assert result.returncode == 0, result.stderr
    assert outputs(repository)["file_list"] == "src/example.py"
    assert outputs(repository)["changed"] == "true"


@pytest.mark.parametrize("clean", [False, True])
@pytest.mark.parametrize("source_changed", [False, True])
def test_enriched_report_matches_filtered_index(
    repository: Path, clean: bool, source_changed: bool
) -> None:
    """Both report schemas preserve classification while excluding vendor files."""
    for vendor in VENDOR_PATHS:
        (repository / vendor).write_text("installed dependency\n")
    if source_changed:
        (repository / "src/example.py").write_text("fixed\n")
    (repository / ".git/info/exclude").write_text("autofix_report*.json\n")
    enriched = repository / "autofix_report_enriched.json"
    enriched.write_text(
        json.dumps(
            {
                "changed": True,
                "files": list(VENDOR_PATHS),
                "file_list": list(VENDOR_PATHS),
                "classification": {"total": 2, "new": 1, "allowed": 1},
            }
        )
    )
    result = run_step(repository, "Consolidate fix mode outputs", clean=clean)
    assert result.returncode == 0, result.stderr
    expected = ["src/example.py"] if source_changed else []
    assert outputs(repository).get("file_list", "").splitlines() == expected
    result = run_step(
        repository,
        "Emit JSON report (same-repo)",
        extra_env={
            "WORKFLOWS_SCRIPTS_PATH": str(WORKFLOW.parents[2]),
            "REPORT_CHANGED": outputs(repository)["changed"],
            "REPORT_FILE_LIST": outputs(repository).get("file_list", ""),
        },
    )
    assert result.returncode == 0, result.stderr
    for path in [enriched, repository / "autofix_report.json"]:
        report = json.loads(path.read_text())
        assert report["changed"] is source_changed
        assert report["files"] == expected
        assert report["file_list"] == expected
        assert report["classification"] == {"total": 2, "new": 1, "allowed": 1}


@pytest.mark.parametrize("source_changed", [False, True])
@pytest.mark.parametrize("root_target", [False, True])
def test_whole_clean_sweep_filters_before_target_validation(
    repository: Path, source_changed: bool, root_target: bool
) -> None:
    """Install-only churn outside Python targets cannot abort the clean sweep."""
    bash_version = subprocess.check_output(["bash", "-c", "echo ${BASH_VERSINFO[0]}"], text=True)
    find_version = subprocess.run(["find", "--version"], capture_output=True, text=True)
    if int(bash_version) < 4 or "GNU findutils" not in find_version.stdout:
        pytest.skip("The Actions Ubuntu workflow requires Bash 4+ and GNU find")
    # Stub formatters only: the complete workflow body, Git, Bash and find are real.
    bin_dir = repository.parent / "bin"
    bin_dir.mkdir()
    for tool in ["ruff", "black"]:
        path = bin_dir / tool
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    if root_target:
        (repository / "root.py").write_text("original\n")
        git(repository, "add", "root.py")
        git(repository, "commit", "-qm", "root Python target")
    for vendor in VENDOR_PATHS:
        (repository / vendor).write_text("installed dependency\n")
    if source_changed:
        (repository / "src/example.py").write_text("fixed\n")
    result = run_step(
        repository,
        "Clean cosmetic sweep",
        extra_env={
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        },
    )
    assert result.returncode == 0, result.stderr
    clean_outputs = outputs(repository)
    assert clean_outputs["changed"] == str(source_changed).lower()
    assert clean_outputs.get("file_list", "") == ("src/example.py" if source_changed else "")
    result = run_step(
        repository,
        "Consolidate fix mode outputs",
        clean=True,
        extra_env={
            "CLEAN_CHANGED": clean_outputs["changed"],
            "CLEAN_FILE_LIST": clean_outputs.get("file_list", ""),
        },
    )
    assert result.returncode == 0, result.stderr
    assert git(repository, "diff", "--cached", "--name-only") == (
        "src/example.py" if source_changed else ""
    )


@pytest.mark.parametrize("upload_outcome", ["", "failure", "skipped", "success"])
def test_patch_availability_requires_successful_upload(
    repository: Path, upload_outcome: str
) -> None:
    """Neither changed work nor stale metadata proves a downloadable artifact exists."""
    result = run_step(
        repository,
        "Finalize outputs",
        extra_env={
            "CHANGED": "true",
            "AUTOFIX_PATCH_AVAILABLE": "true",
            "PATCH_UPLOAD_OUTCOME": upload_outcome,
        },
    )
    assert result.returncode == 0, result.stderr
    assert outputs(repository)["patch_available"] == str(upload_outcome == "success").lower()


def test_new_and_deleted_vendor_paths_are_unstaged(repository: Path) -> None:
    """NUL-delimited literal paths handle deleted and newly installed dependencies."""
    (repository / VENDOR_PATHS[0]).unlink()
    added = repository / "packages/new app/node_modules/[literal]/new.js"
    added.parent.mkdir(parents=True)
    added.write_text("new dependency\n")
    (repository / "src/example.py").write_text("fixed\n")
    result = run_step(repository, "Consolidate fix mode outputs")
    assert result.returncode == 0, result.stderr
    assert git(repository, "diff", "--cached", "--name-only") == "src/example.py"
    assert added.exists()
    assert not (repository / VENDOR_PATHS[0]).exists()


def test_nested_helper_checkout_is_not_committed(repository: Path) -> None:
    """The actual dual checkout can be a staged gitlink rather than ordinary files."""
    helper = repository / "workflows-lib"
    git(repository, "rm", "-r", "workflows-lib")
    git(repository, "commit", "-qm", "remove helper fixture")
    helper.mkdir()
    git(helper, "init", "-q")
    git(helper, "config", "user.name", "Test")
    git(helper, "config", "user.email", "test@example.com")
    (helper / "helper.py").write_text("helper\n")
    git(helper, "add", ".")
    git(helper, "commit", "-qm", "nested checkout")
    (repository / "src/example.py").write_text("fixed\n")
    result = run_step(repository, "Consolidate fix mode outputs")
    assert result.returncode == 0, result.stderr
    assert git(repository, "diff", "--cached", "--name-only") == "src/example.py"


@pytest.mark.parametrize("source_changed", [False, True])
def test_standard_summary_ignores_vendor_paths_before_validation(
    repository: Path, source_changed: bool
) -> None:
    """The full standard summary accepts vendor churn outside explicit source globs."""
    for vendor in VENDOR_PATHS:
        (repository / vendor).write_text("installed dependency\n")
    if source_changed:
        (repository / "src/example.py").write_text("fixed\n")
    result = run_step(
        repository,
        "Summarise safe sweep results",
        extra_env={
            "ALLOWED_FILE_GLOBS": "src/**",
        },
    )
    assert result.returncode == 0, result.stderr
    assert outputs(repository)["changed"] == str(source_changed).lower()
    report = json.loads((repository / "autofix_report_enriched.json").read_text())
    assert report["changed"] is source_changed
    assert report.get("files", []) == (["src/example.py"] if source_changed else [])


def test_standard_summary_still_rejects_out_of_scope_source(repository: Path) -> None:
    """Vendor filtering cannot permit a real source edit outside allowed globs."""
    (repository / "src/example.py").write_text("fixed\n")
    result = run_step(
        repository,
        "Summarise safe sweep results",
        extra_env={
            "ALLOWED_FILE_GLOBS": "tests/**",
        },
    )
    assert result.returncode != 0
    assert "outside allowed globs" in result.stderr
