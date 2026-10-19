"""Tests for relocatable Closer Core distribution packaging."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from scripts import closer_core_package as core_pkg

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
PORTABLE_ROOT = ROOT


@pytest.fixture()
def source_commit() -> str:
    return "c" * 40


def test_package_digest_stable(source_commit: str) -> None:
    d1 = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    d2 = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    assert d1["package_digest"] == d2["package_digest"]


def test_schema_change_moves_digest(source_commit: str) -> None:
    base = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    mutated = json.loads(json.dumps(base))
    mutated["files"]["fixtures/closer-operation/v1/operation.schema.json"] = "d" * 64
    mutated["package_digest"] = core_pkg.compute_package_digest(
        source_commit=source_commit,
        files=mutated["files"],
        dependencies=core_pkg.RUNTIME_DEPENDENCIES,
    )
    assert mutated["package_digest"] != base["package_digest"]


def test_dependency_change_moves_digest(source_commit: str) -> None:
    base = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    deps = dict(core_pkg.RUNTIME_DEPENDENCIES)
    deps["requests"] = "0.0.0"
    digest = core_pkg.compute_package_digest(
        source_commit=source_commit,
        files=base["files"],
        dependencies=deps,
    )
    assert digest != base["package_digest"]


def test_relocate_and_run_validate(source_commit: str) -> None:
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    with tempfile.TemporaryDirectory() as tmp:
        pkg_a = Path(tmp) / "a"
        core_pkg.materialize_package_tree(ROOT, pkg_a, descriptor)
        pkg_b = Path(tmp) / "b"
        shutil.move(str(pkg_a), str(pkg_b))
        record = ROOT / "fixtures/closer-operation/v1/minimal-operation.json"
        proc = core_pkg.run_sealed_entrypoint(
            pkg_b,
            descriptor,
            ["validate", str(record)],
            python=sys.executable,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout


def test_tampered_tree_refused_before_run(source_commit: str) -> None:
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "pkg"
        core_pkg.materialize_package_tree(ROOT, root, descriptor)
        target = root / "scripts/closer_runtime.py"
        target.write_text(target.read_text() + "\n# tamper\n")
        problems = core_pkg.verify_installed_tree(root, descriptor)
        assert problems
        with pytest.raises(core_pkg.CorePackageError):
            core_pkg.run_sealed_entrypoint(
                root, descriptor, ["validate", "x"], python=sys.executable
            )


def test_decoy_api_client_not_used(source_commit, monkeypatch, tmp_path):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    root, decoy = tmp_path / "pkg", tmp_path / "decoy"
    decoy.mkdir()
    marker = tmp_path / "unsealed-import"
    (decoy / "api_client.py").write_text("GITHUB_API = 'EVIL'\n")
    (decoy / "sitecustomize.py").write_text(
        "from pathlib import Path\nimport api_client\n"
        + f"Path({str(marker)!r}).write_text(api_client.GITHUB_API)\n"
    )
    core_pkg.materialize_package_tree(ROOT, root, descriptor)
    monkeypatch.setenv("PYTHONPATH", str(decoy))
    result = core_pkg.run_sealed_entrypoint(
        root,
        descriptor,
        ["validate", str(ROOT / "fixtures/closer-operation/v1/minimal-operation.json")],
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "inherited path executed an unsealed api_client"


def test_draft_portable_snapshot_integration(source_commit: str) -> None:
    """Draft evidence only: hash a copied portable tree, not production qualification."""
    snapshot = Path(tempfile.mkdtemp(prefix="closer-core-draft-"))
    try:
        for rel in core_pkg.CORE_OWNED_PATHS:
            src = PORTABLE_ROOT / rel
            if not src.is_file():
                pytest.skip(f"missing portable draft file {rel}")
            dest = snapshot / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        descriptor = core_pkg.build_public_descriptor(snapshot, source_commit=source_commit)
        assert not core_pkg.validate_public_descriptor(descriptor)
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


@pytest.mark.parametrize(
    "name,version",
    [
        ("jsonschema", "4.21.0"),
        ("PyYAML", "6.0.2"),
        ("requests", "2.0.0"),
        ("jsonschema", "unknown"),
    ],
)
def test_dependency_probe_rejects_unsupported_versions(monkeypatch, name, version):
    versions = {"jsonschema": "4.22.0", "PyYAML": "6.0.3", "requests": "2.34.2"}
    versions[name] = version
    monkeypatch.setattr(
        core_pkg.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(versions), ""),
    )
    with pytest.raises(core_pkg.CorePackageError, match="dependency unsupported"):
        core_pkg.verify_runtime_dependencies(sys.executable)


@pytest.mark.parametrize("version", ["4.22.0", "4.26.0", "5.0.0"])
def test_dependency_probe_accepts_declared_minimum_and_newer(monkeypatch, version):
    versions = {"jsonschema": version, "PyYAML": "6.0.3", "requests": "2.34.2"}
    monkeypatch.setattr(
        core_pkg.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(versions), ""),
    )
    assert core_pkg.verify_runtime_dependencies(sys.executable) == versions


@pytest.mark.parametrize("entry", ["/tmp/evil.py", "../other.py", "scripts/api_client.py"])
def test_descriptor_cannot_redirect_entrypoint(tmp_path, source_commit, entry):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    core_pkg.materialize_package_tree(ROOT, tmp_path / "pkg", descriptor)
    descriptor["entrypoints"]["runtime"] = entry
    with pytest.raises(core_pkg.CorePackageError, match="entrypoint"):
        core_pkg.run_sealed_entrypoint(tmp_path / "pkg", descriptor, [])


def test_materialization_preserves_existing_destination(tmp_path, source_commit):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    destination = tmp_path / "important"
    destination.mkdir()
    (destination / "existing").write_text("retain")
    with pytest.raises(core_pkg.CorePackageError, match="destination exists"):
        core_pkg.materialize_package_tree(ROOT, destination, descriptor)
    assert (destination / "existing").read_text() == "retain"


def test_cli_verify_checks_declared_dependencies(tmp_path, monkeypatch, source_commit):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    root = tmp_path / "pkg"
    core_pkg.materialize_package_tree(ROOT, root, descriptor)

    def unavailable(*a):
        raise core_pkg.CorePackageError("runtime dependency unsupported")

    monkeypatch.setattr(core_pkg, "verify_runtime_dependencies", unavailable)
    with pytest.raises(core_pkg.CorePackageError, match="dependency unsupported"):
        core_pkg.main(["verify", str(root), "--expected-digest", descriptor["package_digest"]])


@pytest.mark.parametrize(
    "extra", ["scripts/__init__.py", "scripts/foreign.py", "scripts/__pycache__/foreign.pyc"]
)
def test_sealed_execution_rejects_undeclared_files(tmp_path, source_commit, extra):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    root = tmp_path / "pkg"
    core_pkg.materialize_package_tree(ROOT, root, descriptor)
    unowned = root / extra
    unowned.parent.mkdir(parents=True, exist_ok=True)
    unowned.write_text("raise RuntimeError('unsealed code')")
    with pytest.raises(core_pkg.CorePackageError, match="closed package files"):
        core_pkg.run_sealed_entrypoint(root, descriptor, ["validate", "unused"])


@pytest.mark.parametrize(
    "producer_kind", ["python", "selftest-reusable-ci", "maint-62-integration-consumer"]
)
def test_packaged_producer_keeps_trusted_workflow_matrix_definitions(
    tmp_path, monkeypatch, source_commit, producer_kind
):
    from tests import test_check_checks_reported as contract

    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    root = tmp_path / "pkg"
    core_pkg.materialize_package_tree(ROOT, root, descriptor)
    monkeypatch.setattr(
        contract.reporter, "__file__", str(root / "scripts/check_checks_reported.py")
    )
    if producer_kind == "python":
        bound = contract.bind_producer(contract.python_producer_fixture())
    else:
        fixture = contract.scenario_fixture(path=f".github/workflows/{producer_kind}.yml")
        bound = contract.bind_scenario_fixture(fixture)
    assert isinstance(bound["strategy"]["matrix"], dict)
    assert not core_pkg.verify_installed_tree(root, descriptor)


def test_cli_verifier_rejects_recomputed_attacker_descriptor(tmp_path, source_commit):
    original = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    root = tmp_path / "pkg"
    core_pkg.materialize_package_tree(ROOT, root, original)
    file = root / "scripts/closer_runtime.py"
    file.write_text(file.read_text() + "\n# modified after trusted publication\n")
    forged = json.loads(json.dumps(original))
    forged["files"]["scripts/closer_runtime.py"] = core_pkg.sha256_file(file)
    forged["package_digest"] = core_pkg.compute_package_digest(
        source_commit=source_commit, files=forged["files"], dependencies=forged["dependencies"]
    )
    (root / "closer-core-package.json").write_text(json.dumps(forged))
    assert core_pkg.verify_installed_tree(root, forged) == []
    assert (
        core_pkg.main(["verify", str(root), "--expected-digest", original["package_digest"]]) == 2
    )


def test_dependency_probe_and_entrypoint_use_same_sealed_environment(
    tmp_path, source_commit, monkeypatch
):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    root = tmp_path / "pkg"
    core_pkg.materialize_package_tree(ROOT, root, descriptor)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        data = (
            json.dumps({"jsonschema": "4.22.0", "PyYAML": "6.0.3", "requests": "2.34.2"})
            if "-c" in command
            else "valid"
        )
        return subprocess.CompletedProcess(command, 0, data, "")

    monkeypatch.setattr(core_pkg.subprocess, "run", run)
    monkeypatch.setenv("PYTHONPATH", "/untrusted/inherited")
    core_pkg.run_sealed_entrypoint(
        root, descriptor, ["--help"], extra_env={"PYTHONUSERBASE": str(tmp_path / "userbase")}
    )
    assert len(calls) == 2
    for command, kw in calls:
        assert "-B" in command
        assert kw["env"]["PYTHONPATH"] == str(root)
        assert kw["env"]["PYTHONUSERBASE"] == str(tmp_path / "userbase")
        assert kw["cwd"] == root


def test_sealed_entrypoint_resolves_relative_package_root(tmp_path, source_commit, monkeypatch):
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    core_pkg.materialize_package_tree(ROOT, tmp_path / "pkg", descriptor)
    monkeypatch.chdir(tmp_path)
    result = core_pkg.run_sealed_entrypoint(Path("pkg"), descriptor, ["--help"])
    assert result.returncode == 0, result.stderr
