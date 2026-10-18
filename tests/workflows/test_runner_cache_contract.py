"""Installed runner caches must restore the artifacts actually consumed by setup.

These local contracts do not establish a hosted cache hit; #3978 also requires
second-round keepalive log evidence after merge.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
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
    filename = f"reusable-{agent}-run.yml"
    caches = [step for step in job["steps"] if step.get("id") == f"{agent}_cli_cache"]
    assert len(caches) == 1, f"{filename}: missing CLI cache step"
    cache = caches[0]
    assert cache["uses"] == CACHE_REF, filename
    key = cache["with"]["key"]
    assert "${{ runner.os }}" in key, filename
    assert "${{ runner.arch }}" in key, filename
    version_var = f"{agent.upper()}_CLI_VERSION"
    assert f"${{{{ env.{version_var} }}}}" in key, filename
    assert "restore-keys" not in cache["with"], filename
    install = _step(job, "Install Codex CLI" if agent == "codex" else f"Ensure {agent.title()} CLI")
    assert job["steps"].index(cache) < job["steps"].index(install), filename
    expose = _step(job, f"Expose cached {agent.title()} CLI")["run"]
    assert '>> "$GITHUB_PATH"' in expose, filename

    if agent != "muse":
        inputs = (workflow.get("on") or workflow[True])["workflow_call"]["inputs"]
        default = inputs[f"{agent}_cli_version"]["default"]
        assert default and default not in ("latest", "stable"), filename
        assert default in job["env"][version_var], filename
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
        assert cache["uses"] == CACHE_REF
        assert cache["with"]["path"] == f"{path}/node_modules"
        assert f"{path}/package-lock.json" in cache["with"]["key"]
        assert "setup-api-client/action.yml" in cache["with"]["key"]
        assert "${{ runner.os }}" in cache["with"]["key"]
        assert "node24" in cache["with"]["key"]
        assert steps.index(cache) < steps.index(_step(job, consumer))


def test_progress_review_caches_pip_before_dependency_install() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "agents-keepalive-loop.yml").read_text())
    job = workflow["jobs"]["progress-review"]
    setup = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert setup["with"]["cache"] == "pip"
    assert (ROOT / setup["with"]["cache-dependency-path"]).is_file()
    assert job["steps"].index(setup) < job["steps"].index(_step(job, "Install dependencies"))


@pytest.mark.parametrize("agent", ("codex", "claude", "gemini"))
def test_npm_prefix_survives_restore_without_reinstall(agent: str, tmp_path: Path) -> None:
    """Run the actual install shell with a fake npm, then restore into a fresh prefix."""
    _, job = _runner(agent)
    install = _step(job, "Install Codex CLI" if agent == "codex" else f"Ensure {agent.title()} CLI")
    fake_bin = tmp_path / "tools"
    fake_bin.mkdir()
    npm = fake_bin / "npm"
    npm.write_text(
        "#!/bin/sh\nset -eu\n"
        'echo install >> "$INSTALL_LOG"\n'
        'mkdir -p "$NPM_CONFIG_PREFIX/bin"\n'
        'printf "#!/bin/sh\\necho cached-cli\\n" > "$NPM_CONFIG_PREFIX/bin/$CLI_BINARY"\n'
        'chmod +x "$NPM_CONFIG_PREFIX/bin/$CLI_BINARY"\n'
    )
    npm.chmod(0o755)
    prefix = tmp_path / "cold" / agent
    log = tmp_path / "installs"
    env = {
        **os.environ,
        "PATH": f"{prefix / 'bin'}:{fake_bin}:/usr/bin:/bin",
        "NPM_CONFIG_PREFIX": str(prefix),
        "INSTALL_LOG": str(log),
        "CLI_BINARY": agent,
        "CODEX_CLI_VERSION": "0.160.0",
        "VERSION": "1.2.3",
        "PACKAGE": "@anthropic-ai/claude-code",
    }
    subprocess.run(
        ["/bin/bash", "-c", install["run"]], env=env, check=True, capture_output=True, text=True
    )
    restored = tmp_path / "restored" / agent
    shutil.copytree(prefix, restored)
    shutil.rmtree(prefix)
    env.update(PATH=f"{restored / 'bin'}:{fake_bin}:/usr/bin:/bin", NPM_CONFIG_PREFIX=str(restored))
    if agent != "codex":
        subprocess.run(
            ["/bin/bash", "-c", install["run"]], env=env, check=True, capture_output=True, text=True
        )
    result = subprocess.run(
        [agent, "--version"], env=env, check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "cached-cli"
    assert log.read_text().splitlines() == ["install"]


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
