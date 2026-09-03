"""Keep keepalive label documentation tied to an executable surface (#3330)."""

import re
from pathlib import Path

DOCS = (
    Path("docs/LABELS.md"),
    Path("docs/keepalive/GoalsAndPlumbing.md"),
)
RETIRED_HEADING = "### Retired label names"


def _documented_labels() -> set[str]:
    labels: set[str] = set()
    for path in DOCS:
        labels.update(re.findall(r"`((?:agents|agent):[A-Za-z0-9:_<>-]+)", path.read_text()))
    return labels


def _documentation_only_labels() -> set[str]:
    retired = Path("docs/LABELS.md").read_text().split(RETIRED_HEADING, maxsplit=1)[1]
    retired = retired.split("\n---", maxsplit=1)[0]
    return set(re.findall(r"`((?:agents|agent):[A-Za-z0-9:_<>-]+)", retired))


def _automation_surface() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in Path(".github").rglob("*") if path.is_file()
    )


def _source_token(label: str) -> str:
    if label == "agent:<name>":
        return "agent:"
    if label == "agent:<name>-invite":
        return "-invite"
    return label.replace("<K>", "")


def test_documented_keepalive_labels_have_an_executable_or_retired_surface() -> None:
    """A documented control must execute somewhere or be explicitly retired."""
    surface = _automation_surface()
    documentation_only = _documentation_only_labels()
    missing = sorted(
        label
        for label in _documented_labels() - documentation_only
        if _source_token(label) not in surface
    )
    assert not missing, f"documented labels lack an automation surface: {missing}"


def test_max_parallel_is_explicitly_retired_not_an_undocumented_noop() -> None:
    """Deliberate-break shape: a retired promise must remain visibly retired."""
    assert "agents:max-parallel:<K>" in _documentation_only_labels()
