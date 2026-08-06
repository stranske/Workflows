"""Validate a GitHub issue body against the fleet's AGENT_ISSUE_FORMAT contract.

Synced to every consumer repo by `maint-68-sync-consumer-repos.yml`. This is the
single definition of "agent-processable" for the whole fleet — do not fork it
per repo.

Why it exists: every automated lane reaches an issue through a LABEL. An issue
filed with no label and no Tasks/Acceptance block is invisible to the entire
pipeline — nothing validates it, nothing optimises it, nothing claims it. Local
automation that files findings rather than work orders therefore produces issues
no agent can ever pick up. (Observed in Fine-Art-Archive #406-409: four
well-evidenced audit findings, zero labels, no Tasks section between them.)

Used at both ends:
  * `agents-issue-format-guard.yml` validates every issue on open/edit and, on
    failure, applies `agents:format` — the label the existing Agents Issue
    Optimizer already listens for — so a bad issue is ROUTED to the machinery
    that repairs it rather than merely flagged;
  * any local script that files issues can pre-flight with
    `python .github/scripts/issue_format.py <body-file>` and refuse to file junk
    (non-zero exit means unfit).

Rules mirror docs/AGENT_ISSUE_FORMAT.md rather than inventing a parallel
standard: Tasks and Acceptance Criteria are REQUIRED; Why / Scope / Non-Goals are
recommended; and at least one acceptance criterion must name a real test,
runnable command, or observable verification gate.

Pure stdlib on purpose — it must run on a bare runner with no install step.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

# Section name -> accepted aliases, from the guide's Required/Recommended tables.
REQUIRED: dict[str, tuple[str, ...]] = {
    "Tasks": ("tasks", "task list", "implementation"),
    "Acceptance Criteria": ("acceptance criteria", "acceptance", "definition of done"),
}
RECOMMENDED: dict[str, tuple[str, ...]] = {
    "Why": ("why", "goals", "summary", "motivation", "finding"),
    "Scope": ("scope", "background", "context", "overview"),
    "Non-Goals": ("non-goals", "out of scope", "constraints"),
}
# A qualifying gate names a test path/id, a runner command, or a verification
# token. Deliberately conservative and string-based, matching the guide's
# "Enforcement note".
GATE = re.compile(
    r"(tests?/[\w./-]+\.py(::[\w:\[\]-]+)?"  # a test path, optionally ::id
    r"|\btest_[\w]+"  # a test function name
    r"|\bpytest\b|\bnpm test\b|\bmake test\b"  # runners
    r"|gh workflow run\b|gh run \b"  # CI invocation
    r"|\bcurl\b.*\bHTTP\b|\bHTTP [1-5]\d\d\b"  # observable HTTP result
    r"|\bsmoke\b|\bverif)",  # smoke / verify tokens
    re.I,
)
# Subjective words the guide bans as acceptance criteria.
BANNED_ADJECTIVES = ("clean", "nice", "good", "fast", "better", "intuitive", "polished")


def _headings(body: str) -> list[tuple[str, int]]:
    """(normalised heading text, line index) for every markdown heading."""
    out = []
    for i, line in enumerate(body.splitlines()):
        m = re.match(r"\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            out.append((m.group(2).strip().strip(":").lower(), i))
    return out


def _find(body: str, aliases: tuple[str, ...]) -> int | None:
    for text, idx in _headings(body):
        for alias in aliases:
            # Match the heading if it *starts with* the alias, so
            # "Acceptance Criteria (all must hold)" still counts.
            if text == alias or text.startswith(alias):
                return idx
    return None


def _section_text(body: str, start: int) -> str:
    """Text from the heading at `start` up to the next heading of any level."""
    lines = body.splitlines()
    idxs = [i for _, i in _headings(body) if i > start]
    end = idxs[0] if idxs else len(lines)
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
        out = [
            "This issue is **not yet agent-processable**. " "See `docs/AGENT_ISSUE_FORMAT.md`.",
            "",
        ]
        if self.missing_required:
            out.append(
                "**Missing required sections:** "
                + ", ".join(f"`{s}`" for s in self.missing_required)
            )
        for p in self.problems:
            out.append(f"- {p}")
        if self.missing_recommended:
            out.append("")
            out.append(
                "_Recommended but absent:_ " + ", ".join(f"`{s}`" for s in self.missing_recommended)
            )
        return "\n".join(out)


def validate(body: str) -> Report:
    """Check an issue body. `ok` is False only for REQUIRED failures."""
    r = Report()
    body = body or ""

    for name, aliases in REQUIRED.items():
        if _find(body, aliases) is None:
            r.missing_required.append(name)
    for name, aliases in RECOMMENDED.items():
        if _find(body, aliases) is None:
            r.missing_recommended.append(name)

    tasks_at = _find(body, REQUIRED["Tasks"])
    if tasks_at is not None:
        text = _section_text(body, tasks_at)
        if not re.search(r"^\s*[-*]\s*\[[ xX]\]", text, re.M):
            r.problems.append(
                "`Tasks` has no checkbox items (`- [ ] …`); agents track progress by them."
            )

    acc_at = _find(body, REQUIRED["Acceptance Criteria"])
    if acc_at is None:
        r.problems.append(
            "No `Acceptance Criteria` section, so there is no named test gate "
            "(format guide §2 requires at least one)."
        )
    else:
        text = _section_text(body, acc_at)
        if not GATE.search(text):
            r.problems.append(
                "`Acceptance Criteria` names no test, runnable command or "
                "observable verification gate — format guide §2 requires at least "
                "one (a test path/id, a runner command and its expected result, or "
                "a documented live-verification step)."
            )
        hits = [w for w in BANNED_ADJECTIVES if re.search(rf"\b{w}\b", text, re.I)]
        if hits:
            r.problems.append(
                "`Acceptance Criteria` uses subjective wording ("
                + ", ".join(sorted(hits))
                + "); replace with a measurable check."
            )

    r.ok = not r.missing_required and not any(
        p.startswith(("`Acceptance Criteria` names no", "No `Acceptance Criteria`"))
        for p in r.problems
    )
    return r


def main(argv: list[str] | None = None) -> int:
    """CLI: validate a body from a file or stdin. Non-zero exit means unfit."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        with open(argv[0], encoding="utf-8") as fh:
            body = fh.read()
    else:
        body = sys.stdin.read()
    report = validate(body)
    print(report.as_markdown())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
