"""Tests for relocatable Closer Core distribution packaging."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
PORTABLE_ROOT = ROOT

sys.path.insert(0, str(SCRIPTS))
import closer_core_package as core_pkg  # noqa: E402


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


def test_decoy_api_client_not_used(source_commit: str) -> None:
    descriptor = core_pkg.build_public_descriptor(ROOT, source_commit=source_commit)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "pkg"
        decoy = Path(tmp) / "decoy" / "scripts"
        decoy.mkdir(parents=True)
        (decoy / "api_client.py").write_text("GITHUB_API = 'EVIL'\n")
        core_pkg.materialize_package_tree(ROOT, root, descriptor)
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{decoy}{os.pathsep}{root}"
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys; sys.path.insert(0, {str(decoy)!r}); import api_client; print(api_client.GITHUB_API)",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert "EVIL" in probe.stdout
        proc2 = subprocess.run(
            [sys.executable, "-c", "import api_client; print(api_client.GITHUB_API)"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": str(root),
                "CLOSER_CORE_PACKAGE_ROOT": str(root),
            },
            cwd=str(root / "scripts"),
        )
        assert "EVIL" not in proc2.stdout
        assert proc2.returncode == 0


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
        core_pkg.main(["verify", str(root)])
