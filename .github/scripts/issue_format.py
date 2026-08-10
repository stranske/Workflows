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
one. Any change to heading detection must keep a fenced-heading case in the
upstream Workflows test `tests/scripts/test_issue_format.py`.

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
    r"|\bpytest\b|\b(?:python(?:3)?\s+-m\s+(?:unittest|pytest)\b)"
    r"|\bnode\s+--test\b|\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:test|vitest|jest|playwright)\b"
    r"|\b(?:make|just|cargo|go|dotnet)\s+(?:test|check)\b"
    r"|\bgh workflow run\b|\bgh run\b"
    r"|\bcurl\b|\bHTTP [1-5]\d\d\b"
    r"|\b(?:API|endpoint|request|response)\s+(?:returns?|responds with)\s+[1-5]\d\d(?:\s+status)?\b"
    r"|\bsmoke\b|\bverif\w*)",
    re.I,
)
BANNED_ADJECTIVES = (
    "clean",
    "nice",
    "good",
    "fast",
    "better",
    "intuitive",
    "polished",
    "performant",
)
_TASK_CATEGORY = r"(?:file|function|class|method|path|config(?:uration)?|key|job|workflow|command)"
_TASK_EXTENSION = (
    r"py|js|jsx|ts|tsx|yml|yaml|json|toml|md|sh|go|rs|java|kt|rb|php|css|html|sql|"
    r"xml|txt|ini|cfg|conf|lock|gradle|swift|c|cc|cpp|h|hpp|cs|fs|r|jl"
)
_TASK_KNOWN_BASENAME = (
    r"(?:Dockerfile|Makefile|Justfile|Procfile|Gemfile|Rakefile|"
    r"Cargo\.toml|pyproject\.toml|package\.json|go\.mod|go\.sum|pom\.xml|"
    r"build\.gradle|CMakeLists\.txt|README(?:\.(?:md|rst|txt))?|"
    r"LICENSE(?:\.(?:md|txt))?|\.gitignore|\.editorconfig)"
)
_TASK_COMMAND = (
    r"(?:python(?:3)?\s+-m\s+(?:pytest|unittest)\b|pytest\b|node\s+--test\b|"
    r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:test|vitest|jest|playwright)\b|"
    r"(?:make|just|cargo|go|dotnet)\s+(?:test|check)\b|"
    r"gh\s+(?:workflow\s+run|run)\s+\S+|curl\s+\S+)"
)


def _concrete_span(span: str) -> bool:
    """Return True when a backticked/unquoted token names a real work target."""
    span = span.strip().rstrip(".,;:!?")
    if not span:
        return False
    if re.fullmatch(_TASK_CATEGORY, span, re.I):
        return False
    # Bare lowercase English words (`bugs`, `later`) are not actionable targets.
    if re.fullmatch(r"[a-z]{2,24}", span):
        return False
    if "/" in span or span.startswith("."):
        return True
    if re.fullmatch(_TASK_KNOWN_BASENAME, span, re.I):
        return True
    if re.fullmatch(rf"[\w.-]+\.(?:{_TASK_EXTENSION})", span, re.I):
        return True
    if "_" in span or "." in span:
        return True
    # Multi-segment PascalCase or lowerCamelCase symbols (e.g. IssueFormatter,
    # calculateDiscount). A capitalized interior segment distinguishes them from
    # generic lowercase prose.
    return re.fullmatch(r"[A-Za-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+", span) is not None


def _task_has_concrete_target(item: str) -> bool:
    """True when a task checkbox names a file, path, symbol, config, job, or command."""
    # Category word must be followed by a concrete identifier (not "file handling").
    for match in re.finditer(rf"\b{_TASK_CATEGORY}\s+(`[^`]+`|[^\s]+)", item, re.I):
        token = match.group(1)
        span = token[1:-1] if token.startswith("`") and token.endswith("`") else token.strip("'\"")
        if _concrete_span(span):
            return True
    for match in re.finditer(r"`([^`]+)`", item):
        if _concrete_span(match.group(1)):
            return True
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", item):
        # Unquoted: only unambiguous lowerCamelCase (calculateDiscount).
        # Brand/prose capitals (GitHub, JavaScript, OpenAI) must not satisfy.
        if not re.fullmatch(r"[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+", token):
            continue
        if _concrete_span(token):
            return True
    if re.search(rf"(?:^|[\s])({_TASK_KNOWN_BASENAME})\b", item, re.I):
        return True
    if re.search(rf"(?:^|[\s])([\w.-]+\.(?:{_TASK_EXTENSION}))\b", item, re.I):
        return True
    # Unquoted path with a directory separator (src/main.go, .github/workflows/x.yml).
    if re.search(r"(?:^|[\s])((?:\./)?[\w.-]+(?:/[\w./-]+)+)", item):
        return True
    # Command names in prose ("make the UI better", "go improve it") are not
    # concrete targets. Require a command-shaped invocation instead.
    return re.search(rf"(?:^|[\s`]){_TASK_COMMAND}", item, re.I) is not None


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
            elif (
                marker[0] == fence[0]
                and len(marker) >= fence[1]
                and re.fullmatch(
                    rf"\s{{0,3}}(?:`{{{fence[1]},}}|~{{{fence[1]},}})\s*",
                    line,
                )
            ):
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
        if any(
            text == alias or text.startswith((f"{alias} (", f"{alias} -", f"{alias} /"))
            for alias in aliases
        ):
            return idx
    return None


def _section_text(body: str, start: int) -> str:
    lines = body.splitlines()
    start_level = next(level for _, idx, level in _headings(body) if idx == start)
    following = [idx for _, idx, level in _headings(body) if idx > start and level <= start_level]
    end = following[0] if following else len(lines)
    return "\n".join(lines[start + 1 : end])


def _without_fenced_code(text: str) -> str:
    """Remove Markdown fences so examples cannot satisfy issue requirements."""
    kept: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        match = re.match(r"\s{0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif (
                marker[0] == fence[0]
                and len(marker) >= fence[1]
                and re.fullmatch(
                    rf"\s{{0,3}}(?:`{{{fence[1]},}}|~{{{fence[1]},}})\s*",
                    line,
                )
            ):
                # Closing fences are marker-only (optional whitespace); trailing
                # content such as a language tag must not end the fence.
                fence = None
            continue
        if fence is None:
            kept.append(line)
    return "\n".join(kept)


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
    if tasks_at is not None:
        task_items = re.findall(
            r"^\s*[-*]\s*\[[ xX]\]\s*(.+)$",
            _without_fenced_code(_section_text(body, tasks_at)),
            re.M,
        )
        if not task_items:
            report.problems.append(
                "`Tasks` has no checkbox items (`- [ ] …`); agents track progress by them."
            )
        elif any(not _task_has_concrete_target(item) for item in task_items):
            report.problems.append(
                "`Tasks` must name a concrete file, symbol, path, config key, job, or command."
            )

    acceptance_at = _find(body, REQUIRED["Acceptance Criteria"])
    if acceptance_at is not None:
        acceptance = _section_text(body, acceptance_at)
        if not GATE.search(acceptance):
            report.problems.append(
                "`Acceptance Criteria` names no test, runnable command or observable "
                "verification gate — Definition of Ready / Quality Bar §2 requires one."
            )
        prose = re.sub(r"(?<!`)`(?!`)[^`\n]*`", "", _without_fenced_code(acceptance))
        hits = [word for word in BANNED_ADJECTIVES if re.search(rf"\b{word}\b", prose, re.I)]
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
