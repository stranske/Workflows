"""Ensure the lock file captures every dependency declared in pyproject.toml."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement
from scripts.sync_dev_dependencies import align_quoted_tool_pins, parse_env_file
from scripts.sync_dev_dependencies import main as sync_dependencies
from scripts.sync_manifest_compiler import compile_manifest

# Install step quoted from Trend_Model_Project pages-wasm-demo.yml at 73120b9a594e.
_REPORTED_WASM_INSTALL = 'python -m pip install "pytest==9.1.1" "pytest-xdist==3.8.0"'

_OPERATORS = ("==", ">=", "<=", "~=", "!=", ">", "<", "===")


def _split_spec(raw: str) -> str:
    entry = raw.strip().strip(",").strip('"')
    for operator in _OPERATORS:
        if operator in entry:
            name, _ = entry.split(operator, 1)
            return name.strip().split("[")[0]
    return entry.strip().split("[")[0]


def _should_include_requirement(raw: str) -> bool:
    requirement = Requirement(raw.strip().rstrip(","))
    if requirement.marker is None:
        return True
    return requirement.marker.evaluate(default_environment())


def _supported_python_environments(pyproject: dict[str, object]) -> list[dict[str, str]]:
    project = pyproject.get("project", {})
    classifiers = project.get("classifiers", [])
    supported_versions = []
    for classifier in classifiers:
        if not isinstance(classifier, str):
            continue
        prefix = "Programming Language :: Python :: "
        if not classifier.startswith(prefix):
            continue
        version = classifier.removeprefix(prefix).strip()
        if version and version[0].isdigit() and "." in version:
            supported_versions.append(version)

    environments = []
    for version in sorted(set(supported_versions)):
        environment = default_environment()
        environment["python_version"] = version
        environment["python_full_version"] = f"{version}.0"
        environments.append(environment)
    return environments


def _lock_requires_requirement(raw: str, *, supported_environments: list[dict[str, str]]) -> bool:
    requirement = Requirement(raw.strip().rstrip(","))
    if requirement.marker is None:
        return True
    if not supported_environments:
        return requirement.marker.evaluate(default_environment())
    return all(requirement.marker.evaluate(environment) for environment in supported_environments)


def _load_lock_versions(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("--"):
            continue
        if "==" not in stripped:
            continue
        name, version = stripped.split("==", 1)
        versions[name.lower()] = version
    return versions


def test_all_pyproject_dependencies_are_in_lock() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    supported_environments = _supported_python_environments(pyproject)

    declared = set()
    for entry in project.get("dependencies", []):
        if _lock_requires_requirement(entry, supported_environments=supported_environments):
            declared.add(_split_spec(entry).lower())

    for group in project.get("optional-dependencies", {}).values():
        for entry in group:
            if _lock_requires_requirement(entry, supported_environments=supported_environments):
                declared.add(_split_spec(entry).lower())

    lock_versions = _load_lock_versions(Path("requirements.lock"))

    missing = []
    for dependency in sorted(declared):
        normalised = dependency.replace("-", "_")
        if dependency not in lock_versions and normalised not in lock_versions:
            missing.append(dependency)

    assert not missing, "requirements.lock is missing pinned versions for: " + ", ".join(missing)


def test_source_pytest_lock_matches_development_pin() -> None:
    """Installing the source lock and dev extra must select the same pytest."""
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dev = project["project"]["optional-dependencies"]["dev"]
    pytest_pins = [Requirement(entry) for entry in dev if Requirement(entry).name == "pytest"]
    assert len(pytest_pins) == 1
    lock_versions = _load_lock_versions(root / "requirements.lock")
    assert (
        str(pytest_pins[0].specifier) == f"=={lock_versions['pytest']}"
    ), "requirements.lock and the development dependency select different pytest versions"


def test_consumer_pytest_sync_matches_source_development_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the dependency producer, independently of consumer-owned workflows."""
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dev = project["project"]["optional-dependencies"]["dev"]
    pytest_pins = [Requirement(entry) for entry in dev if Requirement(entry).name == "pytest"]
    assert len(pytest_pins) == 1
    pins = parse_env_file(root / ".github/workflows/autofix-versions.env")
    assert str(pytest_pins[0].specifier) == f"=={pins['PYTEST_VERSION']}"

    consumer = tmp_path / "pyproject.toml"
    consumer.write_text(
        '[project]\nname = "consumer"\nversion = "1.0"\n'
        '[project.optional-dependencies]\ndev = ["pytest==9.1.1"]\n',
        encoding="utf-8",
    )
    lockfile = tmp_path / "requirements.lock"
    lockfile.write_text("pytest==9.1.1\npytest-xdist==3.8.0\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (consumer, lockfile)}
    monkeypatch.chdir(tmp_path)
    arguments = [
        "--pin-file",
        str(root / ".github/workflows/autofix-versions.env"),
        "--pyproject",
        str(consumer),
    ]
    assert sync_dependencies(["--check", *arguments]) == 1
    assert {path: path.read_bytes() for path in before} == before

    assert sync_dependencies(["--apply", *arguments]) == 0
    generated = tomllib.loads(consumer.read_text(encoding="utf-8"))
    assert generated["project"]["optional-dependencies"]["dev"] == [str(pytest_pins[0])]
    assert _load_lock_versions(lockfile)["pytest"] == next(iter(pytest_pins[0].specifier)).version
    assert sync_dependencies(["--check", *arguments]) == 0
    after = {path: path.read_bytes() for path in before}
    assert sync_dependencies(["--apply", *arguments]) == 0
    assert {path: path.read_bytes() for path in before} == after


def _quoted_package_version(text: str, package: str) -> str:
    match = re.search(
        rf"""["']{re.escape(package)}(?![-.\w])(?:\[[^\]]+\])?==([^"']+)["']""",
        text,
    )
    assert match is not None, package
    return match.group(1)


def test_reported_wasm_install_aligns_to_development_pytest_pin() -> None:
    """The reported WASM install must be rewritten to the pyproject dev pin.

    Maint 68 does not generate pages-wasm-demo.yml. This renders the install
    line from the canonical pins and reads the pytest version back out.
    """
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dev = project["project"]["optional-dependencies"]["dev"]
    pytest_pins = [Requirement(entry) for entry in dev if Requirement(entry).name == "pytest"]
    assert len(pytest_pins) == 1
    development_version = next(iter(pytest_pins[0].specifier)).version
    pins = parse_env_file(root / ".github/workflows/autofix-versions.env")

    assert _quoted_package_version(_REPORTED_WASM_INSTALL, "pytest") != development_version

    aligned, changes = align_quoted_tool_pins(_REPORTED_WASM_INSTALL, pins)
    assert changes == [f"pytest: ==9.1.1 -> =={development_version}"]
    assert _quoted_package_version(aligned, "pytest") == development_version
    assert _quoted_package_version(aligned, "pytest") == pins["PYTEST_VERSION"]
    assert _quoted_package_version(aligned, "pytest-xdist") == pins["PYTEST_XDIST_VERSION"]
    assert "pytest==9.1.1" not in aligned
    assert aligned == (
        "python -m pip install "
        f'"pytest=={development_version}" "pytest-xdist=={pins["PYTEST_XDIST_VERSION"]}"'
    )

    again, more_changes = align_quoted_tool_pins(aligned, pins)
    assert again == aligned
    assert more_changes == []


def test_template_sync_does_not_generate_consumer_wasm_workflow() -> None:
    """Issue #4427's workflow pin cannot be repaired by regenerating Maint 68."""
    root = Path(__file__).resolve().parents[1]
    plan = compile_manifest(root / ".github/sync-manifest.yml").to_plan()
    targets = {entry["target"] for entry in plan["entries"]}
    targets.update(entry["target"] for entry in plan["removals"])
    assert "pyproject.toml" not in targets
    assert ".github/workflows/pages-wasm-demo.yml" not in targets


def test_maint68_delivered_script_resolves_reported_wasm_pytest_mismatch(tmp_path: Path) -> None:
    """Simulate the Maint 68 copy, then read the candidate install pin.

    The live workflow dispatch stays with a maintainer. This copies the compiled
    plan entry the way maint-68-sync-consumer-repos.yml does (``shutil.copy2`` of
    ``resolved_source`` onto the consumer target) and runs that delivered file
    with Maint 52's ``--apply --pre-commit --resolve-locks`` arguments. The
    review split is the input: the development dependency is already current and
    ``pages-wasm-demo.yml`` still installs pytest 9.1.1.
    """
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dev = project["project"]["optional-dependencies"]["dev"]
    pytest_pins = [Requirement(entry) for entry in dev if Requirement(entry).name == "pytest"]
    assert len(pytest_pins) == 1
    development_version = next(iter(pytest_pins[0].specifier)).version
    pins = parse_env_file(root / ".github/workflows/autofix-versions.env")
    assert pins["PYTEST_VERSION"] == development_version
    xdist_version = pins["PYTEST_XDIST_VERSION"]

    compiled = compile_manifest(root / ".github/sync-manifest.yml", repo_root=root)
    matches = [
        entry
        for entry in compiled.section("scripts")
        if entry.source == "scripts/sync_dev_dependencies.py"
    ]
    assert len(matches) == 1
    entry = matches[0]
    assert entry.target == "scripts/sync_dev_dependencies.py"
    assert entry.source_tree == "root"
    assert entry.template_sync == "exact"
    assert entry.delivery == "copy"
    assert "stranske/Trend_Model_Project" not in {rule.repo for rule in entry.skip_repos}
    delivered_source = root / entry.resolved_source
    template_copy = root / "templates/consumer-repo" / entry.source
    assert delivered_source.is_file()
    assert template_copy.read_bytes() == delivered_source.read_bytes()

    consumer = tmp_path / "consumer"
    workflow_dir = consumer / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    shutil.copy2(
        root / ".github/workflows/autofix-versions.env", workflow_dir / "autofix-versions.env"
    )
    pyproject_before = (
        '[project]\nname = "consumer"\nversion = "1.0"\n'
        "[project.optional-dependencies]\n"
        f'dev = ["pytest=={development_version}", "pytest-xdist=={xdist_version}"]\n'
    )
    pyproject_path = consumer / "pyproject.toml"
    pyproject_path.write_text(pyproject_before, encoding="utf-8")
    contract = (
        "run: pytest -q tests/wasm/test_build_wasm_site.py "
        "tests/wasm/test_demo_no_external_cdn.py\n"
    )
    reported = (
        "      - name: Install focused test tools\n"
        "        run: python -m pip install "
        f'"pytest==9.1.1" "pytest-xdist=={xdist_version}"\n'
        "\n"
        "      - name: Verify artifact contract\n"
        f"        {contract}"
    )
    workflow = workflow_dir / "pages-wasm-demo.yml"
    workflow.write_text(reported, encoding="utf-8")

    # Same placement as Detect-and-apply: workflows/<resolved_source> -> consumer/<target>.
    delivered = consumer / entry.target
    delivered.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(delivered_source, delivered)
    assert delivered.read_bytes() == delivered_source.read_bytes()

    completed = subprocess.run(
        [sys.executable, str(delivered), "--apply", "--pre-commit", "--resolve-locks"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert f"pages-wasm-demo.yml:pytest: ==9.1.1 -> =={development_version}" in completed.stdout

    rendered = workflow.read_text(encoding="utf-8")
    assert _quoted_package_version(rendered, "pytest") == development_version
    assert _quoted_package_version(rendered, "pytest") == pins["PYTEST_VERSION"]
    assert _quoted_package_version(rendered, "pytest-xdist") == xdist_version
    assert "pytest==9.1.1" not in rendered
    assert contract in rendered
    assert pyproject_path.read_text(encoding="utf-8") == pyproject_before

    again = subprocess.run(
        [sys.executable, str(delivered), "--check", "--pre-commit"],
        cwd=consumer,
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.returncode == 0, again.stderr
    assert workflow.read_text(encoding="utf-8") == rendered
