"""Bounded pip regression for trip-planner #2006's actual checkout metadata.

Runs 42449207754 and 42484305260 install local editable projects with [dev].
The former selects TPP acc4aed and fails; the latter selects b56d92b and passes.
Metadata-only wheels and editable checkouts retain the three reported tool
requirements and dev extra markers. This checks resolution, not product builds,
runtime dependencies or publication.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from scripts.sync_dev_dependencies import parse_env_file, sync_pyproject

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/dependency_resolution"
TOOLS = {"ruff": "RUFF_VERSION", "mypy": "MYPY_VERSION", "pytest": "PYTEST_VERSION"}
PROJECTS = ("trip-planner", "travel-plan-permission")
# Leave startup/assertion overhead inside the issue's 120-second limit.
RESOLUTION_DEADLINE = time.monotonic() + 100


def tool_requirements(path: Path) -> dict[str, Requirement]:
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    requirements: dict[str, Requirement] = {
        canonicalize_name(req.name): req
        for entry in project["optional-dependencies"]["dev"]
        if canonicalize_name((req := Requirement(entry)).name) in TOOLS
    }
    assert requirements.keys() == TOOLS.keys()
    for requirement in requirements.values():
        specs = list(requirement.specifier)
        assert len(specs) == 1 and specs[0].operator == "=="
        assert requirement.marker is None
    return requirements


def write_wheel(directory: Path, name: str, version: str, metadata: str = "") -> None:
    normalized = name.replace("-", "_")
    dist_info = f"{normalized}-{version}.dist-info"
    with ZipFile(directory / f"{normalized}-{version}-py3-none-any.whl", "w") as wheel:
        wheel.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n{metadata}",
        )
        wheel.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(f"{dist_info}/RECORD", "")


def resolve(
    directory: Path, paths: dict[str, Path], *, editable: bool = False
) -> tuple[subprocess.CompletedProcess, Path]:
    directory.mkdir()
    roots = []
    for project, path in paths.items():
        requirements = tool_requirements(path)
        metadata = "Provides-Extra: dev\n" + "".join(
            f'Requires-Dist: {req}; extra == "dev"\n' for req in requirements.values()
        )
        if editable:
            checkout = directory / project
            checkout.mkdir()
            (checkout / "editable_backend.py").write_bytes(
                (FIXTURES / "editable_backend.py").read_bytes()
            )
            # Retain the same bounded requirements as the wheel cases, while
            # asking pip to prepare both local editable projects' dev extras.
            (checkout / "pyproject.toml").write_text(
                '[build-system]\nrequires = []\nbuild-backend = "editable_backend"\n'
                'backend-path = ["."]\n[project]\n'
                f'name = "{project}"\nversion = "0.1.0"\n'
                "[project.optional-dependencies]\n"
                f"dev = {json.dumps([str(req) for req in requirements.values()])}\n",
                encoding="utf-8",
            )
            roots.extend(["-e", f"{checkout}[dev]"])
        else:
            write_wheel(directory, project, "0.1.0", metadata)
            roots.append(f"{project}[dev]==0.1.0")
        # Include both sides' candidates: missing wheels must not explain failure.
        for name, req in requirements.items():
            write_wheel(directory, name, next(iter(req.specifier)).version)
    report = directory / "report.json"
    remaining = RESOLUTION_DEADLINE - time.monotonic()
    if remaining <= 0:
        pytest.fail("pip dependency resolution exhausted the 100-second suite budget")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "install",
                "--dry-run",
                "--ignore-installed",
                "--no-index",
                "--no-cache-dir",
                "--no-build-isolation",
                "--find-links",
                str(directory),
                "--report",
                str(report),
                *roots,
            ],
            capture_output=True,
            text=True,
            timeout=min(20, remaining),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"pip dependency resolution timed out after {exc.timeout:.1f}s: {roots}")
    return result, report


def assert_resolved(result: subprocess.CompletedProcess, report: Path, planner: Path) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    installed = json.loads(report.read_text(encoding="utf-8"))["install"]
    actual = {
        canonicalize_name(item["metadata"]["name"]): item["metadata"]["version"]
        for item in installed
    }
    expected = {
        name: next(iter(req.specifier)).version for name, req in tool_requirements(planner).items()
    }
    assert actual == {**expected, **dict.fromkeys(PROJECTS, "0.1.0")}


@pytest.mark.parametrize("editable", [False, True], ids=["wheels", "editable"])
def test_original_checkouts_reproduce_resolution_impossible(tmp_path: Path, editable: bool) -> None:
    paths = {name: FIXTURES / "failed" / f"{name}.toml" for name in PROJECTS}
    result, _ = resolve(tmp_path / "wheels", paths, editable=editable)
    diagnostics = result.stdout + result.stderr
    assert result.returncode == 1, diagnostics
    assert "ResolutionImpossible" in diagnostics
    for name, path in paths.items():
        assert f"{name}[dev]" in diagnostics
        assert str(tool_requirements(path)["ruff"]) in diagnostics


@pytest.mark.parametrize("editable", [False, True], ids=["wheels", "editable"])
def test_successful_checkouts_resolve(tmp_path: Path, editable: bool) -> None:
    paths = {name: FIXTURES / "successful" / f"{name}.toml" for name in PROJECTS}
    result, report = resolve(tmp_path / "wheels", paths, editable=editable)
    assert_resolved(result, report, paths["trip-planner"])
    if editable:
        installed = json.loads(report.read_text(encoding="utf-8"))["install"]
        projects = [item for item in installed if item["metadata"]["name"] in PROJECTS]
        assert len(projects) == 2
        for item in projects:
            download = item["download_info"]
            assert download["dir_info"]["editable"] is True
            assert download["url"] == (tmp_path / "wheels" / item["metadata"]["name"]).as_uri()


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_each_historical_tool_mismatch_fails_until_restored(tmp_path: Path, tool: str) -> None:
    """Ruff must not mask the historical mypy and pytest pin conflicts."""
    paths = {name: tmp_path / f"{name}.toml" for name in PROJECTS}
    for name, path in paths.items():
        path.write_bytes((FIXTURES / "successful" / f"{name}.toml").read_bytes())

    producer = paths["travel-plan-permission"]
    successful = producer.read_bytes()
    current = tool_requirements(producer)[tool]
    original = tool_requirements(FIXTURES / "failed/travel-plan-permission.toml")[tool]
    assert current != original, f"{tool} must reproduce a historical pin change"
    assert current == tool_requirements(paths["trip-planner"])[tool]
    producer.write_text(
        successful.decode("utf-8").replace(f'"{current}"', f'"{original}"'),
        encoding="utf-8",
    )
    assert tool_requirements(producer)[tool] == original

    result, _ = resolve(tmp_path / "conflicting", paths)
    diagnostics = result.stdout + result.stderr
    assert result.returncode == 1 and "ResolutionImpossible" in diagnostics, diagnostics
    for project, requirement in (("travel-plan-permission", original), ("trip-planner", current)):
        assert f'{project}[dev] 0.1.0 depends on {requirement}; extra == "dev"' in diagnostics

    producer.write_bytes(successful)
    result, report = resolve(tmp_path / "restored", paths)
    assert_resolved(result, report, paths["trip-planner"])


def test_canonical_pin_sync_requires_both_consumers(tmp_path: Path) -> None:
    """Maint 52 must propagate source pins to both projects sharing an interpreter."""
    pins = parse_env_file(ROOT / ".github/workflows/autofix-versions.env")
    assert set(TOOLS.values()) <= pins.keys()
    paths = {name: tmp_path / f"{name}.toml" for name in PROJECTS}
    for name, path in paths.items():
        path.write_bytes((FIXTURES / "failed" / f"{name}.toml").read_bytes())

    _, errors = sync_pyproject(paths["trip-planner"], pins, apply=True)
    assert not errors
    result, _ = resolve(tmp_path / "one-consumer", paths)
    diagnostics = result.stdout + result.stderr
    assert result.returncode == 1 and "ResolutionImpossible" in diagnostics, diagnostics

    changes, errors = sync_pyproject(paths["travel-plan-permission"], pins, apply=True)
    assert changes and not errors
    for path in paths.values():
        requirements = tool_requirements(path)
        assert all(
            str(requirements[name].specifier) == f"=={pins[key]}" for name, key in TOOLS.items()
        )
        assert sync_pyproject(path, pins) == ([], [])
    result, report = resolve(tmp_path / "both-consumers", paths)
    assert_resolved(result, report, paths["trip-planner"])
