#!/usr/bin/env python3
"""Opt-in execution check for deliberate-break acceptance criteria."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from importlib import import_module, metadata
from io import BytesIO
from pathlib import Path

VERDICT_PASS = "PASS"
VERDICT_HOLLOW = "FAIL_HOLLOW"
VERDICT_BROKEN = "FAIL_BROKEN"
VERDICT_SKIPPED = "SKIPPED"

MARKER_RE = re.compile(
    r"(?:<!--\s*)?deliberate-break:\s*(?P<body>.*?)(?:\s*-->)?$",
    re.IGNORECASE,
)
SECTION_HEADER_RE = re.compile(r"^#{2,6}\s+(.+?)\s*$", re.MULTILINE)
ASSERTION_DIFF_RE = re.compile(
    r"\b(assert|expect\(|pytest\.raises\(|assert\.)\b",
)
DEFAULT_TIMEOUT_SECONDS = 120
# Compatible installed versions may exceed this Workflows-owned bootstrap floor;
# automatic repair remains reproducibly pinned by PYTEST_RUNTIME_DEPENDENCIES.
PYYAML_VERSION = "6.0.3"
PYTEST_RUNTIME_DEPENDENCIES = (f"pyyaml=={PYYAML_VERSION}",)
PYYAML_PROBE_SENTINEL = "__gate_pyyaml_import_ok__"
PYYAML_PROBE_CODE = f"import yaml; print({PYYAML_PROBE_SENTINEL!r})"


@dataclass(frozen=True)
class DeliberateBreakSpec:
    test_id: str
    test_file: str
    break_file: str
    command: tuple[str, ...]


class RuntimeDependencyError(Exception):
    """Wrap failures raised specifically while repairing runtime dependencies."""

    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error = error


class CommandUnavailableError(Exception):
    """Wrap OS failures raised while launching the deliberate-break command."""

    def __init__(self, error: OSError) -> None:
        super().__init__(str(error))
        self.error = error


def _json_result(verdict: str, **fields: object) -> dict[str, object]:
    return {"verdict": verdict, **fields}


def _subprocess_output_text(value: str | bytes | None) -> str | None:
    """Normalize captured subprocess output for JSON result payloads."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _write_github_output(**fields: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in fields.items():
            handle.write(f"{key}={value}\n")


def _acceptance_criteria(markdown: str) -> str:
    headers = list(SECTION_HEADER_RE.finditer(markdown))
    for index, match in enumerate(headers):
        if match.group(1).strip().lower() != "acceptance criteria":
            continue
        start = match.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(markdown)
        return markdown[start:end].strip()
    return markdown


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in shlex.split(text):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key.strip().replace("_", "-").lower()] = value.strip()
    return values


def _explicit_marker(section: str) -> DeliberateBreakSpec | None:
    for line in section.splitlines():
        match = MARKER_RE.search(line.strip())
        if not match:
            continue
        values = _parse_key_values(match.group("body"))
        test_id = values.get("test") or values.get("test-id")
        test_file = values.get("test-file") or values.get("file")
        break_file = values.get("break-file") or values.get("revert-file")
        command_text = values.get("command")
        if not test_id or not test_file or not break_file:
            raise ValueError("deliberate-break marker requires test, test-file, and break-file")
        command = tuple(shlex.split(command_text)) if command_text else _pytest_command(test_id)
        return DeliberateBreakSpec(test_id, test_file, break_file, command)
    return None


def _fallback_marker(section: str, markdown: str = "") -> DeliberateBreakSpec | None:
    named_line = next(
        (line for line in section.splitlines() if "named test:" in line.lower()),
        "",
    )
    break_line = next(
        (
            line
            for line in section.splitlines()
            if "deliberate-break" in line.lower() or "deliberate break" in line.lower()
        ),
        "",
    )
    if not named_line or not break_line:
        return None

    test_file_match = re.search(r"`([^`]*(?:test|tests)[^`]*\.py)`", named_line)
    test_name_match = (
        re.search(r"\btest\s+`([^`]+)`", named_line)
        or re.search(r"\bwith\s+`([^`]+)`", named_line)
        or re.search(r"\bwith\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", named_line)
    )
    break_file = _infer_break_file(break_line, named_line, markdown)
    if not test_file_match or not test_name_match or not break_file:
        return None

    test_file = test_file_match.group(1)
    test_id = f"{test_file}::{test_name_match.group(1)}"
    return DeliberateBreakSpec(test_id, test_file, break_file, _pytest_command(test_id))


