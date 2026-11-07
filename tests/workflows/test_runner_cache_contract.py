"""Installed runner caches must restore the artifacts actually consumed by setup.

These local contracts do not establish a hosted cache hit; #3978 also requires
second-round keepalive log evidence after merge.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
AGENTS = ("codex", "claude", "cursor", "gemini", "muse")
CACHE_REF = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"


def _runner(agent: str) -> tuple[dict, dict]:
    workflow = yaml.safe_load((WORKFLOWS / f"reusable-{agent}-run.yml").read_text())
    return workflow, workflow["jobs"][agent]


def _step(job: dict, name: str) -> dict:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, f"Missing or duplicate step: {name}"
    return matches[0]


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: f"reusable-{agent}-run.yml")
def test_cli_cache_tracks_installed_version_and_path(agent: str) -> None:
    workflow, job = _runner(agent)
    filename = f".github/workflows/reusable-{agent}-run.yml"
    caches = [step for step in job["steps"] if step.get("id") == f"{agent}_cli_cache"]
    assert len(caches) == 1, f"{filename}: missing CLI cache step"
    cache = caches[0]
    assert cache["uses"] == CACHE_REF, filename
    assert cache.get("if", True) in (
        True,
        "${{ !cancelled() }}",
    ), f"{filename}: CLI cache restore must run unless cancelled"
    key = cache["with"]["key"]
    assert "${{ runner.os }}" in key, filename
    assert "${{ runner.arch }}" in key, filename
    version_var = f"{agent.upper()}_CLI_VERSION"
    assert f"${{{{ env.{version_var} }}}}" in key, f"{filename}: CLI cache key missing version"
    assert (
        "restore-keys" not in cache["with"]
    ), f"{filename}: CLI cache must match the exact version"
    install = _step(job, "Install Codex CLI" if agent == "codex" else f"Ensure {agent.title()} CLI")
    assert job["steps"].index(cache) < job["steps"].index(
        install
    ), f"{filename}: CLI cache restored after installation"
    expose_step = _step(job, f"Expose cached {agent.title()} CLI")
    assert job["steps"].index(expose_step) < job["steps"].index(
        install
    ), f"{filename}: CLI path exposed after installation"
    expose = expose_step["run"]
    assert '>> "$GITHUB_PATH"' in expose, filename

    if agent != "muse":
        inputs = (workflow.get("on") or workflow[True])["workflow_call"]["inputs"]
        default = inputs[f"{agent}_cli_version"]["default"]
        assert default and default not in ("latest", "stable"), filename
        if agent in ("codex", "claude", "gemini"):
            assert re.fullmatch(
                r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", default
            ), f"{filename}: CLI default must pin an exact npm release"
        assert job["env"][version_var] == (
            f"${{{{ inputs.{agent}_cli_version || '{default}' }}}}"
        ), f"{filename}: CLI cache fallback differs from input default"
        prefix = f"${{{{ runner.temp }}}}/agent-cli/{agent}"
        assert cache["with"]["path"] == prefix, filename
        assert prefix in expose, filename
        if agent in ("codex", "claude", "gemini"):
            assert install["env"]["NPM_CONFIG_PREFIX"] == prefix, filename
            assert "node24" in key, filename
            assert re.search(
                r"npm install -g .*\$\{(?:CODEX_CLI_VERSION|VERSION)", install["run"]
            ), filename
            effective_version = install["env"].get(version_var, install["env"].get("VERSION"))
            assert effective_version in (
                job["env"][version_var],
                f"${{{{ env.{version_var} }}}}",
            ), filename
            if agent == "codex":
                assert install["if"] == "steps.codex_cli_cache.outputs.cache-hit != 'true'"
            else:
                assert f"command -v {agent}" in install["run"], filename
        else:
            assert "${CURSOR_CLI_VERSION}/linux/${arch}/agent-cli-package.tar.gz" in install["run"]
            assert 'tar --strip-components=1 -xzf - -C "$cli_dir"' in install["run"]
    else:
        resolve = _step(job, "Resolve Muse CLI version")
        assert job["steps"].index(resolve) < job["steps"].index(cache)
        assert 'echo "MUSE_CLI_VERSION=$version" >> "$GITHUB_ENV"' in resolve["run"]
        assert job["env"]["MUSE_NO_AUTO_UPDATE"] == "1"
        assert "muse-bin-${{ env.MUSE_CLI_VERSION }}" in cache["with"]["path"]
        assert ".muse-version" in cache["with"]["path"]
        assert ".muse-release-info.json" in cache["with"]["path"]
        assert '!= "$MUSE_CLI_VERSION"' in install["run"]
        assert ".config" not in cache["with"]["path"]
        assert "auth" not in cache["with"]["path"]
    if agent == "claude":
        assert "${{ env.CLAUDE_CLI_PACKAGE }}" in key


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: f"reusable-{agent}-run.yml")
@pytest.mark.parametrize(
    "regression",
    (
        "missing-cache",
        "unversioned-key",
        "late-path",
        "skipped-cache",
        "late-cache",
        "fallback-key",
    ),
)
def test_cli_cache_contract_rejects_regressions(
    agent: str, regression: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutate parsed copies so protected workflow files are never rewritten."""
    workflow, job = _runner(agent)
    cache = next(step for step in job["steps"] if step.get("id") == f"{agent}_cli_cache")
    if regression == "missing-cache":
        job["steps"].remove(cache)
    elif regression == "unversioned-key":
        version = f"${{{{ env.{agent.upper()}_CLI_VERSION }}}}"
        assert version in cache["with"]["key"]
        cache["with"]["key"] = cache["with"]["key"].replace(version, "fixed")
    elif regression == "late-path":
        expose = _step(job, f"Expose cached {agent.title()} CLI")
        job["steps"].remove(expose)
        job["steps"].append(expose)
    elif regression == "skipped-cache":
        cache["if"] = False
    elif regression == "late-cache":
        job["steps"].remove(cache)
        job["steps"].append(cache)
    else:
        cache["with"]["restore-keys"] = "${{ runner.os }}-"

    monkeypatch.setattr(f"{__name__}._runner", lambda requested: (workflow, job))
    filename = f".github/workflows/reusable-{agent}-run.yml"
    messages = {
        "missing-cache": "missing CLI cache step",
        "unversioned-key": "CLI cache key missing version",
        "late-path": "CLI path exposed after installation",
        "skipped-cache": "CLI cache restore must run unless cancelled",
        "late-cache": "CLI cache restored after installation",
        "fallback-key": "CLI cache must match the exact version",
    }
    with pytest.raises(AssertionError, match=re.escape(f"{filename}: {messages[regression]}")):
        test_cli_cache_tracks_installed_version_and_path(agent)


