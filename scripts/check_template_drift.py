#!/usr/bin/env python3
"""Enforce drift checks between Workflows agent workflows and templates."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

WORKFLOW_ALIAS_MAPPINGS = {
    "agents-63-issue-intake.yml": "agents-issue-intake.yml",
}


@dataclass(frozen=True)
class WorkflowPair:
    main_path: Path
    template_path: Path


@dataclass(frozen=True)
class AllowlistEntry:
    main_path: str
    template_path: str
    main_sha256: str
    template_sha256: str
    reason: str

    def allows(
        self,
        *,
        main_path: str,
        template_path: str,
        main_text: str,
        template_text: str,
    ) -> bool:
        return (
            self.main_path == main_path
            and self.template_path == template_path
            and self.main_sha256 == normalized_sha256(main_text)
            and self.template_sha256 == normalized_sha256(template_text)
        )


@dataclass(frozen=True)
class TemplateDriftAllowlist:
    entries: tuple[AllowlistEntry, ...] = ()

    def allows(
        self,
        *,
        main_path: str,
        template_path: str,
        main_text: str,
        template_text: str,
    ) -> bool:
        return any(
            entry.allows(
                main_path=main_path,
                template_path=template_path,
                main_text=main_text,
                template_text=template_text,
            )
            for entry in self.entries
        )


@dataclass(frozen=True)
class PairResult:
    main_path: str
    template_path: str
    status: str
    main_sha256: str
    template_sha256: str
    reason: str = ""


def normalize_text(text: str) -> str:
    """Normalize text before drift comparison.

    The old shell guard counted unified-diff header lines and raw line counts.
    This checker compares actual content after stabilizing line endings and
    trailing whitespace.
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def normalized_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def drift_between(
    main_text: str,
    template_text: str,
    allowlist: TemplateDriftAllowlist | tuple[AllowlistEntry, ...] | None = None,
    *,
    main_path: str = "",
    template_path: str = "",
) -> bool:
    """Return True when unallowlisted functional drift exists."""

    if normalize_text(main_text) == normalize_text(template_text):
        return False

    if allowlist is None:
        return True

    entries = (
        allowlist.entries if isinstance(allowlist, TemplateDriftAllowlist) else tuple(allowlist)
    )
    allowed = TemplateDriftAllowlist(entries)
    return not allowed.allows(
        main_path=main_path,
        template_path=template_path,
        main_text=main_text,
        template_text=template_text,
    )


def read_allowlist(path: Path) -> TemplateDriftAllowlist:
    if not path.exists():
        return TemplateDriftAllowlist()

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    entries: list[AllowlistEntry] = []
    for section in parser.sections():
        entries.append(
            AllowlistEntry(
                main_path=parser.get(section, "main"),
                template_path=parser.get(section, "template"),
                main_sha256=parser.get(section, "main_sha256"),
                template_sha256=parser.get(section, "template_sha256"),
                reason=parser.get(section, "reason", fallback=""),
            )
        )
    return TemplateDriftAllowlist(tuple(entries))


def read_manifest_workflow_names(repo_root: Path) -> set[str]:
    manifest_path = repo_root / ".github" / "sync-manifest.yml"
    if not manifest_path.exists():
        return set()

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    workflow_names: set[str] = set()
    for entry in manifest.get("workflows", []) or []:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source", ""))
        if source.startswith(".github/workflows/"):
            workflow_names.add(source.removeprefix(".github/workflows/"))
    return workflow_names


def discover_workflow_pairs(repo_root: Path) -> list[WorkflowPair]:
    main_dir = repo_root / ".github" / "workflows"
    template_dir = repo_root / "templates" / "consumer-repo" / ".github" / "workflows"
    manifest_workflow_names = read_manifest_workflow_names(repo_root)

    pairs: dict[tuple[str, str], WorkflowPair] = {}

    for main_path in sorted(main_dir.glob("agents-*.yml")):
        template_name = WORKFLOW_ALIAS_MAPPINGS.get(main_path.name, main_path.name)
        template_path = template_dir / template_name
        if (
            not template_path.exists()
            and main_path.name not in WORKFLOW_ALIAS_MAPPINGS
            and template_name not in manifest_workflow_names
        ):
            continue
        rel_main = main_path.relative_to(repo_root).as_posix()
        rel_template = template_path.relative_to(repo_root).as_posix()
        pairs[(rel_main, rel_template)] = WorkflowPair(main_path, template_path)

    return [pairs[key] for key in sorted(pairs)]


