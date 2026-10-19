#!/usr/bin/env python3
"""Portable, relocatable Closer Core package (Workflows-owned).

Builds a closed file set with a public descriptor (no host paths). Host install
bindings are separate and never embedded in the published archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTRACT = "closer-operation/v1"
CORE_PACKAGE_VERSION = "1"
OWNER = "Workflows"
PACKAGE_KIND = "closer-core"
PUBLIC_SCHEMA = 1

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")

# Closed owned file set relative to the Workflows checkout root.
CORE_OWNED_PATHS: tuple[str, ...] = (
    "scripts/closer_runtime.py",
    "scripts/closer_operation_github.py",
    "scripts/check_checks_reported.py",
    "scripts/api_client.py",
    "scripts/reusable_ci_scope.py",
    "fixtures/closer-operation/v1/operation.schema.json",
    ".github/workflows/reusable-10-ci-python.yml",
    ".github/workflows/selftest-reusable-ci.yml",
    ".github/workflows/maint-62-integration-consumer.yml",
)

# Declared third-party runtime deps; each line affects package_digest.
RUNTIME_DEPENDENCIES: dict[str, str] = {
    "jsonschema": ">=4.22.0",
    "PyYAML": "6.0.3",
    "requests": "2.34.2",
}

ENTRYPOINT_RUNTIME = "scripts/closer_runtime.py"


class CorePackageError(RuntimeError):
    """Invalid descriptor, digest mismatch, or seal violation."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _relative_owned_paths(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel in CORE_OWNED_PATHS:
        path = root / rel
        if not path.is_file():
            raise CorePackageError(f"missing owned file: {rel}")
        digests[rel] = sha256_file(path)
    return digests


def compute_package_digest(
    *,
    source_commit: str,
    files: Mapping[str, str],
    dependencies: Mapping[str, str],
) -> str:
    return sha256_json(
        [
            PACKAGE_KIND,
            OWNER,
            CORE_PACKAGE_VERSION,
            CONTRACT,
            source_commit,
            sorted(files.items()),
            sorted(dependencies.items()),
        ]
    )


def build_public_descriptor(
    core_root: Path,
    *,
    source_commit: str,
) -> dict[str, Any]:
    if not _SHA.fullmatch(source_commit):
        raise ValueError("source_commit must be a 40-char lowercase git SHA")
    core_root = core_root.resolve()
    files = _relative_owned_paths(core_root)
    descriptor: dict[str, Any] = {
        "schema_version": PUBLIC_SCHEMA,
        "package_kind": PACKAGE_KIND,
        "owner": OWNER,
        "core_version": CORE_PACKAGE_VERSION,
        "contract": CONTRACT,
        "source_commit": source_commit,
        "files": files,
        "dependencies": dict(RUNTIME_DEPENDENCIES),
        "entrypoints": {"runtime": ENTRYPOINT_RUNTIME},
    }
    descriptor["package_digest"] = compute_package_digest(
        source_commit=source_commit,
        files=files,
        dependencies=RUNTIME_DEPENDENCIES,
    )
    return descriptor


