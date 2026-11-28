"""Workflows that run here keep third-party code pinned (OpenSSF Scorecard, 2026-11-28).

Scorecard's Pinned-Dependencies check flags two kinds of supply-chain exposure that
the owner decided to fix and keep at zero:

* a third-party action referenced by a movable tag instead of a full commit SHA
  (GitHub-owned ``actions/*`` and ``github/*`` tag pins and this repository's own
  ``stranske/Workflows/...@main`` reusable calls are deliberately out of scope);
* a script downloaded and piped straight into a shell (``curl ... | sh``).

Health 40 counts any new open Scorecard alert of these kinds; this test stops one
from being merged in the first place.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIRS = (
    ROOT / ".github" / "workflows",
    ROOT / "templates" / "consumer-repo" / ".github" / "workflows",
)
FIRST_PARTY_OWNERS = {"actions", "github"}
OWN_REUSABLE_PREFIX = "stranske/Workflows/"
SHA_PIN = re.compile(r"^[0-9a-f]{40}$")
PIPE_TO_SHELL = re.compile(r"\b(?:curl|wget)\b[^\n|#]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b")


def _workflow_files() -> list[Path]:
    files: list[Path] = []
    for directory in WORKFLOW_DIRS:
        files.extend(sorted(directory.glob("*.yml")))
        files.extend(sorted(directory.glob("*.yaml")))
    return files


def _uses_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses" and isinstance(value, str):
                yield value.strip()
            else:
                yield from _uses_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _uses_refs(item)


def _run_scripts(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run" and isinstance(value, str):
                yield value
            else:
                yield from _run_scripts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _run_scripts(item)


def unpinned_third_party(uses: str) -> bool:
    if uses.startswith(("./", "docker://")) or "@" not in uses:
        return False
    if uses.startswith(OWN_REUSABLE_PREFIX):
        return False
    target, ref = uses.rsplit("@", 1)
    if target.split("/", 1)[0] in FIRST_PARTY_OWNERS:
        return False
    return not SHA_PIN.match(ref)


def _offences() -> list[str]:
    offences = []
    for path in _workflow_files():
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        rel = path.relative_to(ROOT)
        offences.extend(f"{rel}: {uses}" for uses in _uses_refs(data) if unpinned_third_party(uses))
        for script in _run_scripts(data):
            offences.extend(f"{rel}: {m.group(0)}" for m in PIPE_TO_SHELL.finditer(script))
    return offences


def test_workflows_pin_third_party_actions_and_never_pipe_downloads_to_a_shell():
    offences = _offences()
    assert offences == [], "\n".join(offences)


def test_the_scan_reads_real_workflows():
    files = _workflow_files()
    assert len(files) > 50
    refs = [
        uses
        for path in files
        for uses in _uses_refs(yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader))
    ]
    assert any(ref.startswith("peter-evans/create-pull-request@") for ref in refs)
    assert any(ref.startswith("astral-sh/setup-uv@") for ref in refs)


@pytest.mark.parametrize(
    ("uses", "flagged"),
    [
        ("peter-evans/create-pull-request@v8", True),
        ("peter-evans/create-pull-request@3ffccacd46053766916f087ce41d627c0b8cf2d1", False),
        ("actions/checkout@v7", False),
        ("github/codeql-action/upload-sarif@v4", False),
        ("stranske/Workflows/.github/workflows/reusable-codex-run.yml@main", False),
        ("stranske/other/.github/workflows/x.yml@main", True),
        ("./.github/workflows/reusable-10-ci-python.yml", False),
        ("docker://alpine:3", False),
    ],
)
def test_classifier(uses, flagged):
    assert unpinned_third_party(uses) is flagged


@pytest.mark.parametrize(
    ("script", "flagged"),
    [
        ("curl -LsSf https://astral.sh/uv/install.sh | sh", True),
        ('curl -sSL "$url" | sh -s -- -b dir v1', True),
        ("wget -qO- https://x | sudo bash", True),
        ('curl -sSLf -o "$f" "$url"\necho "$sum  $f" | sha256sum --check -', False),
        ('curl -sSL "$url" | tar -xz -C dir actionlint', False),
    ],
)
def test_pipe_to_shell_pattern(script, flagged):
    assert bool(PIPE_TO_SHELL.search(script)) is flagged
