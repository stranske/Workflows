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