def check_pairs(
    repo_root: Path,
    pairs: list[WorkflowPair],
    allowlist: TemplateDriftAllowlist,
) -> list[PairResult]:
    results: list[PairResult] = []
    for pair in pairs:
        main_text = pair.main_path.read_text(encoding="utf-8")
        main_rel = pair.main_path.relative_to(repo_root).as_posix()
        template_rel = pair.template_path.relative_to(repo_root).as_posix()
        main_hash = normalized_sha256(main_text)

        if not pair.template_path.exists():
            results.append(
                PairResult(
                    main_path=main_rel,
                    template_path=template_rel,
                    status="drift",
                    main_sha256=main_hash,
                    template_sha256="",
                    reason="template counterpart is missing",
                )
            )
            continue

        template_text = pair.template_path.read_text(encoding="utf-8")
        template_hash = normalized_sha256(template_text)

        if normalize_text(main_text) == normalize_text(template_text):
            status = "in_sync"
            reason = ""
        elif allowlist.allows(
            main_path=main_rel,
            template_path=template_rel,
            main_text=main_text,
            template_text=template_text,
        ):
            status = "allowlisted"
            reason = next(
                (
                    entry.reason
                    for entry in allowlist.entries
                    if entry.main_path == main_rel
                    and entry.template_path == template_rel
                    and entry.main_sha256 == main_hash
                    and entry.template_sha256 == template_hash
                ),
                "",
            )
        else:
            status = "drift"
            reason = "unallowlisted content differs"

        results.append(
            PairResult(
                main_path=main_rel,
                template_path=template_rel,
                status=status,
                main_sha256=main_hash,
                template_sha256=template_hash,
                reason=reason,
            )
        )
    return results


def render_summary(results: list[PairResult]) -> str:
    lines = ["# Template Drift Report", ""]
    counts = {
        "in_sync": sum(1 for result in results if result.status == "in_sync"),
        "allowlisted": sum(1 for result in results if result.status == "allowlisted"),
        "drift": sum(1 for result in results if result.status == "drift"),
    }
    lines.append(
        f"- in sync: {counts['in_sync']}\n"
        f"- allowlisted baseline drift: {counts['allowlisted']}\n"
        f"- unallowlisted drift: {counts['drift']}"
    )
    lines.append("")

    if counts["drift"]:
        lines.extend(["## Unallowlisted Drift", ""])
        for result in results:
            if result.status == "drift":
                lines.append(f"- `{result.main_path}` -> `{result.template_path}`")
                lines.append(f"  - main sha256: `{result.main_sha256}`")
                lines.append(f"  - template sha256: `{result.template_sha256}`")
                if result.reason:
                    lines.append(f"  - reason: {result.reason}")
        lines.append("")

    if counts["allowlisted"]:
        lines.extend(["## Allowlisted Baseline Drift", ""])
        for result in results:
            if result.status == "allowlisted":
                lines.append(f"- `{result.main_path}` -> `{result.template_path}`")
                if result.reason:
                    lines.append(f"  - reason: {result.reason}")
        lines.append("")

    return "\n".join(lines)


def print_allowlist_template(results: list[PairResult]) -> None:
    for index, result in enumerate(
        (result for result in results if result.status == "drift"),
        start=1,
    ):
        print(f"[pair.{index}]")
        print(f"main = {result.main_path}")
        print(f"template = {result.template_path}")
        print(f"main_sha256 = {result.main_sha256}")
        print(f"template_sha256 = {result.template_sha256}")
        print(
            "reason = Existing reviewed baseline drift; align the template or "
            "update this fingerprint deliberately."
        )
        print()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("config/template-drift-allowlist.txt"),
    )
    parser.add_argument("--summary", type=Path)
    parser.add_argument(
        "--print-allowlist-template",
        action="store_true",
        help="Print INI entries for currently unallowlisted drift.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    allowlist_path = args.allowlist if args.allowlist.is_absolute() else repo_root / args.allowlist
    allowlist = read_allowlist(allowlist_path)
    results = check_pairs(repo_root, discover_workflow_pairs(repo_root), allowlist)

    if args.print_allowlist_template:
        print_allowlist_template(results)
        return 0

    summary = render_summary(results)
    print(summary)
    if args.summary:
        args.summary.write_text(summary + "\n", encoding="utf-8")

    if any(result.status == "drift" for result in results):
        print(
            "::error::Unallowlisted template drift detected. "
            "Align the template or update config/template-drift-allowlist.txt.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