def _infer_break_file(break_line: str, named_line: str, markdown: str) -> str | None:
    """Pick a revert target from acceptance wording, skipping label-like backticks."""

    def _candidate_paths(text: str) -> list[str]:
        paths: list[str] = []
        for path in re.findall(r"`([^`]+)`", text):
            normalized = path.strip().rstrip(":")
            if not normalized:
                continue
            if re.fullmatch(r"[A-Za-z][\w-]*:\s*.+", normalized):
                continue
            if re.search(r"\s", normalized):
                continue
            path_only = normalized.split(":", 1)[0]
            if "/" in path_only or path_only.endswith((".py", ".yml", ".yaml", ".js")):
                paths.append(path_only)
        return paths

    ordered_paths: list[str] = []
    for text in (break_line, named_line, markdown):
        ordered_paths.extend(_candidate_paths(text))

    workflow_paths = [
        path
        for path in ordered_paths
        if ".github/workflows/" in path or path.endswith((".yml", ".yaml"))
    ]
    if workflow_paths:
        return workflow_paths[0]

    return ordered_paths[0] if ordered_paths else None


def parse_deliberate_break_spec(markdown: str) -> DeliberateBreakSpec | None:
    section = _acceptance_criteria(markdown)
    return _explicit_marker(section) or _fallback_marker(section, markdown)


def _pytest_command(test_id: str) -> tuple[str, ...]:
    return (sys.executable, "-m", "pytest", test_id, "-q")


def _supported_pyyaml_version(installed_version: str | None) -> bool:
    """Return whether an installed PyYAML version satisfies the bootstrap floor."""
    if installed_version is None:
        return False
    installed_match = re.fullmatch(
        r"(\d+(?:\.\d+)*)(?P<pre>(?:a|b|rc)\d+)?" r"(?:\.post\d+)?(?P<dev>\.dev\d+)?(?:\+[\w.-]+)?",
        installed_version,
    )
    floor_match = re.fullmatch(r"(\d+(?:\.\d+)*)", PYYAML_VERSION)
    if installed_match is None or floor_match is None:
        return False
    installed_release = tuple(int(part) for part in installed_match.group(1).split("."))
    floor_release = tuple(int(part) for part in floor_match.group(1).split("."))
    width = max(len(installed_release), len(floor_release))
    normalized_installed = installed_release + (0,) * (width - len(installed_release))
    normalized_floor = floor_release + (0,) * (width - len(floor_release))
    if normalized_installed != normalized_floor:
        return normalized_installed > normalized_floor
    return installed_match.group("pre") is None and installed_match.group("dev") is None


def _ensure_pytest_runtime_deps() -> None:
    """Install lightweight dependencies that Gate test-quality may not preinstall.

    Gate's test-quality job installs only ``pytest``. Deliberate-break may still
    collect tests that import PyYAML (for example via ``sync_manifest_compiler``).
    Installing here avoids editing ``pr-00-gate.yml``, which forces an
    Actions ``action_required`` approval wait on workflow-touching PRs.
    """
    try:
        installed_version = metadata.version("PyYAML")
    except metadata.PackageNotFoundError:
        installed_version = None
    import_error: Exception | None = None
    if _supported_pyyaml_version(installed_version):
        try:
            import_module("yaml")
        except Exception as exc:
            # Any ordinary import-time failure means the installed distribution
            # is unusable. Reinstall the locked wheel before collecting tests.
            import_error = exc
        else:
            return
    if not _supported_pyyaml_version(installed_version) or import_error is not None:
        # Local and custom environments are user-owned; dependency repair may
        # mutate the active interpreter only in GitHub Actions.
        if os.environ.get("GITHUB_ACTIONS") != "true":
            error = ImportError(
                f"PyYAML >= {PYYAML_VERSION} is required; install "
                f"'PyYAML>={PYYAML_VERSION}' in the active environment"
            )
            raise error from import_error
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
        ]
        if import_error is not None:
            command.append("--force-reinstall")
        command.extend(PYTEST_RUNTIME_DEPENDENCIES)
        subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        try:
            import_module("yaml")
        except Exception as retry_error:
            error = ImportError(f"PyYAML remained unimportable after reinstall: {retry_error}")
            raise error from (import_error or retry_error)


