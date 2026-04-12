"""Ensure the lock file captures every dependency declared in pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

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