@pytest.mark.parametrize(
    "inherited_addopts",
    ("", "-x --maxfail=1", "--collect-only"),
    ids=("default", "inherited-exitfirst", "inherited-collect-only"),
)
def test_cli_cache_deletion_fails_pytest_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inherited_addopts: str
) -> None:
    """Check pytest's exit status and diagnostic without editing protected workflows."""
    monkeypatch.setenv("PYTEST_ADDOPTS", inherited_addopts)
    plugin = tmp_path / "runner_cache_break.py"
    plugin.write_text(textwrap.dedent("""\
            import pytest

            @pytest.fixture(autouse=True)
            def remove_codex_cache(request, monkeypatch):
                original = request.module._runner

                def without_cache(agent):
                    workflow, job = original(agent)
                    if agent == "codex":
                        job["steps"] = [
                            step for step in job["steps"]
                            if step.get("id") != "codex_cli_cache"
                        ]
                    return workflow, job

                monkeypatch.setattr(request.module, "_runner", without_cache)
            """))
    command = [
        sys.executable,
        "-m",
        "pytest",
        str(Path(__file__).resolve()),
        "-k",
        "test_cli_cache_tracks_installed_version_and_path",
        "-m",
        "not slow",
        "--noconftest",
        "-o",
        "addopts=",
        "-q",
    ]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(tmp_path), os.environ.get("PYTHONPATH", "")]),
        # -o addopts= clears ini options, but inherited env options still apply.
        # Both subprocesses must execute all five runner assertions.
        "PYTEST_ADDOPTS": "",
    }
    broken = subprocess.run(
        [*command, "-p", "runner_cache_break"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    diagnostic = broken.stdout + broken.stderr
    assert broken.returncode == pytest.ExitCode.TESTS_FAILED, diagnostic
    assert ".github/workflows/reusable-codex-run.yml: missing CLI cache step" in diagnostic
    assert "1 failed, 4 passed" in broken.stdout, diagnostic

    recovered = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
    )
    assert recovered.returncode == pytest.ExitCode.OK, recovered.stdout + recovered.stderr
    assert "5 passed" in recovered.stdout


@pytest.mark.parametrize("agent", ("codex", "claude", "gemini"))
@pytest.mark.parametrize("version", ("next", "^1.0.0", "~1.0.0", "*"))
def test_cli_cache_contract_rejects_floating_npm_defaults(
    agent: str, version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stable cache key cannot describe a moving npm release selection."""
    workflow, job = _runner(agent)
    inputs = (workflow.get("on") or workflow[True])["workflow_call"]["inputs"]
    inputs[f"{agent}_cli_version"]["default"] = version
    version_var = f"{agent.upper()}_CLI_VERSION"
    job["env"][version_var] = f"${{{{ inputs.{agent}_cli_version || '{version}' }}}}"
    if agent == "codex":
        _step(job, "Install Codex CLI")["env"][version_var] = job["env"][version_var]
    monkeypatch.setattr(f"{__name__}._runner", lambda requested: (workflow, job))
    filename = f".github/workflows/reusable-{agent}-run.yml"
    with pytest.raises(
        AssertionError, match=re.escape(f"{filename}: CLI default must pin an exact npm release")
    ):
        test_cli_cache_tracks_installed_version_and_path(agent)


@pytest.mark.parametrize("agent", ("codex", "claude", "cursor", "gemini"))
def test_cli_cache_contract_rejects_different_version_fallback(
    agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow, job = _runner(agent)
    version_var = f"{agent.upper()}_CLI_VERSION"
    # Retain the input default as a substring to exercise the former weak check.
    job["env"][version_var] = job["env"][version_var].replace("|| '", "|| '1")
    if agent == "codex":
        _step(job, "Install Codex CLI")["env"][version_var] = job["env"][version_var]
    monkeypatch.setattr(f"{__name__}._runner", lambda requested: (workflow, job))
    filename = f".github/workflows/reusable-{agent}-run.yml"
    with pytest.raises(
        AssertionError,
        match=re.escape(f"{filename}: CLI cache fallback differs from input default"),
    ):
        test_cli_cache_tracks_installed_version_and_path(agent)


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: f"reusable-{agent}-run.yml")
def test_octokit_restore_precedes_both_install_surfaces(agent: str) -> None:
    _, job = _runner(agent)
    steps = job["steps"]
    for surface, path, consumer in (
        (
            "workspace",
            ".github/scripts",
            "Agent run base setup" if agent in ("codex", "claude") else "Setup API client",
        ),
        ("Workflows", ".workflows-lib/.github/scripts", "Ensure Workflows script deps"),
    ):
        cache = _step(job, f"Cache {surface} Octokit dependencies")
        filename = f".github/workflows/reusable-{agent}-run.yml"
        key = cache["with"]["key"]
        action_path = f"{Path(path).parent}/actions/setup-api-client/action.yml"
        assert cache["uses"] == CACHE_REF, filename
        assert cache["with"]["path"] == f"{path}/node_modules", filename
        # The action contains the exact Octokit pins; both inputs must be hashed
        # from the checkout whose installed modules are being restored.
        assert f"hashFiles('{path}/package-lock.json', '{action_path}')" in key, filename
        assert "${{ runner.os }}" in key, filename
        assert "${{ runner.arch }}" in key, filename
        assert "node24" in key, filename
        assert "restore-keys" not in cache["with"], filename
        assert steps.index(cache) < steps.index(_step(job, consumer)), filename


@pytest.mark.parametrize("surface", ("workspace", "Workflows"))
@pytest.mark.parametrize("missing_lru_cache", (False, True), ids=("complete", "needs-repair"))
def test_octokit_restore_skips_install_and_repairs_incomplete_cache(
    surface: str, missing_lru_cache: bool, tmp_path: Path
) -> None:
    """Exercise the shared installer with cached modules and an offline npm stub."""
    _, job = _runner("codex")
    cache = _step(job, f"Cache {surface} Octokit dependencies")
    action_dir = ROOT / ".github/actions/setup-api-client"
    action = yaml.safe_load((action_dir / "action.yml").read_text())
    setup = {"steps": action["runs"]["steps"]}
    install = _step(setup, "Install API client dependencies")["run"]
    export_path = _step(setup, "Export NODE_PATH for shared deps")["run"]
    fake_bin = tmp_path / "tools"
    fake_bin.mkdir()
    npm = fake_bin / "npm"
    npm.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        'printf "%s\\n" "$*" >> "$INSTALL_LOG"\n'
        'for spec in "$@"; do\n'
        '  case "$spec" in\n'
        "    @octokit/*@*|lru-cache@*)\n"
        '      package="${spec%@*}"\n'
        '      version="${spec##*@}"\n'
        '      mkdir -p "node_modules/$package"\n'
        '      printf \'module.exports = "%s";\\n\' "$version" '
        '> "node_modules/$package/index.js"\n'
        "      ;;\n  esac\ndone\n"
    )
    npm.chmod(0o755)
    log = tmp_path / "installs"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "INSTALL_LOG": str(log),
        "GITHUB_ACTION_PATH": str(action_dir),
    }
    env.pop("NODE_PATH", None)

    def run_setup(workspace: Path) -> None:
        env["GITHUB_WORKSPACE"] = str(workspace)
        env["GITHUB_ENV"] = str(workspace / "github-env")
        # Workspace setup uses the action's default; Workflows setup supplies
        # the explicit install_dir pointing into the shared scripts checkout.
        install_dir = (
            "" if surface == "workspace" else str((workspace / cache["with"]["path"]).parent)
        )
        for script in (install, export_path):
            result = subprocess.run(
                ["/bin/bash", "-c", script.replace("${{ inputs.install_dir }}", install_dir)],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr

    cold = tmp_path / "cold"
    run_setup(cold)
    archive = tmp_path / "archive"
    shutil.copytree(cold / cache["with"]["path"], archive)
    shutil.rmtree(cold)
    restored = tmp_path / "restored"
    modules = restored / cache["with"]["path"]
    shutil.copytree(archive, modules)
    if missing_lru_cache:
        shutil.rmtree(modules / "lru-cache")
    run_setup(restored)

    expected_install = (
        "install --no-save --location=project @octokit/rest@20.0.2 "
        "@octokit/plugin-retry@6.0.1 @octokit/plugin-paginate-rest@9.1.5 "
        "@octokit/auth-app@6.0.3 lru-cache@10.4.3"
    )
    assert log.read_text().splitlines() == [expected_install] * (2 if missing_lru_cache else 1)
    assert (restored / "github-env").read_text() == f"NODE_PATH={modules}\n"
    env["NODE_PATH"] = str(modules)
    probe = subprocess.run(
        ["node", "-p", "require('@octokit/rest') + ':' + require('lru-cache')"],
        cwd=restored,
        env=env,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "20.0.2:10.4.3"


def test_progress_review_caches_pip_before_dependency_install() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "agents-keepalive-loop.yml").read_text())
    job = workflow["jobs"]["progress-review"]
    setup = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert setup["with"]["cache"] == "pip"
    assert (ROOT / setup["with"]["cache-dependency-path"]).is_file()
    assert job["steps"].index(setup) < job["steps"].index(
        _step(job, "Install analysis dependencies")
    )


@pytest.mark.parametrize("agent", ("codex", "claude", "gemini"))
def test_npm_prefix_survives_restore_without_reinstall(agent: str, tmp_path: Path) -> None:
    """Run the actual install shell with a fake npm, then restore into a fresh prefix."""
    workflow, job = _runner(agent)
    install = _step(job, "Install Codex CLI" if agent == "codex" else f"Ensure {agent.title()} CLI")
    expose = _step(job, f"Expose cached {agent.title()} CLI")["run"]
    inputs = (workflow.get("on") or workflow[True])["workflow_call"]["inputs"]
    version = inputs[f"{agent}_cli_version"]["default"]
    fake_bin = tmp_path / "tools"
    fake_bin.mkdir()
    npm = fake_bin / "npm"
    npm.write_text(
        "#!/bin/sh\nset -eu\n"
        'printf "%s\\n" "$*" >> "$INSTALL_LOG"\n'
        'package_dir="$NPM_CONFIG_PREFIX/lib/node_modules/$CLI_PACKAGE"\n'
        'mkdir -p "$NPM_CONFIG_PREFIX/bin" "$package_dir/bin"\n'
        'printf "#!/bin/sh\\necho cached-cli\\n" > "$package_dir/bin/cli.js"\n'
        'chmod +x "$package_dir/bin/cli.js"\n'
        'ln -s "../lib/node_modules/$CLI_PACKAGE/bin/cli.js" '
        '"$NPM_CONFIG_PREFIX/bin/$CLI_BINARY"\n'
    )
    npm.chmod(0o755)
    prefix_template = install["env"]["NPM_CONFIG_PREFIX"]
    prefix = Path(prefix_template.replace("${{ runner.temp }}", str(tmp_path / "cold")))
    log = tmp_path / "installs"
    package = {
        "codex": "@openai/codex",
        "claude": "@anthropic-ai/claude-code",
        "gemini": "@google/gemini-cli",
    }[agent]
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "NPM_CONFIG_PREFIX": str(prefix),
        "INSTALL_LOG": str(log),
        "CLI_BINARY": agent,
        "CLI_PACKAGE": package,
        "CODEX_CLI_VERSION": version,
        "VERSION": version,
        "PACKAGE": "@anthropic-ai/claude-code",
    }

    def expose_prefix(round_name: str) -> None:
        github_path = tmp_path / f"{round_name}-github-path"
        env["GITHUB_PATH"] = str(github_path)
        subprocess.run(
            ["/bin/bash", "-c", expose.replace("${{ runner.temp }}", str(tmp_path / round_name))],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        paths = github_path.read_text().splitlines()
        assert str(Path(env["NPM_CONFIG_PREFIX"]) / "bin") in paths
        env["PATH"] = ":".join([*paths, str(fake_bin), "/usr/bin", "/bin"])

    expose_prefix("cold")
    subprocess.run(
        ["/bin/bash", "-c", install["run"]], env=env, check=True, capture_output=True, text=True
    )
    restored = Path(prefix_template.replace("${{ runner.temp }}", str(tmp_path / "restored")))
    shutil.copytree(prefix, restored, symlinks=True)
    shutil.rmtree(prefix)
    restored_binary = restored / "bin" / agent
    assert restored_binary.is_symlink()
    assert restored_binary.resolve(strict=True) == (
        restored / "lib" / "node_modules" / package / "bin" / "cli.js"
    )
    env.update(PATH=f"{fake_bin}:/usr/bin:/bin", NPM_CONFIG_PREFIX=str(restored))
    expose_prefix("restored")
    if agent != "codex":
        subprocess.run(
            ["/bin/bash", "-c", install["run"]], env=env, check=True, capture_output=True, text=True
        )
    result = subprocess.run(
        [agent, "--version"], env=env, check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "cached-cli"
    assert log.read_text().splitlines() == [f"install -g {package}@{version}"]


def test_muse_resolves_exact_release_and_rejects_unversioned_channel(tmp_path: Path) -> None:
    if not shutil.which("jq"):
        pytest.skip("jq is supplied by the hosted Ubuntu runner")
    _, job = _runner("muse")
    resolve = _step(job, "Resolve Muse CLI version")["run"]
    tools = tmp_path / "tools"
    tools.mkdir()
    curl = tools / "curl"
    curl.write_text('#!/bin/sh\nprintf \'{"version":"%s"}\\n\' "$TEST_VERSION"\n')
    curl.chmod(0o755)
    env_file = tmp_path / "env"
    env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "GITHUB_ENV": str(env_file)}
    for version, expected in (("1.4.10-R6427.1", 0), ("latest", 1)):
        result = subprocess.run(
            ["/bin/bash", "-c", resolve],
            env={**env, "TEST_VERSION": version},
            capture_output=True,
            text=True,
        )
        assert (result.returncode == 0) == (expected == 0), result.stderr
    assert env_file.read_text() == "MUSE_CLI_VERSION=1.4.10-R6427.1\n"


def test_cursor_archive_restore_exposes_cli_without_download(tmp_path: Path) -> None:
    import tarfile

    _, job = _runner("cursor")
    install = _step(job, "Ensure Cursor CLI")["run"]
    tools = tmp_path / "tools"
    tools.mkdir()
    cli = tmp_path / "cursor-agent"
    cli.write_text("#!/bin/sh\necho cached-cursor\n")
    cli.chmod(0o755)
    archive = tmp_path / "cursor.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(cli, arcname="package/cursor-agent")
    log = tmp_path / "downloads"
    curl = tools / "curl"
    curl.write_text(
        "#!/bin/sh\nset -eu\n"
        'case "$*" in\n'
        '  *"/test-release/linux/"*"/agent-cli-package.tar.gz") ;;\n'
        "  *) exit 90 ;;\nesac\n"
        'echo download >> "$DOWNLOAD_LOG"\ncat "$TEST_ARCHIVE"\n'
    )
    curl.chmod(0o755)
    prefix = tmp_path / "cold" / "agent-cli" / "cursor"
    env = {
        **os.environ,
        "PATH": f"{prefix}:{tools}:/usr/bin:/bin",
        "CURSOR_CLI_VERSION": "test-release",
        "DOWNLOAD_LOG": str(log),
        "TEST_ARCHIVE": str(archive),
        "GITHUB_PATH": str(tmp_path / "github-path"),
    }
    install = install.replace("${{ runner.temp }}", str(tmp_path / "cold"))
    subprocess.run(
        ["/bin/bash", "-c", install], env=env, check=True, capture_output=True, text=True
    )
    restored = tmp_path / "restored" / "agent-cli" / "cursor"
    shutil.copytree(prefix, restored, symlinks=True)
    shutil.rmtree(prefix)
    env["PATH"] = f"{restored}:{tools}:/usr/bin:/bin"
    result = subprocess.run(
        ["/bin/bash", "-c", install], env=env, check=True, capture_output=True, text=True
    )
    assert "cached-cursor" in result.stdout
    assert (restored / "agent").resolve() == restored / "cursor-agent"
    assert log.read_text().splitlines() == ["download"]


def test_muse_restored_release_is_used_and_mismatched_release_is_rejected(tmp_path: Path) -> None:
    _, job = _runner("muse")
    # Exercise install/cache validation without running the unchanged host sandbox setup.
    install = _step(job, "Ensure Muse CLI")["run"].split("# Meta's docs:")[0]
    cli_dir = tmp_path / ".local" / "bin"
    cli_dir.mkdir(parents=True)
    binary = cli_dir / "muse-bin-1.4.10-R6427.1"
    binary.write_text("#!/bin/sh\necho restored-muse\n")
    binary.chmod(0o755)
    (cli_dir / "muse").symlink_to(binary.name)
    state = cli_dir / ".muse-version"
    state.write_text("1.4.10-R6427.1\n")
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "MUSE_CLI_VERSION": "1.4.10-R6427.1",
        "MUSE_NO_AUTO_UPDATE": "1",
    }
    result = subprocess.run(["/bin/bash", "-c", install], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "restored-muse" in result.stdout
    state.write_text("1.4.9-R6000.1\n")
    result = subprocess.run(["/bin/bash", "-c", install], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Muse release changed during setup" in result.stdout
