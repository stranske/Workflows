from __future__ import annotations

import sys
from pathlib import Path

import pytest
from scripts import check_api_wrapper_guard as guard


def _patch_guard_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    workflows = root / ".github" / "workflows"
    scripts_gh = root / ".github" / "scripts"
    scripts = root / "scripts"
    for directory in (workflows, scripts_gh, scripts):
        directory.mkdir(parents=True, exist_ok=True)

    skip_guard = scripts / "check_api_wrapper_guard.py"
    skip_api = scripts / "api_client.py"
    skip_guard.write_text("# guard self-skip\n", encoding="utf-8")
    skip_api.write_text("# wrapped client\n", encoding="utf-8")

    monkeypatch.setattr(guard, "ROOT", root)
    monkeypatch.setattr(
        guard,
        "TARGET_DIRS",
        (workflows, scripts_gh, scripts),
    )
    monkeypatch.setattr(
        guard,
        "SKIP_FILES",
        {
            skip_guard,
            skip_api,
            scripts_gh / "github-api-with-retry.js",
            scripts_gh / "token_load_balancer.js",
        },
    )


@pytest.fixture
def guard_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _patch_guard_root(monkeypatch, root)
    return root


def test_scan_file_detects_direct_gh_api(guard_root: Path) -> None:
    path = guard_root / "scripts" / "bad.js"
    path.write_text('run("gh api repos/owner/repo");\n', encoding="utf-8")

    violations = guard._scan_file(path)

    assert violations == ["scripts/bad.js:1: direct gh api usage"]


def test_scan_file_detects_api_github_com(guard_root: Path) -> None:
    path = guard_root / "scripts" / "bad.js"
    path.write_text('fetch("https://api.github.com/repos/owner/repo");\n', encoding="utf-8")

    violations = guard._scan_file(path)

    assert violations == ["scripts/bad.js:1: direct api.github.com usage"]


