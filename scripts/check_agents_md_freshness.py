#!/usr/bin/env python3
"""Warn when the managed Orchestrator AGENTS.md section cites stale repo facts."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

MANAGED_START = "<!-- BEGIN orch-playbook -->"
MANAGED_END = "<!-- END orch-playbook -->"
PATH_SUFFIXES = {
    ".cfg",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    value: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "value": self.value, "message": self.message}


def managed_section(text: str) -> str | None:
    start = text.find(MANAGED_START)
    end = text.find(MANAGED_END, start + len(MANAGED_START)) if start >= 0 else -1
    if start < 0 or end < 0 or end < start:
        return None
    return text[start : end + len(MANAGED_END)]


def _clean_ref(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    value = re.sub(r"[:#]L?\d+(?:-L?\d+)?$", "", value)
    return value


def _looks_like_path(value: str) -> bool:
    if value.startswith(("./", "../", ".github/", "docs/", "scripts/", "templates/", "tools/")):
        return True
    path = Path(value)
    return "/" in value or path.suffix.lower() in PATH_SUFFIXES


def _resolve_repo_path(repo_root: Path, ref: str) -> Path | None:
    root = repo_root.resolve()
    raw_path = Path(ref)
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _path_exists(repo_root: Path, ref: str) -> bool:
    candidate = _resolve_repo_path(repo_root, ref)
    return candidate.exists() if candidate else False


def _command_parts(ref: str) -> list[str]:
    try:
        return shlex.split(ref)
    except ValueError:
        return ref.split()


def _command_exists(repo_root: Path, ref: str) -> bool:
    parts = _command_parts(ref)
    if not parts:
        return True
    command = parts[0]
    if command.startswith(("./", "../")) or "/" in command:
        candidate = _resolve_repo_path(repo_root, command)
        return candidate.exists() if candidate else False
    return shutil.which(command) is not None


def _check_command_ref(repo_root: Path, ref: str) -> list[Finding]:
    findings: list[Finding] = []
    if not _command_exists(repo_root, ref):
        findings.append(Finding("command", ref, f"referenced command not found: {ref}"))
    for arg in _command_parts(ref)[1:]:
        arg = _clean_ref(arg)
        if "=" in arg:
            _, arg = arg.split("=", 1)
            arg = _clean_ref(arg)
        if _looks_like_path(arg) and not _path_exists(repo_root, arg):
            findings.append(Finding("path", arg, f"referenced path not found: {arg}"))
    return findings


def cited_refs(section: str) -> list[str]:
    refs: list[str] = []
    for raw in re.findall(r"`([^`]+)`", section):
        value = _clean_ref(raw)
        if not value or value.startswith(("http://", "https://")):
            continue
        refs.append(value)
    return refs


def check_agents_md(repo_root: Path, agents_md: Path | None = None) -> list[Finding]:
    agents_path = agents_md or repo_root / "AGENTS.md"
    if not agents_path.exists():
        return []
    section = managed_section(agents_path.read_text(encoding="utf-8"))
    if section is None:
        return []

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for ref in cited_refs(section):
        if " " in ref:
            for finding in _check_command_ref(repo_root, ref):
                key = (finding.kind, finding.value)
                if key not in seen:
                    findings.append(finding)
                seen.add(key)
        elif _looks_like_path(ref):
            key = ("path", ref)
            if key not in seen and not _path_exists(repo_root, ref):
                findings.append(Finding("path", ref, f"referenced path not found: {ref}"))
            seen.add(key)
    return findings


def _emit_github_warnings(findings: list[Finding]) -> None:
    for finding in findings:
        message = finding.message.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")
        print(f"::warning title=AGENTS.md freshness::{message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--agents-md", type=Path)
    parser.add_argument("--github-annotations", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--strict", action="store_true", help="Exit non-zero when findings are present."
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    if args.agents_md:
        agents_md = (
            args.agents_md if args.agents_md.is_absolute() else repo_root / args.agents_md
        ).resolve()
    else:
        agents_md = None
    findings = check_agents_md(repo_root, agents_md)

    if args.as_json:
        print(json.dumps({"findings": [finding.as_dict() for finding in findings]}, indent=2))
    elif findings:
        for finding in findings:
            print(finding.message)
    else:
        print("AGENTS.md managed section freshness check passed.")

    if args.github_annotations and findings:
        _emit_github_warnings(findings)

    return 1 if args.strict and findings else 0


if __name__ == "__main__":
    sys.exit(main())
