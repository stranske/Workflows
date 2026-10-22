"""Run the authored acceptance job against a polluted ambient pytest environment."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CALLERS = [
    ".github/workflows/agents-verifier.yml",
    "templates/consumer-repo/.github/workflows/agents-verifier.yml",
]


@pytest.mark.parametrize("relative", CALLERS)
@pytest.mark.parametrize(
    "broken_plugin", [False, True], ids=["declared-plugin-valid", "declared-plugin-failing"]
)
def test_acceptance_job_isolates_python_and_preserves_declared_plugin_loading(
    tmp_path, relative, broken_plugin
):
    job = yaml.safe_load((ROOT / relative).read_text())["jobs"]["acceptance-gates"]
    script = next(
        step["run"]
        for step in job["steps"]
        if step.get("name") == "Run acceptance commands without workflow secrets"
    )
    head = tmp_path / "acceptance-head"
    head.mkdir()
    (head / "pyproject.toml").write_text(
        '[project]\nname="acceptance-fixture"\nversion="1.0"\n'
        '[project.optional-dependencies]\ntest=["declared-gate-plugin==1.0"]\n'
    )
    (head / "requirements.txt").write_text("declared-gate-plugin==1.0\n")
    (head / "test_acceptance.py").write_text(
        "import os, shutil, sys\n"
        "def test_collection(request):\n"
        "    assert request.config._declared_gate_plugin_loaded\n"
        "    assert sys.prefix != sys.base_prefix\n"
        "    assert shutil.which('pytest').startswith(sys.prefix + os.sep)\n"
        "    assert 'PYTEST_DISABLE_PLUGIN_AUTOLOAD' not in os.environ\n"
        "    assert 'GATE_SENTINEL_SECRET' not in os.environ\n"
        "    print('ACCEPTANCE_COLLECTION_READY')\n"
    )
    source_hash = hashlib.sha256((head / "test_acceptance.py").read_bytes()).hexdigest()
    plans = tmp_path / "closure-plans"
    plans.mkdir()
    plan = {
        "repository": "owner/repo",
        "pr_number": 4175,
        "head_sha": "a" * 40,
        "source_hash": "b" * 64,
        "gate_source": "acceptance-commands",
        "markdown": "## Acceptance Criteria\n- [ ] `pytest -q -s test_acceptance.py` passes\n",
        "commands": [{"criterion": 0, "command": "pytest -q -s test_acceptance.py"}],
    }
    (plans / "plans.json").write_text(json.dumps([plan]))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    polluted = tmp_path / "ambient-plugins"
    polluted.mkdir()
    metadata = polluted / "stale_platformdirs-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: stale-platformdirs\nVersion: 1.0\n")
    (metadata / "entry_points.txt").write_text(
        "[pytest11]\nplatformdirs = platformdirs.pytest_plugin\n"
    )
    # Existing pytest engine and its dependencies are linked read-only into the
    # offline venv. No global/site packages or ambient entry-point metadata enter it.
    modules = [
        "pytest",
        "_pytest",
        "pluggy",
        "iniconfig",
        "packaging",
        "pygments",
        "py",
        "typing_extensions",
    ]
    module_paths = {}
    for name in modules:
        spec = importlib.util.find_spec(name)
        assert spec is not None
        module_paths[name] = str(
            Path(spec.origin).parent if spec.submodule_search_locations else Path(spec.origin)
        )
    bootstrap = f"""#!{sys.executable}