def _pyyaml_runtime_needs_repair() -> bool:
    """Return whether the active PyYAML runtime is missing, stale, or unusable."""
    try:
        installed_version = metadata.version("PyYAML")
    except metadata.PackageNotFoundError:
        return True
    if not _supported_pyyaml_version(installed_version):
        return True
    try:
        import_module("yaml")
    except Exception:
        return True
    return False


def _uses_pytest_runtime(command: tuple[str, ...]) -> bool:
    """Return whether a command runs pytest in the active Python environment."""
    if not command:
        return False
    if Path(command[0]).name == "pytest":
        pytest_path = shutil.which(command[0])
        if not pytest_path:
            return False
        launcher = _python_shebang_launcher(Path(pytest_path), shutil.which)
        if launcher is None:
            return False
        launcher_probe = (
            launcher[0],
            *_drop_interactive_python_flags(launcher[1:]),
            "-c",
            PYYAML_PROBE_CODE,
        )
        return Path(launcher[0]).resolve() == Path(
            sys.executable
        ).resolve() and not _python_probe_changes_import_context(launcher_probe)
    executable = shutil.which(command[0]) or command[0]
    probe = _python_module_pytest_probe(command, 0)
    return (
        Path(executable).resolve() == Path(sys.executable).resolve()
        and probe is not None
        and not _python_probe_changes_import_context(probe)
    )


def _run(
    command: tuple[str, ...],
    cwd: Path,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    pythonpath = str(cwd)
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pythonpath
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
    )


UV_RUN_VALUE_OPTIONS = frozenset(
    {
        "-C",
        "-P",
        "-f",
        "-i",
        "-p",
        "-w",
        "--allow-insecure-host",
        "--cache-dir",
        "--color",
        "--config-file",
        "--config-setting",
        "--config-settings-package",
        "--default-index",
        "--directory",
        "--env-file",
        "--exclude-newer",
        "--exclude-newer-package",
        "--extra",
        "--extra-index-url",
        "--find-links",
        "--fork-strategy",
        "--group",
        "--index",
        "--index-strategy",
        "--index-url",
        "--keyring-provider",
        "--link-mode",
        "--no-binary-package",
        "--no-build-isolation-package",
        "--no-build-package",
        "--no-extra",
        "--no-group",
        "--no-sources-package",
        "--only-group",
        "--package",
        "--prerelease",
        "--project",
        "--python",
        "--python-platform",
        "--refresh-package",
        "--reinstall-package",
        "--resolution",
        "--upgrade-package",
        "--with",
        "--with-editable",
        "--with-requirements",
    }
)


