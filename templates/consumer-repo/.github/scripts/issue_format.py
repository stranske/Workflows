#!/usr/bin/env python3
"""Validate a GitHub issue body against the fleet's AGENT_ISSUE_FORMAT contract.

Synced to every consumer repo by `maint-68-sync-consumer-repos.yml`. This is the
single definition of "agent-processable" for the whole fleet — do not fork it
per repo.

Why it exists: every automated lane reaches an issue through a LABEL. An issue
filed with no label and no Tasks/Acceptance block is invisible to the entire
pipeline — nothing validates it, nothing optimises it, nothing claims it. Local
automation that files *findings* rather than *work orders* therefore produces
issues no agent can ever pick up: good evidence, permanently unactionable.
(Observed in Fine-Art-Archive #406-409: four well-evidenced audit findings, zero
labels, no Tasks section between them.)

Used at both ends:
  * `agents-issue-format-guard.yml` validates every issue on open/edit and, on
    failure, applies `agents:format` — the label the existing Agents Issue
    Optimizer already listens for — so a bad issue is ROUTED to the machinery
    that repairs it rather than merely flagged;
  * any local script that files issues can pre-flight with
    `python .github/scripts/issue_format.py <body-file>` and refuse to file junk
    (non-zero exit means unfit).

Rules mirror docs/AGENT_ISSUE_FORMAT.md rather than inventing a parallel
standard: Tasks and Acceptance Criteria are REQUIRED; Why / Scope /
Implementation Notes / Non-Goals are reported as recommended; and at least one
acceptance criterion must name a real test, runnable command, or observable
verification gate.

Recommended sections are advisory: their absence is reported to help authors
improve an issue, but does not change the exit code or route an otherwise valid
work order through the optimizer. Keeping that distinction prevents the guard
from flagging well-formed work orders solely for an optional heading.

`_headings()` skips fenced code blocks, and that is load-bearing rather than
cosmetic. Without it a body whose ONLY "Tasks" and "Acceptance Criteria" lines
sit inside a ```bash fence validates as conforming — a false negative that lets
an unactionable issue through the guard. Well-written issues quote commands and
expected output in fences constantly, so this is the common case, not an edge
one. Any change to heading detection must keep a fenced-heading case in
tests/scripts/test_issue_format.py.

Pure stdlib on purpose — it must run on a bare runner with no install step.
"""

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
    r"|\bsmoke\b|\bverif\w*)",
    re.I,
)
BANNED_ADJECTIVES = ("clean", "nice", "good", "fast", "better", "intuitive", "polished")


def _headings(body: str) -> list[tuple[str, int, int]]:
    """Return markdown headings outside fenced code blocks with line indexes."""
    out: list[tuple[str, int, int]] = []
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
            out.append((heading.group(2).strip().strip(":").lower(), i, len(heading.group(1))))
    return out


def _find(body: str, aliases: tuple[str, ...]) -> int | None:
    for text, idx, _ in _headings(body):
        if text in aliases:
            return idx
    return None


def _section_text(body: str, start: int) -> str:
    lines = body.splitlines()
    start_level = next(level for _, idx, level in _headings(body) if idx == start)
    following = [idx for _, idx, level in _headings(body) if idx > start and level <= start_level]
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