def validate_public_descriptor(descriptor: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if descriptor.get("schema_version") != PUBLIC_SCHEMA:
        problems.append("unsupported public schema_version")
    if descriptor.get("package_kind") != PACKAGE_KIND:
        problems.append("package_kind mismatch")
    if descriptor.get("owner") != OWNER:
        problems.append("owner must be Workflows")
    if descriptor.get("contract") != CONTRACT:
        problems.append("contract mismatch")
    if descriptor.get("core_version") != CORE_PACKAGE_VERSION:
        problems.append("unsupported core_version")
    if descriptor.get("entrypoints") != {"runtime": ENTRYPOINT_RUNTIME}:
        problems.append("entrypoints differ from the closed owned runtime entrypoint")
    if not _SHA.fullmatch(str(descriptor.get("source_commit", ""))):
        problems.append("invalid source_commit")
    files = descriptor.get("files")
    if not isinstance(files, dict) or set(files) != set(CORE_OWNED_PATHS):
        problems.append("files set does not match the closed owned file list")
    elif any(not _DIGEST.fullmatch(str(v)) for v in files.values()):
        problems.append("invalid file digest in files")
    deps = descriptor.get("dependencies")
    if deps != RUNTIME_DEPENDENCIES:
        problems.append("dependencies differ from the declared runtime set")
    digest = descriptor.get("package_digest")
    if not _DIGEST.fullmatch(str(digest or "")):
        problems.append("invalid package_digest")
    elif not problems:
        expected = compute_package_digest(
            source_commit=str(descriptor["source_commit"]),
            files=files,
            dependencies=RUNTIME_DEPENDENCIES,
        )
        if digest != expected:
            problems.append("package_digest does not match descriptor contents")
    return problems


def materialize_package_tree(
    core_root: Path,
    dest: Path,
    descriptor: Mapping[str, Any],
) -> Path:
    problems = validate_public_descriptor(descriptor)
    if problems:
        raise CorePackageError("; ".join(problems))
    dest = dest.resolve()
    if dest.exists():
        raise CorePackageError("destination exists; use a fresh immutable package directory")
    dest.mkdir(parents=True)
    for rel in CORE_OWNED_PATHS:
        src = core_root / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        if sha256_file(target) != descriptor["files"][rel]:
            raise CorePackageError(f"materialized digest mismatch: {rel}")
    public_path = dest / "closer-core-package.json"
    public_path.write_text(json.dumps(dict(descriptor), indent=2, sort_keys=True) + "\n")
    return dest


def verify_installed_tree(package_root: Path, descriptor: Mapping[str, Any]) -> list[str]:
    problems = validate_public_descriptor(descriptor)
    if problems:
        return problems
    package_root = package_root.resolve()
    expected_files = set(CORE_OWNED_PATHS) | {"closer-core-package.json"}
    actual_files = {
        str(path.relative_to(package_root))
        for path in package_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != expected_files:
        problems.append("installed tree differs from closed package files")
    for rel, digest in descriptor["files"].items():
        path = package_root / rel
        try:
            if any(p.is_symlink() for p in (path, *path.parents) if p != package_root.parent):
                problems.append(f"{rel}: package paths must not be symlinks")
                continue
            if sha256_file(path) != digest:
                problems.append(f"{rel}: digest differs from descriptor")
        except OSError:
            problems.append(f"{rel}: unreadable")
    on_disk = package_root / "closer-core-package.json"
    if on_disk.is_file():
        try:
            loaded = json.loads(on_disk.read_text())
            problems.extend(validate_public_descriptor(loaded))
            if loaded != descriptor:
                problems.append("on-disk descriptor differs from the selected descriptor")
        except json.JSONDecodeError:
            problems.append("closer-core-package.json is not valid JSON")
    else:
        problems.append("closer-core-package.json missing")
    return problems


def write_host_binding(
    path: Path,
    *,
    package_root: Path,
    descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    """Host-local install record; never ship inside the public archive."""
    binding = {
        "kind": "closer-core-host-binding",
        "package_root": str(package_root.resolve()),
        "package_digest": descriptor["package_digest"],
        "descriptor_relpath": "closer-core-package.json",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    return binding


def _dependency_probe_code() -> str:
    lines = ["import importlib", "from importlib.metadata import version", "out = {}"]
    for name in RUNTIME_DEPENDENCIES:
        mod = "yaml" if name.lower() == "pyyaml" else name
        lines.append(f"mod = importlib.import_module('{mod}')")
        lines.append(f"out['{name}'] = version('{name}')")
    lines.append("import json; print(json.dumps(out, sort_keys=True))")
    return "\n".join(lines)


def verify_runtime_dependencies(
    python: str | Path, *, env: Mapping[str, str] | None = None, cwd: Path | None = None
) -> dict[str, str]:
    proc = subprocess.run(
        [str(python), "-B", "-c", _dependency_probe_code()],
        capture_output=True,
        text=True,
        env=dict(env) if env is not None else None,
        cwd=cwd,
        check=False,
    )
    if proc.returncode != 0:
        raise CorePackageError(
            f"runtime dependency probe failed: {proc.stderr.strip() or proc.stdout}"
        )
    try:
        observed = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise CorePackageError("runtime dependency probe returned invalid versions") from exc
    for name, required in RUNTIME_DEPENDENCIES.items():
        actual = observed.get(name) if isinstance(observed, dict) else None
        if required.startswith(">="):
            valid = isinstance(actual, str) and re.fullmatch(r"\d+\.\d+\.\d+", actual)
            compatible = bool(valid) and tuple(map(int, actual.split("."))) >= tuple(
                map(int, required[2:].split("."))
            )
        else:
            compatible = actual == required
        if not compatible:
            raise CorePackageError(
                f"runtime dependency unsupported: {name} {actual}; requires {required}"
            )
    return observed


def run_sealed_entrypoint(
    package_root: Path,
    descriptor: Mapping[str, Any],
    argv: Sequence[str],
    *,
    python: str | Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a Core entrypoint with PYTHONPATH confined to the package root."""
    package_root = package_root.resolve()
    problems = verify_installed_tree(package_root, descriptor)
    if problems:
        raise CorePackageError("; ".join(problems))
    python = str(python or sys.executable)
    entry = descriptor["entrypoints"]["runtime"]
    script = package_root / entry
    if not script.is_file():
        raise CorePackageError(f"entrypoint missing: {entry}")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["CLOSER_CORE_PACKAGE_ROOT"] = str(package_root.resolve())
    env["CLOSER_CORE_PACKAGE_DIGEST"] = str(descriptor["package_digest"])
    # Package root must precede any inherited path so generic scripts/* caches cannot win.
    env["PYTHONPATH"] = str(package_root.resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra_env:
        if any(
            k
            in {
                "PYTHONPATH",
                "PYTHONHOME",
                "CLOSER_CORE_PACKAGE_ROOT",
                "CLOSER_CORE_PACKAGE_DIGEST",
            }
            for k in extra_env
        ):
            raise CorePackageError("extra environment cannot override sealed package bindings")
        env.update(extra_env)
    verify_runtime_dependencies(python, env=env, cwd=package_root)
    return subprocess.run(
        [python, "-B", str(script), *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=package_root,
        check=False,
    )


def _selftest() -> int:
    failures = 0
    core_root = Path(__file__).resolve().parents[1]
    commit = "0" * 40
    d1 = build_public_descriptor(core_root, source_commit=commit)
    d2 = build_public_descriptor(core_root, source_commit=commit)
    if d1["package_digest"] != d2["package_digest"]:
        print("FAIL: package digest not stable")
        failures += 1
    mutated = dict(d1)
    mutated["dependencies"] = dict(RUNTIME_DEPENDENCIES)
    mutated["dependencies"]["jsonschema"] = ">=99.0.0"
    mutated["package_digest"] = compute_package_digest(
        source_commit=commit,
        files=d1["files"],
        dependencies=mutated["dependencies"],
    )
    if mutated["package_digest"] == d1["package_digest"]:
        print("FAIL: dependency change did not move digest")
        failures += 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "pkg"
        materialize_package_tree(core_root, root, d1)
        if verify_installed_tree(root, d1):
            print("FAIL: verify_installed_tree after materialize")
            failures += 1
        bad = json.loads(json.dumps(d1))
        bad["files"]["scripts/closer_runtime.py"] = "f" * 64
        if not verify_installed_tree(root, bad):
            print("FAIL: expected tampered descriptor to fail verify")
            failures += 1
    print(f"selftest: {failures} failures")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="write a relocatable Core package directory")
    b.add_argument("--core-root", type=Path, default=Path(__file__).resolve().parents[1])
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--source-commit", required=True)
    b.set_defaults(func=_cmd_build)

    v = sub.add_parser("verify", help="verify an installed package tree")
    v.add_argument("package_root", type=Path)
    v.add_argument("--expected-digest", required=True)
    v.set_defaults(func=_cmd_verify)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


def _cmd_build(args: argparse.Namespace) -> int:
    descriptor = build_public_descriptor(args.core_root, source_commit=args.source_commit)
    materialize_package_tree(args.core_root, args.out, descriptor)
    print(json.dumps({"package_digest": descriptor["package_digest"], "out": str(args.out)}))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    public = args.package_root / "closer-core-package.json"
    descriptor = json.loads(public.read_text())
    problems = verify_installed_tree(args.package_root, descriptor)
    if descriptor.get("package_digest") != args.expected_digest:
        problems.append("package_digest differs from trusted host digest")
    if problems:
        print(json.dumps({"ok": False, "problems": problems}))
        return 2
    verify_runtime_dependencies(sys.executable)
    print(json.dumps({"ok": True, "package_digest": descriptor["package_digest"]}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(_selftest())
    raise SystemExit(main())