def _uv_run_pytest_prefix(command: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return ``uv run`` plus options when its command operand is pytest."""
    if len(command) < 3 or Path(command[0]).name != "uv" or command[1] != "run":
        return None
    index = 2
    while index < len(command) and command[index].startswith("-"):
        option = command[index]
        if option == "--":
            index += 1
            break
        index += 2 if option in UV_RUN_VALUE_OPTIONS else 1
    if index >= len(command) or Path(command[index]).name != "pytest":
        return None
    return command[:index]


def _uv_module_pytest_prefix(command: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return uv options preceding ``-m pytest`` or ``--module pytest``."""
    if len(command) < 4 or Path(command[0]).name != "uv" or command[1] != "run":
        return None
    index = 2
    while index < len(command) and command[index].startswith("-"):
        option = command[index]
        if option in {"-m", "--module"}:
            if index + 1 < len(command) and command[index + 1] == "pytest":
                return command[:index]
            return None
        if option == "--":
            return None
        index += 2 if option in UV_RUN_VALUE_OPTIONS else 1
    return None


PYTHON_VALUE_OPTIONS = frozenset({"-W", "-X", "--check-hash-based-pycs"})
PYTHON_TERMINATING_OPTIONS = frozenset({"-", "--", "-?", "-V", "-VV", "-h", "--help", "--version"})
PYTHON_COMPACT_FLAGS = frozenset("bBdEIiOPqRstuvx")
PYTHON_IMPORT_CONTEXT_FLAGS = frozenset("EIPsS")


def _python_probe_changes_import_context(probe: tuple[str, ...]) -> bool:
    """Return whether a probe uses flags that can change module visibility."""
    for option in probe[1:]:
        if option == "-c":
            break
        if not option.startswith("-") or option.startswith("--"):
            continue
        for character in option[1:]:
            if character in PYTHON_IMPORT_CONTEXT_FLAGS:
                return True
            if character in {"W", "X"}:
                break
    return False


def _drop_interactive_python_flags(options: tuple[str, ...]) -> tuple[str, ...]:
    """Omit lowercase ``-i`` from probe argv.

    Interactive mode forces a prompt after ``-c`` scripts. An import-time
    traceback followed by EOF then exits 0, so PyYAML probe return codes
    become unreliable when ``i`` is preserved from the original launcher.
    Uppercase ``-I`` (isolated mode) is kept.
    """
    cleaned: list[str] = []
    for option in options:
        if option == "-i":
            continue
        if option.startswith("-") and not option.startswith("--") and len(option) > 1:
            body = option[1:]
            kept: list[str] = []
            for position, character in enumerate(body):
                if character == "i":
                    continue
                kept.append(character)
                if character in {"W", "X"}:
                    kept.append(body[position + 1 :])
                    break
            cleaned_body = "".join(kept)
            if not cleaned_body:
                continue
            cleaned.append(f"-{cleaned_body}")
            continue
        cleaned.append(option)
    return tuple(cleaned)


def _python_module_pytest_probe(
    command: tuple[str, ...],
    python_index: int,
) -> tuple[str, ...] | None:
    """Replace Python's program selector only when it is exactly ``-m pytest``."""
    index = python_index + 1
    while index < len(command):
        option = command[index]
        if option == "-m":
            if index + 1 < len(command) and command[index + 1] == "pytest":
                return (
                    *command[: python_index + 1],
                    *_drop_interactive_python_flags(command[python_index + 1 : index]),
                    "-c",
                    PYYAML_PROBE_CODE,
                )
            return None
        if (
            option == "-c"
            or option in PYTHON_TERMINATING_OPTIONS
            or option.startswith("--help-")
            or not option.startswith("-")
        ):
            return None
        if option in PYTHON_VALUE_OPTIONS:
            if option == "--check-hash-based-pycs" and (
                index + 1 >= len(command)
                or command[index + 1] not in {"always", "default", "never"}
            ):
                return None
            index += 2
            continue
        if option.startswith("--"):
            return None
        if option.startswith("-") and not option.startswith("--"):
            compact = option[1:]
            for position, character in enumerate(compact):
                if character in PYTHON_COMPACT_FLAGS:
                    continue
                if character in {"V", "h", "?"}:
                    return None
                if character in {"W", "X"}:
                    index += 2 if position + 1 == len(compact) else 1
                    break
                if character in {"c", "m"}:
                    selector_value = compact[position + 1 :]
                    if character == "m" and (
                        selector_value == "pytest"
                        or (
                            not selector_value
                            and index + 1 < len(command)
                            and command[index + 1] == "pytest"
                        )
                    ):
                        prefix = compact[:position].replace("i", "")
                        preserved = (f"-{prefix}",) if prefix else ()
                        return (
                            *command[: python_index + 1],
                            *_drop_interactive_python_flags(command[python_index + 1 : index]),
                            *preserved,
                            "-c",
                            PYYAML_PROBE_CODE,
                        )
                    return None
                return None
            else:
                index += 1
            continue
        index += 1
    return None


def _uv_python_module_probe(command: tuple[str, ...]) -> tuple[str, ...] | None:
    """Build a probe for ``uv run [options] python [flags] -m pytest``."""
    if len(command) < 4 or Path(command[0]).name != "uv" or command[1] != "run":
        return None
    index = 2
    while index < len(command) and command[index].startswith("-"):
        option = command[index]
        if option in {"-m", "--module"}:
            return None
        if option == "--":
            index += 1
            break
        index += 2 if option in UV_RUN_VALUE_OPTIONS else 1
    if index >= len(command) or not re.fullmatch(
        r"python(?:\d+(?:\.\d+)*)?", Path(command[index]).name
    ):
        return None
    return _python_module_pytest_probe(command, index)


def _python_shebang_launcher(
    executable: Path,
    resolve_name: Callable[[str], str | None],
) -> tuple[str, ...] | None:
    """Return a verified Python shebang launcher, preserving interpreter flags."""
    try:
        shebang = executable.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeError, IndexError):
        return None
    if not shebang.startswith("#!"):
        return None
    try:
        launcher = shlex.split(shebang[2:].strip())
    except ValueError:
        return None
    if not launcher:
        return None
    if Path(launcher[0]).name == "env":
        env_args = launcher[1:]
        if env_args[:1] == ["-S"]:
            env_args = env_args[1:]
        if not env_args or not re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(env_args[0]).name):
            return None
        resolved = resolve_name(env_args[0])
        if not resolved:
            return None
        return (resolved, *env_args[1:])
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(launcher[0]).name):
        return tuple(launcher)
    return None