import json, pathlib, subprocess, sys, venv
if sys.argv[1:3] == ['-m', 'venv']:
    target = pathlib.Path(sys.argv[3])
    venv.EnvBuilder(with_pip=False).create(target)
    python = target / 'bin/python3'
    purelib = pathlib.Path(subprocess.check_output([str(python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip())
    for name, source in {module_paths!r}.items():
        source = pathlib.Path(source)
        (purelib / (name if source.is_dir() else name + '.py')).symlink_to(source, target_is_directory=source.is_dir())
    entry = target / 'bin/pytest'
    entry.write_text('#!' + str(python) + '\\nfrom pytest import console_main\\nraise SystemExit(console_main())\\n')
    entry.chmod(0o755)
    raise SystemExit(0)
import os
os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
"""
    (binaries / "python3").write_text(bootstrap)
    (binaries / "python3").chmod(0o755)
    (binaries / "pytest").write_text(
        "#!/bin/sh\nexport PYTHONPATH="
        + shlex.quote(str(polluted))
        + "\nexec "
        + shlex.quote(sys.executable)
        + ' -m pytest "$@"\n'
    )
    (binaries / "pytest").chmod(0o755)
    helper = tmp_path / "gate-runner/scripts/runner_lib/acceptance_gate.py"
    helper.parent.mkdir(parents=True)
    # Only package installation is replaced with an offline declared-plugin fixture.
    # Extraction, prepare dependency discovery, command execution and result writing
    # all run the actual production helper, including its credential whitelist.
    plugin_code = (
        "raise RuntimeError('declared project plugin failed')\n"
        if broken_plugin
        else "def pytest_configure(config): config._declared_gate_plugin_loaded = True\n"
    )
    helper.write_text(f"""
import importlib.util, json, pathlib, shlex, sys, sysconfig
spec = importlib.util.spec_from_file_location('production_acceptance_gate', {str(ROOT / 'scripts/runner_lib/acceptance_gate.py')!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
real_run = module.run
log = pathlib.Path({str(tmp_path / 'install-observations.json')!r})
def offline_install(commands, cwd):
    argv = shlex.split(commands[0].command)
    if argv[1:4] != ['-m', 'pip', 'install']:
        return real_run(commands, cwd)
    observations = json.loads(log.read_text()) if log.exists() else []
    observations.append({{'argv': argv, 'executable': sys.executable, 'prefix': sys.prefix}})
    log.write_text(json.dumps(observations))
    if sys.prefix != sys.base_prefix and ('-e' in argv or '-r' in argv):
        site = pathlib.Path(sysconfig.get_path('purelib'))
        (site / 'declared_gate_plugin.py').write_text({plugin_code!r})
        info = site / 'declared_gate_plugin-1.0.dist-info'
        info.mkdir(exist_ok=True)
        (info / 'METADATA').write_text('Name: declared-gate-plugin\\nVersion: 1.0\\n')
        (info / 'entry_points.txt').write_text('[pytest11]\\ndeclared_gate_plugin = declared_gate_plugin\\n')
    return [module.Result(-1, commands[0].command, 0, 'offline dependency fixture installed')]
module.run = offline_install
module.main()
""")
    result = subprocess.run(
        ["/bin/bash", "-eu", "-c", script],
        cwd=tmp_path,
        env={
            "PATH": str(binaries) + os.pathsep + os.defpath,
            "RUNNER_TEMP": str(runner_temp),
            "HOME": str(tmp_path),
            "GATE_SENTINEL_SECRET": "must-not-reach-acceptance",
        },
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads((tmp_path / "closure-results.json").read_text())[0]
    assert {k: receipt[k] for k in plan} == plan
    if broken_plugin:
        assert receipt["results"][0]["exit_code"] != 0
        assert "declared project plugin failed" in receipt["results"][0]["output"]
    else:
        assert receipt["results"][0]["exit_code"] == 0, receipt["results"]
        assert "ACCEPTANCE_COLLECTION_READY" in receipt["results"][0]["output"]
    assert hashlib.sha256((head / "test_acceptance.py").read_bytes()).hexdigest() == source_hash
    installs = json.loads((tmp_path / "install-observations.json").read_text())
    assert all(row["executable"].startswith(str(runner_temp)) for row in installs)
    assert any(row["argv"][-2:] == ["-e", ".[test]"] for row in installs)
    assert any(row["argv"][-2:] == ["-r", "requirements.txt"] for row in installs)
    assert all("platformdirs.pytest_plugin" not in row["output"] for row in receipt["results"])


@pytest.mark.parametrize("relative", CALLERS)
def test_acceptance_runtime_is_explicit_and_security_boundary_unchanged(relative):
    job = yaml.safe_load((ROOT / relative).read_text())["jobs"]["acceptance-gates"]
    setup = next(s for s in job["steps"] if s.get("name") == "Set up acceptance Python")
    assert setup["uses"].startswith("actions/setup-python@")
    assert setup["with"]["python-version"] == "3.14"
    assert job["permissions"] == {"contents": "read"}
    assert "secrets." not in str(job) and "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in str(job)
    checkout = next(s for s in job["steps"] if s.get("name") == "Checkout immutable merge commit")
    assert checkout["with"]["ref"] == "${{ needs.verifier.outputs.target_sha }}"
    assert checkout["with"]["persist-credentials"] is False