def test_scan_file_reports_unwrapped_github_rest_call(guard_root: Path) -> None:
    path = guard_root / "scripts" / "bad.js"
    path.write_text(
        "\n".join(
            [
                "async function listIssues() {",
                "  await github.rest.issues.listForRepo({ owner, repo });",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = guard._scan_file(path)

    assert violations == ["scripts/bad.js:2: API call without createTokenAwareRetry"]


@pytest.mark.parametrize(
    "wrapper_hint",
    [
        "createTokenAwareRetry",
        "github-rate-limited-wrapper.js",
        "paginateWithRetry",
        "github-api-with-retry.js",
        "ensureRateLimitWrapped",
    ],
)
def test_scan_file_allows_wrapped_api_calls(
    guard_root: Path,
    wrapper_hint: str,
) -> None:
    path = guard_root / "scripts" / "wrapped.js"
    path.write_text(
        "\n".join(
            [
                f"const wrapper = '{wrapper_hint}';",
                "await github.rest.repos.get({ owner, repo });",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert guard._scan_file(path) == []


def test_scan_file_yaml_missing_load_balancer_step(guard_root: Path) -> None:
    path = guard_root / ".github" / "workflows" / "bad.yml"
    path.write_text(
        "\n".join(
            [
                "name: bad",
                "on: push",
                "jobs:",
                "  run:",
                "    steps:",
                "      - run: octokit.request('GET /repos/{owner}/{repo}')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = guard._scan_file(path)

    assert violations == [
        ".github/workflows/bad.yml:6: API call without createTokenAwareRetry",
        ".github/workflows/bad.yml: missing export-load-balancer-tokens or setup-api-client step",
    ]


def test_scan_file_yaml_with_setup_api_client_has_no_load_balancer_violation(
    guard_root: Path,
) -> None:
    path = guard_root / ".github" / "workflows" / "wrapped.yml"
    path.write_text(
        "\n".join(
            [
                "name: wrapped",
                "on: push",
                "jobs:",
                "  run:",
                "    steps:",
                "      - uses: ./.github/actions/setup-api-client",
                "      - run: github.rest.repos.get()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = guard._scan_file(path)

    assert violations == [
        ".github/workflows/wrapped.yml:7: API call without createTokenAwareRetry",
    ]


@pytest.mark.parametrize(
    ("relative_path", "suffix"),
    [
        ("scripts/tests/mock.js", ".js"),
        ("scripts/__tests__/mock.js", ".js"),
        (".github/workflows/tests/mock.yml", ".yml"),
        ("scripts/node_modules/pkg/index.js", ".js"),
    ],
)
def test_is_target_file_skips_tests_and_node_modules(
    guard_root: Path,
    relative_path: str,
    suffix: str,
) -> None:
    path = guard_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"gh api /repos{suffix}\n", encoding="utf-8")

    assert guard._is_target_file(path) is False


def test_is_target_file_skips_known_skip_files(guard_root: Path) -> None:
    path = guard_root / "scripts" / "api_client.py"
    path.write_text("gh api /repos\n", encoding="utf-8")

    assert guard._is_target_file(path) is False


def test_collect_all_files_skips_node_modules(guard_root: Path) -> None:
    allowed = guard_root / "scripts" / "scan-me.js"
    skipped = guard_root / "scripts" / "node_modules" / "pkg" / "index.js"
    allowed.write_text("// ok\n", encoding="utf-8")
    skipped.parent.mkdir(parents=True)
    skipped.write_text("gh api /repos\n", encoding="utf-8")

    collected = guard._collect_all_files()

    assert allowed in collected
    assert skipped not in collected


def test_main_all_reports_violation_message_shape(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = guard_root / "scripts" / "bad.js"
    bad.write_text('run("gh api /repos/owner/repo");\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_api_wrapper_guard.py", "--all"])

    exit_code = guard.main()
    captured = capsys.readouterr().out

    assert exit_code == 1
    assert captured == (
        "API guard violations detected:\n\n" "- scripts/bad.js:1: direct gh api usage\n"
    )


def test_main_all_clean_exit_zero(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clean = guard_root / "scripts" / "clean.js"
    clean.write_text(
        "\n".join(
            [
                "const { createTokenAwareRetry } = require('./helper');",
                "await github.rest.repos.get();",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["check_api_wrapper_guard.py", "--all"])

    exit_code = guard.main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert captured == "No API guard violations detected.\n"


def test_main_writes_output_file(guard_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = guard_root / "scripts" / "bad.js"
    output = guard_root / "report.md"
    bad.write_text('fetch("https://api.github.com/user");\n', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_api_wrapper_guard.py",
            "--all",
            "--output",
            str(output),
        ],
    )

    exit_code = guard.main()

    assert exit_code == 1
    assert output.read_text(encoding="utf-8") == (
        "API guard violations detected:\n\n" "- scripts/bad.js:1: direct api.github.com usage\n"
    )


def test_main_diff_mode_uses_changed_files(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = guard_root / "scripts" / "changed.js"
    bad.write_text('run("gh api /repos/owner/repo");\n', encoding="utf-8")
    monkeypatch.setattr(guard, "_collect_changed_files", lambda _base, _remote: [bad])
    monkeypatch.setattr(sys, "argv", ["check_api_wrapper_guard.py"])

    exit_code = guard.main()
    captured = capsys.readouterr().out

    assert exit_code == 1
    assert "- scripts/changed.js:1: direct gh api usage" in captured


def test_main_no_matching_files_writes_placeholder(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = guard_root / "empty-report.md"
    monkeypatch.setattr(guard, "_collect_all_files", lambda: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_api_wrapper_guard.py",
            "--all",
            "--output",
            str(output),
        ],
    )

    exit_code = guard.main()

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == "No matching files to scan.\n"


def test_main_no_files_without_output_is_silent(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(guard, "_collect_all_files", lambda: [])
    monkeypatch.setattr(sys, "argv", ["check_api_wrapper_guard.py", "--all"])

    exit_code = guard.main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert captured == ""


def test_main_does_not_write_stdout_when_output_requested(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = guard_root / "scripts" / "bad.js"
    output = guard_root / "report.md"
    bad.write_text('run("gh api /repos/owner/repo");\n', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_api_wrapper_guard.py",
            "--all",
            "--output",
            str(output),
        ],
    )

    exit_code = guard.main()
    captured = capsys.readouterr().out

    assert exit_code == 1
    assert captured == ""
    assert output.exists()


# --- Diff collector/resolver tests ---


def test_resolve_base_ref_remote_ref_exists(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When remote ref already exists locally, return it."""
    monkeypatch.setattr(guard, "_rev_exists", lambda revision: revision == "origin/main")

    result = guard._resolve_base_ref("main", "origin")

    assert result == "origin/main"


def test_resolve_base_ref_fetch_needed(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When remote ref doesn't exist but can be fetched, return it after fetch."""
    call_count = [0]

    def mock_rev_exists(revision: str) -> bool:
        call_count[0] += 1
        return call_count[0] == 2 and revision == "origin/main"

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        # Verify fetch was called
        assert args == ["fetch", "--depth", "1", "origin", "main"]
        return ""

    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)

    result = guard._resolve_base_ref("main", "origin")

    assert result == "origin/main"


def test_resolve_base_ref_fallback_to_base_ref_only(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When remote ref doesn't exist and fetch doesn't help, but base_ref exists locally."""

    def mock_rev_exists(revision: str) -> bool:
        # origin/main doesn't exist, but main does
        return revision == "main"

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        # Fetch was attempted but didn't help
        assert args == ["fetch", "--depth", "1", "origin", "main"]
        return ""

    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)

    result = guard._resolve_base_ref("main", "origin")

    assert result == "main"


def test_resolve_base_ref_not_resolvable(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither remote ref nor base ref can be resolved."""

    def mock_rev_exists(revision: str) -> bool:
        return False

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        return ""

    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)

    result = guard._resolve_base_ref("main", "origin")

    assert result is None


def test_collect_changed_files_successful_diff(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When base ref resolves and diff succeeds, return changed files."""
    changed_file = guard_root / "scripts" / "changed.js"

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return "origin/main"

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        assert args == ["diff", "--name-only", "--diff-filter=d", "origin/main..HEAD"]
        return "scripts/changed.js\n"

    def mock_rev_exists(revision: str) -> bool:
        return True

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)
    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)

    result = guard._collect_changed_files("main", "origin")

    assert result == [changed_file]


def test_collect_changed_files_diff_returns_deleted_files_filtered(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When diff returns deleted files, they should be filtered by --diff-filter=d."""
    changed_file = guard_root / "scripts" / "changed.js"
    deleted_file = guard_root / "scripts" / "deleted.js"

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return "origin/main"

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        # --diff-filter=d should return only deleted files, but we test the path
        assert args == ["diff", "--name-only", "--diff-filter=d", "origin/main..HEAD"]
        # Return both a changed and a deleted file to verify filtering
        return "scripts/changed.js\nscripts/deleted.js\n"

    def mock_rev_exists(revision: str) -> bool:
        return True

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)
    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)

    result = guard._collect_changed_files("main", "origin")

    # Both files should be in the result (diff-filter=d returns deleted files from the diff)
    assert changed_file in result
    assert deleted_file in result


def test_collect_changed_files_fallback_to_head_minus_one(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When base ref diff fails but HEAD~1 exists, use HEAD~1..HEAD."""
    changed_file = guard_root / "scripts" / "changed.js"

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return "origin/main"

    call_count = [0]

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: diff against base ref fails
            assert args == ["diff", "--name-only", "--diff-filter=d", "origin/main..HEAD"]
            raise RuntimeError("diff failed")
        # Second call: diff against HEAD~1 succeeds
        assert args == ["diff", "--name-only", "--diff-filter=d", "HEAD~1..HEAD"]
        return "scripts/changed.js\n"

    def mock_rev_exists(revision: str) -> bool:
        return revision in {"origin/main", "HEAD~1"}

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)
    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)

    result = guard._collect_changed_files("main", "origin")

    assert result == [changed_file]


def test_collect_changed_files_fallback_to_all_files(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When base ref diff fails, HEAD~1 doesn't exist, fallback to all files."""
    all_files = [guard_root / "scripts" / "file1.js", guard_root / "scripts" / "file2.js"]

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return "origin/main"

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        # Both diff attempts fail
        if "origin/main..HEAD" in " ".join(args):
            raise RuntimeError("diff failed")
        if "HEAD~1..HEAD" in " ".join(args):
            raise RuntimeError("diff failed")
        raise RuntimeError("unexpected git call")

    def mock_rev_exists(revision: str) -> bool:
        return revision == "origin/main"

    def mock_collect_all_files() -> list[Path]:
        return all_files

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)
    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)
    monkeypatch.setattr(guard, "_collect_all_files", mock_collect_all_files)

    result = guard._collect_changed_files("main", "origin")

    assert result == all_files


def test_collect_changed_files_base_ref_unresolvable_raises(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When base ref cannot be resolved, raise RuntimeError."""

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return None

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)

    with pytest.raises(RuntimeError, match="Unable to resolve base ref"):
        guard._collect_changed_files("nonexistent", "origin")


def test_collect_changed_files_head_minus_one_fallback_also_fails_uses_all_files(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When HEAD~1..HEAD also fails, fallback to _collect_all_files."""
    all_files = [guard_root / "scripts" / "file1.js"]

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return "origin/main"

    call_count = [0]

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            assert args == ["diff", "--name-only", "--diff-filter=d", "origin/main..HEAD"]
            raise RuntimeError("diff failed")
        if call_count[0] == 2:
            assert args == ["diff", "--name-only", "--diff-filter=d", "HEAD~1..HEAD"]
            raise RuntimeError("diff failed")
        raise RuntimeError("unexpected git call")

    def mock_rev_exists(revision: str) -> bool:
        return revision in {"origin/main", "HEAD~1"}

    def mock_collect_all_files() -> list[Path]:
        return all_files

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)
    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)
    monkeypatch.setattr(guard, "_collect_all_files", mock_collect_all_files)

    result = guard._collect_changed_files("main", "origin")

    assert result == all_files


def test_collect_changed_files_head_minus_one_diff_returns_empty(
    guard_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When HEAD~1..HEAD diff succeeds but returns no files, return empty list."""

    def mock_resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
        return "origin/main"

    call_count = [0]

    def mock_run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            assert args == ["diff", "--name-only", "--diff-filter=d", "origin/main..HEAD"]
            raise RuntimeError("diff failed")
        if call_count[0] == 2:
            assert args == ["diff", "--name-only", "--diff-filter=d", "HEAD~1..HEAD"]
            return ""  # Empty output
        raise RuntimeError("unexpected git call")

    def mock_rev_exists(revision: str) -> bool:
        return revision in ("origin/main", "HEAD~1")

    def mock_collect_all_files() -> list[Path]:
        return []

    monkeypatch.setattr(guard, "_resolve_base_ref", mock_resolve_base_ref)
    monkeypatch.setattr(guard, "_run_git", mock_run_git)
    monkeypatch.setattr(guard, "_rev_exists", mock_rev_exists)
    monkeypatch.setattr(guard, "_collect_all_files", mock_collect_all_files)

    result = guard._collect_changed_files("main", "origin")

    assert result == []