def _uv_pytest_python_launcher(uv_run_prefix: tuple[str, ...], cwd: Path) -> tuple[str, ...] | None:
    """Resolve the Python shebang launcher used by ``uv run pytest``."""
    located = _run((*uv_run_prefix, "which", "pytest"), cwd)
    if located.returncode != 0 or not located.stdout.strip():
        return None

    def resolve_name(name: str) -> str | None:
        resolved = _run((*uv_run_prefix, "which", name), cwd)
        if resolved.returncode != 0 or not resolved.stdout.strip():
            return None
        return resolved.stdout.strip().splitlines()[-1]

    pytest_path = Path(located.stdout.strip().splitlines()[-1])
    return _python_shebang_launcher(pytest_path, resolve_name)


def _pyyaml_probe_command(command: tuple[str, ...], cwd: Path) -> tuple[str, ...] | None:
    """Return a read-only PyYAML import probe for the pytest launcher's runtime."""
    if uv_prefix := _uv_module_pytest_prefix(command):
        return (*uv_prefix, "python", "-c", PYYAML_PROBE_CODE)
    if probe := _uv_python_module_probe(command):
        return probe
    if command and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(command[0]).name):
        return _python_module_pytest_probe(command, 0)
    if (uv_prefix := _uv_run_pytest_prefix(command)) and (
        launcher := _uv_pytest_python_launcher(uv_prefix, cwd)
    ):
        return (
            launcher[0],
            *_drop_interactive_python_flags(launcher[1:]),
            "-c",
            PYYAML_PROBE_CODE,
        )
    if command and Path(command[0]).name == "pytest":
        pytest_path = shutil.which(command[0])
        if pytest_path and (launcher := _python_shebang_launcher(Path(pytest_path), shutil.which)):
            return (
                launcher[0],
                *_drop_interactive_python_flags(launcher[1:]),
                "-c",
                PYYAML_PROBE_CODE,
            )
    return None


def _pyyaml_probe_succeeds(command: tuple[str, ...], cwd: Path) -> bool:
    """Check PyYAML in the same subprocess context as the pytest command."""
    probe_command = _pyyaml_probe_command(command, cwd)
    if probe_command is None:
        return False
    probe = _run(probe_command, cwd)
    return probe.returncode == 0 and PYYAML_PROBE_SENTINEL in probe.stdout


