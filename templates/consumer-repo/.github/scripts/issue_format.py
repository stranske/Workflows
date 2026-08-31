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

import contextlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
_LINT_COMMAND = (
    r"\b(?:ruff(?:\s+check)?|mypy|black\s+--check|isort\s+--check|flake8|"
    r"pylint|eslint|prettier\s+--check|tsc\s+--noEmit)\b"
)
GATE = re.compile(
    r"(tests?/[\w./-]+\.py(::[\w:\[\]-]+)?"
    r"|\btest_[\w]+"
    r"|\bpytest\b|\b(?:python(?:3)?\s+-m\s+(?:unittest|pytest)\b)"
    r"|\bnode\s+--test\b|\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:test|vitest|jest|playwright)\b"
    r"|\b(?:make|just|cargo|go|dotnet)\s+(?:test|check)\b"
    + r"|"
    + _LINT_COMMAND
    + r"|\bgh workflow run\b|\bgh run\b"
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
_TASK_CATEGORY = (
    r"(?:file|function|class|component|method|path|config(?:uration)?|key|job|workflow|command)"
)
_TASK_TRAILING_SYMBOL_CATEGORY = r"(?:function|class|component|method|job|workflow)"
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
    + _LINT_COMMAND
    + r"|gh\s+(?:workflow\s+run|run)\s+\S+|curl\s+\S+)"
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
        # A quoted identifier immediately following an explicit target category
        # is concrete even when its spelling is a normal lowercase word (for
        # example, ``function `validate` `` or ``key `timeout` ``).
        if (
            token.startswith("`")
            and token.endswith("`")
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", span)
            and not re.fullmatch(_TASK_CATEGORY, span, re.I)
        ):
            return True
        if _concrete_span(span):
            return True
    # Natural prose often names a PascalCase symbol before its category (for
    # example, "UserForm component"). The category makes this use specific;
    # generic capitalized product words without that context remain rejected.
    for match in re.finditer(
        rf"\b([A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]+)\s+{_TASK_TRAILING_SYMBOL_CATEGORY}\b",
        item,
    ):
        if _concrete_span(match.group(1)):
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


# --- Addressability ---------------------------------------------------------
#
# A perfectly-formatted issue can still be impossible to action, because format
# and addressability are different axes. Fine-Art-Archive #406-409 are the
# reference case: every required section present, `agents:formatted` awarded,
# and every one of the six paths #409 instructs an agent to modify exists only
# in a local workspace that is not on GitHub. A lane cloned the repo, could not
# find `scripts/automation_audit.py`, and stalled — `agents:tried-codex` ->
# `needs-human` -> `agents:auto-pilot-pause`.
#
# `_task_has_concrete_target` already requires a task to NAME a file; this asks
# the next question — does that file exist in the repo the issue was filed
# against?
#
# The gate is deliberately asymmetric. Naming a file that does not exist yet is
# normal and correct ("create `src/foo.py`"), so unresolved paths alone never
# fail. What fails is an issue that cites several paths and resolves NONE of
# them, which means it describes some other tree. That also aligns with the
# format's own requirement that `Why` cite current evidence at `file:line`: an
# issue with no resolvable path has no current evidence in this repo.
_PATH_SPAN = re.compile(r"`([^`\n]+)`")
_UNQUOTED_PATH = re.compile(
    r"(?<![\w./-])((?:\./)?(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.[A-Za-z0-9]+)(?![\w./-])"
)
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_NODE_SUFFIX = re.compile(r"::.+$")  # pytest node ids: tests/x.py::test_y
_ORIGINAL_ISSUE_BLOCK_RE = re.compile(
    r"<details\b[^>]*>\s*<summary>Original Issue</summary>\s*"
    r"(?P<fence>`{3,}|~{3,})text\s*\n(?P<inner>.*?)\n(?P=fence)\s*</details>",
    re.DOTALL | re.IGNORECASE,
)
# Self-referential boilerplate. The format contract tells authors to cite it, so
# nearly every body mentions it — and it lives in every repo, which means
# counting it as evidence would let one boilerplate line defeat the whole gate.
# Measured on Fine-Art-Archive #409: this was the ONLY path that resolved.
_NOT_EVIDENCE = frozenset(
    {
        "docs/AGENT_ISSUE_FORMAT.md",
        "AGENT_ISSUE_FORMAT.md",
    }
)
_PATHISH_EXT = (
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".sql",
    ".html",
    ".css",
    ".xml",
    ".txt",
    ".lock",
    ".env",
)
# Below this many citations the sample is too small to conclude "wrong repo" —
# a single path in a prose aside must not fail an otherwise sound issue.
_MIN_CITATIONS_TO_JUDGE = 3


def _normalise_cited_path(raw: str) -> str | None:
    """Return a safe repo-relative citation, or None for non-path text."""
    candidate = _NODE_SUFFIX.sub("", raw.strip())
    candidate = _LINE_SUFFIX.sub("", candidate)
    if candidate.startswith("./"):
        candidate = candidate[2:]
    if not candidate or " " in candidate:
        return None
    if candidate.startswith("/") or any(part == ".." for part in candidate.split("/")):
        return None
    if candidate in _NOT_EVIDENCE:
        return None
    if "://" in candidate or candidate.startswith(("-", "@", "#", "$")):
        return None
    if any(ch in candidate for ch in "*?<>|"):  # globs and placeholders
        return None
    if "/" not in candidate and not candidate.endswith(_PATHISH_EXT):
        return None
    return candidate


def _task_items(body: str) -> list[str]:
    return re.findall(r"^\s*[-*]\s*\[[ xX]\]\s*(.+)$", body or "", re.M)


def _candidate_matches(text: str) -> list[tuple[int, int, str]]:
    """Extract candidate paths together with their position in a task."""
    matches = [(match.start(), match.end(), match.group(1)) for match in _PATH_SPAN.finditer(text)]
    matches.extend(
        (match.start(), match.end(), match.group(1)) for match in _UNQUOTED_PATH.finditer(text)
    )
    return sorted(matches)


_EXPLICIT_CREATE_PREFIX = re.compile(
    r"\b(?:create|add|introduce|scaffold|generate|write)\s+"
    r"(?:(?:a|the)\s+)?(?:new\s+)?(?:(?:files?|directories|directory|folders?)\s+)?"
    r"(?:at\s+|named\s+)?$",
    re.I,
)


def _cited_paths(body: str) -> list[str]:
    """Safe repo-relative citations, including unquoted task paths."""
    seen: dict[str, None] = {}
    for raw in _PATH_SPAN.findall(body or ""):
        if candidate := _normalise_cited_path(raw):
            seen.setdefault(candidate, None)
    for item in _task_items(body):
        for raw in _UNQUOTED_PATH.findall(item):
            if candidate := _normalise_cited_path(raw):
                seen.setdefault(candidate, None)
    return list(seen)


def _created_paths(body: str) -> set[str]:
    """Paths explicitly created by a task are not pre-existing evidence."""
    created: set[str] = set()
    for item in _task_items(body):
        creation_chain = False
        previous_end = 0
        seen_in_item: set[str] = set()
        for start, end, raw in _candidate_matches(item):
            candidate = _normalise_cited_path(raw)
            if candidate is None or candidate in seen_in_item:
                continue
            seen_in_item.add(candidate)
            # The path must be the direct object of an explicit file-creation
            # phrase.  "Add validation to missing/a.py" modifies a cited file;
            # it does not declare that file as new.
            prefix = item[:start].rstrip("`")
            if _EXPLICIT_CREATE_PREFIX.search(prefix):
                creation_chain = True
            elif creation_chain:
                separator = item[previous_end:start]
                creation_chain = bool(
                    re.fullmatch(r"\s*(?:[,;]\s*)?(?:(?:and|or)\s+)?", separator, re.I)
                )
            if creation_chain:
                created.add(candidate)
            previous_end = end
    return created


def _search_roots(repo_root: Path) -> list[Path]:
    """`repo_root` plus the conventional source roots, and packages under them.

    Issues routinely cite a path relative to the package rather than the repo —
    `collect/quality.py` for `src/fine_art_archive/collect/quality.py`. Treating
    those as missing would fill the advisory with false alarms and, worse, make
    `resolved` undercount, which is what the failure rule keys on.
    """
    roots = [repo_root]
    for name in ("src", "lib", "app", "packages"):
        base = repo_root / name
        if not base.is_dir():
            continue
        roots.append(base)
        # One level deeper covers the src/<package>/ layout. Bounded so a large
        # monorepo cannot turn this into a directory walk.
        with contextlib.suppress(OSError):
            roots.extend(sorted(p for p in base.iterdir() if p.is_dir())[:12])
    return roots


def _resolve_citations(body: str, repo_root: Path) -> tuple[list[str], list[str]]:
    """Split cited paths into (resolved, unresolved) against `repo_root`."""
    roots = _search_roots(repo_root)
    resolved: list[str] = []
    unresolved: list[str] = []
    for candidate in _cited_paths(body):
        found = any((root / candidate).exists() for root in roots)
        (resolved if found else unresolved).append(candidate)
    return resolved, unresolved


def _list_content_indent(line: str) -> int | None:
    """Return the content indentation established by a Markdown list marker."""
    match = re.match(r"^( {0,3})(?:[-+*]|\d+[.)]) +", line)
    return match.end() if match else None


def _fence_match(line: str, list_indent: int | None) -> re.Match[str] | None:
    """Match a Markdown fence, including a fence nested in the current list."""
    match = re.match(r"^( *)(`{3,}|~{3,})", line)
    if match is None:
        return None
    indent = len(match.group(1))
    if indent <= 3:
        return match
    if list_indent is not None and list_indent <= indent <= list_indent + 3:
        return match
    return None


def _headings(body: str) -> list[tuple[str, int, int]]:
    """Return markdown headings outside fenced code blocks with line indexes."""
    out: list[tuple[str, int, int]] = []
    fence: tuple[str, int] | None = None
    list_indent: int | None = None
    for i, line in enumerate(body.splitlines()):
        if (new_list_indent := _list_content_indent(line)) is not None:
            list_indent = new_list_indent
        elif (
            line.strip()
            and fence is None
            and len(line) - len(line.lstrip(" ")) < (list_indent or 0)
        ):
            list_indent = None
        fence_match = _fence_match(line, list_indent)
        if fence_match:
            marker = fence_match.group(2)
            if fence is None:
                fence = (marker[0], len(marker))
            elif (
                marker[0] == fence[0]
                and len(marker) >= fence[1]
                and not line[fence_match.end() :].strip()
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
    list_indent: int | None = None
    for line in text.splitlines():
        if (new_list_indent := _list_content_indent(line)) is not None:
            list_indent = new_list_indent
        elif (
            line.strip()
            and fence is None
            and len(line) - len(line.lstrip(" ")) < (list_indent or 0)
        ):
            list_indent = None
        match = _fence_match(line, list_indent)
        if match:
            marker = match.group(2)
            if fence is None:
                fence = (marker[0], len(marker))
            elif (
                marker[0] == fence[0]
                and len(marker) >= fence[1]
                and not line[match.end() :].strip()
            ):
                # Closing fences are marker-only (optional whitespace); trailing
                # content such as a language tag must not end the fence.
                fence = None
            continue
        if fence is None:
            kept.append(line)
    return "\n".join(kept)


def _strip_original_issue_blocks(text: str) -> str:
    """Remove only the formatter's canonical fenced provenance block."""
    return _ORIGINAL_ISSUE_BLOCK_RE.sub("", text).rstrip()


@dataclass
class Report:
    ok: bool = True
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)

    def as_markdown(self) -> str:
        if self.ok and not self.missing_recommended and not self.advisories:
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
        if self.advisories:
            out.extend(["", "_Advisory:_"])
            out.extend(f"- {advisory}" for advisory in self.advisories)
        if self.missing_recommended:
            out.extend(
                [
                    "",
                    "_Recommended but absent:_ "
                    + ", ".join(f"`{section}`" for section in self.missing_recommended),
                ]
            )
        return "\n".join(out)


def validate(body: str, repo_root: Path | None = None) -> Report:
    """Check an issue body; every structural format problem is non-conforming.

    `repo_root`, when given, additionally checks that the paths the body cites
    actually exist there — see the Addressability block above. It is optional so
    the validator stays a pure body check for callers that have no checkout.
    """
    report = Report()
    body = _strip_original_issue_blocks(body or "")
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
        else:
            offending_item = next(
                (item for item in task_items if not _task_has_concrete_target(item)), None
            )
            if offending_item is not None:
                preview = " ".join(offending_item.split())[:160]
                report.problems.append(
                    "`Tasks` item must name a concrete file, symbol, path, config key, job, or "
                    f"command: `{preview}`."
                )

    acceptance_at = _find(body, REQUIRED["Acceptance Criteria"])
    if acceptance_at is not None:
        acceptance = _section_text(body, acceptance_at)
        acceptance_prose = _without_fenced_code(acceptance)
        if not GATE.search(acceptance_prose):
            report.problems.append(
                "`Acceptance Criteria` names no test, runnable command or observable "
                "verification gate — Definition of Ready / Quality Bar §2 requires one."
            )
        prose = re.sub(r"(?<!`)`(?!`)[^`\n]*`", "", acceptance_prose)
        # Only discard tokens that are demonstrably file paths.  A broad
        # slash-separated-word pattern would also erase subjective prose such
        # as "fast/performant" before the adjective check sees it.
        prose = re.sub(
            r"(?<![\w/])(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,10}\b",
            "",
            prose,
        )
        # The measurable exit-status idiom "exits clean" is allowed, but only
        # that phrase is exempt: another subjective use of "clean" in the same
        # criterion must remain visible to the adjective check.
        adjective_prose = re.sub(r"\b(?:exit|exits|exited)\s+clean\b", "", prose, flags=re.I)
        hits = [
            word for word in BANNED_ADJECTIVES if re.search(rf"\b{word}\b", adjective_prose, re.I)
        ]
        if hits:
            report.problems.append(
                "`Acceptance Criteria` uses subjective wording ("
                + ", ".join(sorted(hits))
                + "); replace with a measurable check."
            )
    if repo_root is not None:
        resolved, unresolved = _resolve_citations(body, repo_root)
        unresolved_evidence = [path for path in unresolved if path not in _created_paths(body)]
        cited = len(resolved) + len(unresolved_evidence)
        if cited >= _MIN_CITATIONS_TO_JUDGE and not resolved:
            report.problems.append(
                f"None of the {cited} paths this issue cites exist in this repository "
                f"({', '.join(f'`{p}`' for p in unresolved_evidence[:6])}"
                + (", …" if cited > 6 else "")
                + "). An agent cloning this repo has nothing to act on. File it "
                "against the repo that holds the code, or cite the evidence here."
            )
        elif unresolved:
            report.advisories.append(
                f"{len(unresolved)} cited path(s) do not exist yet: "
                + ", ".join(f"`{p}`" for p in unresolved[:6])
                + (", …" if len(unresolved) > 6 else "")
                + " — expected when a task creates them; check for typos otherwise."
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
    # CI runs this after `actions/checkout`, so the working directory IS the
    # repo the issue was filed against — which is exactly what addressability
    # must be judged against.
    report = validate(body, repo_root=Path.cwd())
    print(report.as_markdown())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
