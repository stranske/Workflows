"""Validate a GitHub issue body against the fleet AGENT_ISSUE_FORMAT contract."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

REQUIRED: dict[str, tuple[str, ...]] = {
    "Tasks": ("tasks", "task list", "implementation"),
    "Acceptance Criteria": ("acceptance criteria", "acceptance", "definition of done"),
}
RECOMMENDED: dict[str, tuple[str, ...]] = {
    "Why": ("why", "goals", "summary", "motivation", "finding"),
    "Scope": ("scope", "background", "context", "overview"),
    "Implementation Notes": ("implementation notes",),
    "Non-Goals": ("non-goals", "out of scope", "constraints"),
}
GATE = re.compile(
    r"(tests?/[\w./-]+\.py(::[\w:\[\]-]+)?"
    r"|\btest_[\w]+"
    r"|\bpytest\b|\bnpm test\b|\bmake test\b"
    r"|\bgh workflow run\b|\bgh run\b"
    r"|\bcurl\b|\bHTTP [1-5]\d\d\b"
    r"|\b(?:API|endpoint|request|response)\s+(?:returns?|responds with)\s+[1-5]\d\d(?:\s+status)?\b"
    r"|\bsmoke\b|\bverif)",
    re.I,
)
BANNED_ADJECTIVES = ("clean", "nice", "good", "fast", "better", "intuitive", "polished")


def _headings(body: str) -> list[tuple[str, int]]:
    """Return markdown headings outside fenced code blocks with line indexes."""
    out: list[tuple[str, int]] = []
    fence: tuple[str, int] | None = None
    for i, line in enumerate(body.splitlines()):
        fence_match = re.match(r"\s{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence is not None:
            continue
        heading = re.match(r"\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            out.append((heading.group(2).strip().strip(":").lower(), i))
    return out


def _find(body: str, aliases: tuple[str, ...]) -> int | None:
    for text, idx in _headings(body):
        if any(text == alias or text.startswith(alias) for alias in aliases):
            return idx
    return None


def _section_text(body: str, start: int) -> str:
    lines = body.splitlines()
    following = [idx for _, idx in _headings(body) if idx > start]
    end = following[0] if following else len(lines)
    return "\n".join(lines[start + 1 : end])


@dataclass
class Report:
    ok: bool = True
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def as_markdown(self) -> str:
        if self.ok and not self.missing_recommended:
            return "Issue body conforms to `docs/AGENT_ISSUE_FORMAT.md`."
        if self.ok:
            out = ["Issue body is agent-processable with advisories.", ""]
        else:
            out = [
                "This issue is **not yet agent-processable**. See `docs/AGENT_ISSUE_FORMAT.md`.",
                "",
            ]
        if self.missing_required:
            out.append(
                "**Missing required sections:** "
                + ", ".join(f"`{section}`" for section in self.missing_required)
            )
        out.extend(f"- {problem}" for problem in self.problems)
        if self.missing_recommended:
            out.extend(
                [
                    "",
                    "_Recommended but absent:_ "
                    + ", ".join(f"`{section}`" for section in self.missing_recommended),
                ]
            )
        return "\n".join(out)


def validate(body: str) -> Report:
    """Check an issue body; every structural format problem is non-conforming."""
    report = Report()
    body = body or ""
    for name, aliases in REQUIRED.items():
        if _find(body, aliases) is None:
            report.missing_required.append(name)
    for name, aliases in RECOMMENDED.items():
        if _find(body, aliases) is None:
            report.missing_recommended.append(name)

    tasks_at = _find(body, REQUIRED["Tasks"])
    if tasks_at is not None and not re.search(
        r"^\s*[-*]\s*\[[ xX]\]", _section_text(body, tasks_at), re.M
    ):
        report.problems.append(
            "`Tasks` has no checkbox items (`- [ ] …`); agents track progress by them."
        )

    acceptance_at = _find(body, REQUIRED["Acceptance Criteria"])
    if acceptance_at is not None:
        acceptance = _section_text(body, acceptance_at)
        if not GATE.search(acceptance):
            report.problems.append(
                "`Acceptance Criteria` names no test, runnable command or observable "
                "verification gate — Definition of Ready / Quality Bar §2 requires one."
            )
        hits = [word for word in BANNED_ADJECTIVES if re.search(rf"\b{word}\b", acceptance, re.I)]
        if hits:
            report.problems.append(
                "`Acceptance Criteria` uses subjective wording ("
                + ", ".join(sorted(hits))
                + "); replace with a measurable check."
            )
    report.ok = not report.missing_required and not report.problems
    return report


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        with open(argv[0], encoding="utf-8") as issue_file:
            body = issue_file.read()
    else:
        body = sys.stdin.read()
    report = validate(body)
    print(report.as_markdown())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