def _run_with_runtime_deps(
    command: tuple[str, ...],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the check, repairing PyYAML only after a YAML-triggered failure."""
    managed_runtime = _uses_pytest_runtime(command)
    try:
        completed = _run(command, cwd)
    except OSError as exc:
        raise CommandUnavailableError(exc) from exc
    if completed.returncode == 0:
        return completed

    output = f"{completed.stdout}\n{completed.stderr}".lower()
    missing_pyyaml = any(
        marker in output
        for marker in (
            "no module named 'yaml'",
            'no module named "yaml"',
            "modulenotfounderror: yaml",
            "importerror: yaml",
        )
    )
    yaml_traceback = bool(re.search(r"(?:^|[/\\])yaml[/\\][^\n]*", output, re.MULTILINE))
    if yaml_traceback and not missing_pyyaml:
        if managed_runtime:
            try:
                missing_pyyaml = _pyyaml_runtime_needs_repair() or not _pyyaml_probe_succeeds(
                    command, cwd
                )
            except OSError as exc:
                raise CommandUnavailableError(exc) from exc
        elif probe_command := _pyyaml_probe_command(command, cwd):
            try:
                probe = _run(probe_command, cwd)
            except OSError as exc:
                raise CommandUnavailableError(exc) from exc
            missing_pyyaml = probe.returncode != 0 or PYYAML_PROBE_SENTINEL not in probe.stdout
    if not missing_pyyaml:
        return completed

    if not managed_runtime:
        error = ImportError(
            "PyYAML failed inside a wrapped or custom deliberate-break command; "
            "automatic repair is disabled because the wrapper may use a different "
            "Python environment"
        )
        raise RuntimeDependencyError(error) from error

    try:
        _ensure_pytest_runtime_deps()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ImportError, OSError) as exc:
        raise RuntimeDependencyError(exc) from exc
    try:
        probe_succeeded = _pyyaml_probe_succeeds(command, cwd)
    except OSError as exc:
        raise CommandUnavailableError(exc) from exc
    if not probe_succeeded:
        error = ImportError("PyYAML remained unavailable in the managed pytest command environment")
        raise RuntimeDependencyError(error) from error
    try:
        return _run(command, cwd)
    except OSError as exc:
        raise CommandUnavailableError(exc) from exc


def _runtime_dependency_error_result(error: Exception) -> dict[str, object]:
    """Map dependency-repair failures consistently for head and base runs."""
    if isinstance(error, subprocess.TimeoutExpired):
        return _json_result(
            VERDICT_BROKEN,
            reason="dependency-install-timeout",
            command=list(error.cmd) if isinstance(error.cmd, (tuple, list)) else str(error.cmd),
            timeout=error.timeout,
        )
    if isinstance(error, subprocess.CalledProcessError):
        return _json_result(
            VERDICT_BROKEN,
            reason="dependency-install-failed",
            command=list(error.cmd) if isinstance(error.cmd, (tuple, list)) else str(error.cmd),
            returncode=error.returncode,
            stdout=_subprocess_output_text(error.stdout),
            stderr=_subprocess_output_text(error.stderr),
        )
    if isinstance(error, ImportError):
        return _json_result(
            VERDICT_BROKEN,
            reason="dependency-import-failed",
            detail=str(error),
            cause=str(error.__cause__) if error.__cause__ is not None else None,
        )
    return _json_result(
        VERDICT_BROKEN,
        reason="dependency-install-unavailable",
        detail=str(error),
    )


def _git(
    args: list[str],
    cwd: Path,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _assertion_diff_lines(diff_text: str) -> Iterator[str]:
    """Yield removed assertion lines; adding a new assertion is valid test growth."""
    for line in diff_text.splitlines():
        if not line.startswith("-") or line.startswith("---"):
            continue
        if ASSERTION_DIFF_RE.search(line):
            yield line[:240]


def _changed_assertions(base: str, head: str, test_file: str, cwd: Path) -> list[str]:
    status = _git(["diff", "--name-status", f"{base}...{head}", "--", test_file], cwd)
    if any(line.split("\t", 1)[0] == "A" for line in status.stdout.splitlines()):
        return []
    completed = _git(
        ["diff", "--no-ext-diff", "--unified=0", f"{base}...{head}", "--", test_file],
        cwd,
    )
    return list(_assertion_diff_lines(completed.stdout))


def _archive_ref(base: str, target: Path, cwd: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", base],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    target_root = target.resolve()
    with tarfile.open(fileobj=BytesIO(archive.stdout), mode="r:") as tar:
        for member in tar:
            member_path = target_root / member.name
            resolved = member_path.resolve()
            if not resolved.is_relative_to(target_root):
                raise ValueError(f"unsafe archive path: {member.name}")
            if member.isdir():
                resolved.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            resolved.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, resolved.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            resolved.chmod(member.mode & 0o777)


def verify_spec(
    spec: DeliberateBreakSpec,
    *,
    base: str,
    head: str = "HEAD",
    cwd: Path | None = None,
    enforce_tamper: bool = True,
) -> dict[str, object]:
    repo = cwd or Path.cwd()
    test_path = repo / spec.test_file
    if not test_path.is_file():
        return _json_result(
            VERDICT_BROKEN,
            reason="test-file-missing",
            test_file=spec.test_file,
        )

    try:
        if enforce_tamper:
            tampered = _changed_assertions(base, head, spec.test_file, repo)
            if tampered:
                return _json_result(
                    VERDICT_BROKEN,
                    reason="test-assertion-tamper",
                    test_file=spec.test_file,
                    changed_assertions=tampered,
                )

    except subprocess.TimeoutExpired as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="tamper-check-timeout",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            timeout=exc.timeout,
        )
    except subprocess.CalledProcessError as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="tamper-check-failed",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            returncode=exc.returncode,
            stdout=exc.stdout,
            stderr=exc.stderr,
        )
    except OSError as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="tamper-check-unavailable",
            detail=str(exc),
        )

    try:
        head_run = _run_with_runtime_deps(spec.command, repo)
    except subprocess.TimeoutExpired as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="command-timeout",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            timeout=exc.timeout,
        )
    except RuntimeDependencyError as wrapped:
        return _runtime_dependency_error_result(wrapped.error)
    except CommandUnavailableError as wrapped:
        return _json_result(
            VERDICT_BROKEN,
            reason="command-unavailable",
            command=list(spec.command),
            detail=str(wrapped.error),
        )

    if head_run.returncode != 0:
        return _json_result(
            VERDICT_BROKEN,
            reason="head-test-failed",
            test_id=spec.test_id,
            command=list(spec.command),
            stdout=head_run.stdout,
            stderr=head_run.stderr,
        )

    try:
        with tempfile.TemporaryDirectory(prefix="deliberate-break-base-") as tmp:
            base_dir = Path(tmp)
            _archive_ref(base, base_dir, repo)
            base_test = base_dir / spec.test_file
            base_test.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(test_path, base_test)
            base_run = _run_with_runtime_deps(spec.command, base_dir)
    except subprocess.TimeoutExpired as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="command-timeout",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            timeout=exc.timeout,
        )
    except ValueError as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="archive-extract-failed",
            detail=str(exc),
        )
    except RuntimeDependencyError as wrapped:
        return _runtime_dependency_error_result(wrapped.error)
    except CommandUnavailableError as wrapped:
        return _json_result(
            VERDICT_BROKEN,
            reason="command-unavailable",
            command=list(spec.command),
            detail=str(wrapped.error),
        )
    except subprocess.CalledProcessError as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="archive-command-failed",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            returncode=exc.returncode,
            stdout=_subprocess_output_text(exc.stdout),
            stderr=_subprocess_output_text(exc.stderr),
        )
    except OSError as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="base-setup-failed",
            detail=str(exc),
        )

    if base_run.returncode == 0:
        return _json_result(
            VERDICT_HOLLOW,
            reason="test-passed-on-base-with-candidate-test",
            test_id=spec.test_id,
            test_file=spec.test_file,
            break_file=spec.break_file,
            command=list(spec.command),
            stdout=base_run.stdout,
            stderr=base_run.stderr,
        )

    return _json_result(
        VERDICT_PASS,
        reason="head-passed-base-failed",
        test_id=spec.test_id,
        test_file=spec.test_file,
        break_file=spec.break_file,
        command=list(spec.command),
        base_stdout=base_run.stdout,
        base_stderr=base_run.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body-file")
    parser.add_argument("--pr-body-env", default="PR_BODY")
    parser.add_argument("--no-tamper-check", action="store_true")
    args = parser.parse_args(argv)

    body = ""
    if args.pr_body_file:
        body = Path(args.pr_body_file).read_text(encoding="utf-8")
    else:
        body = os.environ.get(args.pr_body_env, "")

    spec = parse_deliberate_break_spec(body)
    if spec is None:
        _write_github_output(has_marker="false", verdict=VERDICT_SKIPPED)
        print(json.dumps(_json_result(VERDICT_SKIPPED, reason="no deliberate-break marker")))
        print("skipped: no deliberate-break marker")
        return 0

    _write_github_output(has_marker="true")
    result = verify_spec(
        spec,
        base=args.base,
        head=args.head,
        enforce_tamper=not args.no_tamper_check,
    )
    _write_github_output(verdict=str(result["verdict"]))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verdict"] == VERDICT_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
