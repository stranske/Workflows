#!/usr/bin/env python3
"""
Validate GitHub Actions workflow YAML files.

This script checks workflow files for common syntax errors and issues
that may not be caught by basic YAML parsers but cause failures in GitHub Actions.
"""

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)


LINE_LENGTH_EXEMPTIONS = (
    "stranske/Workflows/.github/actions/setup-api-client@",
    "stranske/Workflows/.github/workflows/reusable-model-profile-trial.yml@",
)


class WorkflowDiscoveryError(RuntimeError):
    """Changed workflow discovery could not complete a Git comparison."""


def check_line_length(file_path: Path, max_length: int = 100) -> list[tuple[int, str]]:
    """Check for lines that exceed maximum length (may cause wrapping issues)."""
    issues = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if len(line.rstrip()) > max_length and not any(
                exemption in line for exemption in LINE_LENGTH_EXEMPTIONS
            ):
                issues.append((line_num, f"Line exceeds {max_length} characters"))
    return issues


def check_runs_on_placement(file_path: Path) -> list[tuple[int, str]]:
    """Check that 'runs-on' is properly placed on its own line."""
    issues = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if "runs-on:" in stripped:
                # Check if there's content before 'runs-on:' on the same line
                before_runs_on = line.split("runs-on:")[0].strip()
                if before_runs_on and not before_runs_on.endswith("#"):
                    issues.append(
                        (
                            line_num,
                            "runs-on should be on its own line (found text before it)",
                        )
                    )
    return issues


def check_yaml_syntax(file_path: Path) -> list[tuple[int, str]]:
    """Validate basic YAML syntax."""
    issues = []
    try:
        with open(file_path, encoding="utf-8") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as e:
        line_num = getattr(e, "problem_mark", None)
        if line_num:
            issues.append((line_num.line + 1, f"YAML syntax error: {e.problem}"))
        else:
            issues.append((0, f"YAML syntax error: {str(e)}"))
    return issues


def check_multiline_conditions(file_path: Path) -> list[tuple[int, str]]:
    """Check for complex conditions that should use multiline format."""
    issues = []
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            # Only flag if line exceeds repo standard (100 chars) OR continues improperly
            if stripped.startswith("if:") and len(stripped) > 100:
                # Check if it's using multiline format
                if not stripped.endswith("|") and not stripped.endswith(">"):
                    issues.append(
                        (
                            line_num,
                            "Very long 'if' condition should use multiline format (| or >)",
                        )
                    )
            # Check if next line looks like continuation without proper multiline syntax
            elif stripped.startswith("if:") and line_num < len(lines):
                next_line = lines[line_num].strip()
                # Check if 'runs-on:' appears mid-line (indicates malformed wrapping)
                if next_line and "runs-on:" in next_line and not next_line.startswith("runs-on:"):
                    issues.append(
                        (
                            line_num + 1,
                            "Found 'runs-on:' not at start of line - possible malformed multiline 'if'",
                        )
                    )
    return issues


def validate_workflow(file_path: Path, verbose: bool = False) -> bool:
    """Validate a workflow file and return True if valid."""
    all_issues = []

    # Run all checks
    all_issues.extend([(line, f"YAML: {msg}") for line, msg in check_yaml_syntax(file_path)])
    all_issues.extend([(line, f"Length: {msg}") for line, msg in check_line_length(file_path)])
    all_issues.extend(
        [(line, f"Placement: {msg}") for line, msg in check_runs_on_placement(file_path)]
    )
    all_issues.extend(
        [(line, f"Format: {msg}") for line, msg in check_multiline_conditions(file_path)]
    )

    if all_issues:
        print(f"\n❌ {file_path.name}: Found {len(all_issues)} issue(s)")
        for line_num, message in sorted(all_issues):
            if line_num > 0:
                print(f"  Line {line_num}: {message}")
            else:
                print(f"  {message}")
        return False
    else:
        if verbose:
            print(f"✓ {file_path.name}: Valid")
        return True


# Workflows with pre-existing lint issues that are temporarily skipped
# TODO: Fix these workflows and remove from skip list
# See: https://github.com/mhfed/Workflows/issues/XXXX
LEGACY_SKIP_WORKFLOWS = {
    # Belt workflows have long lines - need refactoring
    "agents-71-codex-belt-dispatcher.yml",
    "agents-72-codex-belt-worker.yml",
    "agents-73-codex-belt-conveyor.yml",
}


def _workflow_paths_from_stdout(stdout: str) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        path = Path(stripped)
        if path.suffix not in {".yml", ".yaml"}:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _local_workflow_edits() -> list[Path]:
    """Tracked staged and unstaged workflow edits relative to ``HEAD``."""
    try:
        proc = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=d",
                "HEAD",
                "--",
                ".github/workflows",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return _workflow_paths_from_stdout(proc.stdout)


def discover_changed_workflows(base_ref: str | None = None) -> list[Path]:
    """Return workflow paths changed on this branch relative to a merge base ref.

    When ``base_ref`` is explicitly given, only that ref is queried. Otherwise
    ``origin/main`` is tried before ``main``. Stops on the first successful Git
    comparison even when the diff is empty, and raises
    :class:`WorkflowDiscoveryError` if no permitted comparison succeeds.

    Default discovery also unions tracked local edits under ``.github/workflows``
    (staged and unstaged) against ``HEAD``.
    """
    candidates = [base_ref] if base_ref is not None else ["origin/main", "main"]
    errors: list[str] = []
    for ref in candidates:
        try:
            proc = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    "--diff-filter=d",
                    f"{ref}...HEAD",
                    "--",
                    ".github/workflows",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            errors.append(f"{ref}: {exc}")
            continue
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip() or f"git diff exited {proc.returncode}"
            errors.append(f"{ref}: {detail}")
            continue
        paths = _workflow_paths_from_stdout(proc.stdout)
        if base_ref is None:
            seen = {str(path) for path in paths}
            for path in _local_workflow_edits():
                key = str(path)
                if key not in seen:
                    seen.add(key)
                    paths.append(path)
        return paths
    raise WorkflowDiscoveryError(
        "Failed to discover changed workflow files via git diff (" + "; ".join(errors) + ")"
    )


def main():
    parser = argparse.ArgumentParser(description="Validate GitHub Actions workflow YAML files")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Workflow files to validate (default: git-changed files under .github/workflows)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show validation results for all files",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Don't skip known legacy workflows (validate all files)",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help=(
            "Explicit merge base for discovering changed workflows when no files are "
            "listed (defaults to origin/main, then main)"
        ),
    )
    args = parser.parse_args()

    files = list(args.files)
    if not files:
        try:
            files = discover_changed_workflows(args.base_ref)
        except WorkflowDiscoveryError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            sys.exit(1)
        if not files:
            print("No changed workflow files to validate")
            sys.exit(0)

    all_valid = True
    skipped_count = 0
    for file_path in files:
        if not file_path.exists():
            print(f"❌ {file_path}: File not found")
            all_valid = False
            continue

        # Skip known legacy workflows unless --no-skip is specified
        if file_path.name in LEGACY_SKIP_WORKFLOWS and not args.no_skip:
            if args.verbose:
                print(f"⏭️  {file_path.name}: Skipped (known legacy workflow)")
            skipped_count += 1
            continue

        if not validate_workflow(file_path, args.verbose):
            all_valid = False

    if all_valid:
        msg = f"\n✓ All {len(files) - skipped_count} workflow file(s) validated successfully"
        if skipped_count:
            msg += f" ({skipped_count} legacy workflow(s) skipped)"
        print(msg)
        sys.exit(0)
    else:
        print("\n❌ Validation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
