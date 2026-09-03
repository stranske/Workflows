"""Keep keepalive label documentation tied to an executable surface (#3330)."""

import re
from pathlib import Path

DOCS = (
    Path("docs/LABELS.md"),
    Path("docs/keepalive/GoalsAndPlumbing.md"),
)
RETIRED_HEADING = "### Retired label names"
RETIRED_LABELS = {"agents:max-parallel:<K>", "agent:codex-invite"}
DISABLED_LABELS = {"agent:aider"}
AUTOMATION_ROOTS = (Path(".github/workflows"), Path(".github/scripts"))
AUTOMATION_SUFFIXES = {".js", ".py", ".sh", ".yml", ".yaml"}
SWEEP_PATHS = (
    Path(".github/workflows/agents-keepalive-sweep.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-keepalive-sweep.yml"),
)


def _documented_labels() -> set[str]:
    labels: set[str] = set()
    for path in DOCS:
        labels.update(re.findall(r"`((?:agents|agent):[A-Za-z0-9:_<>-]+)", path.read_text()))
    return labels


def _documentation_only_labels() -> set[str]:
    retired = Path("docs/LABELS.md").read_text().split(RETIRED_HEADING, maxsplit=1)[1]
    retired = retired.split("\n---", maxsplit=1)[0]
    documented = set(re.findall(r"`((?:agents|agent):[A-Za-z0-9:_<>-]+)", retired))
    return documented & RETIRED_LABELS


def _automation_surface() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for root in AUTOMATION_ROOTS
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and path.suffix in AUTOMATION_SUFFIXES
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
    documentation_only = _documentation_only_labels() | DISABLED_LABELS
    missing = sorted(
        label
        for label in _documented_labels() - documentation_only
        if _source_token(label) not in surface
    )
    assert not missing, f"documented labels lack an automation surface: {missing}"


def test_max_parallel_is_explicitly_retired_not_an_undocumented_noop() -> None:
    """Deliberate-break shape: a retired promise must remain visibly retired."""
    assert "agents:max-parallel:<K>" in _documentation_only_labels()


def test_retired_section_does_not_exempt_active_replacement_labels() -> None:
    """Replacement labels mentioned beside retirements remain executable."""
    assert "agents:max-runs:<K>" not in _documentation_only_labels()
    assert "agent:<name>-invite" not in _documentation_only_labels()


def test_disabled_labels_are_explicitly_documented_as_non_executable() -> None:
    """A reserved label needs an explicit no-dispatch contract until implemented."""
    labels_doc = Path("docs/LABELS.md").read_text()
    assert "`agent:aider` is reserved and disabled" in labels_doc
    assert re.search(r"will not\s+dispatch a runner", labels_doc)


def test_keepalive_sweeps_normalize_the_opt_in_label_before_filtering() -> None:
    """All sweep modes normalize labels and require an executable routing label."""
    root_workflow = SWEEP_PATHS[0].read_text(encoding="utf-8")
    consumer_workflow = SWEEP_PATHS[1].read_text(encoding="utf-8")
    assert root_workflow.count("(label.name || '').toLowerCase()") == 2
    assert consumer_workflow.count("(label.name || '').toLowerCase()") == 4
    required_snippets = (
        "labelNames.includes('agents:keepalive')",
        "const routingLabels = labelNames.filter",
        "'agent:aider', 'agent:needs-attention', 'agent:rate-limited', 'agent:retry'",
        "(label.name || '').toLowerCase() === 'agent:needs-attention'",
    )
    for snippet in required_snippets:
        assert root_workflow.count(snippet) == 1
        assert consumer_workflow.count(snippet) == 2


def test_run_cap_docs_state_the_executable_bounds() -> None:
    """The operator docs must disclose parseRunCap's 1–5 effective range."""
    labels_doc = Path("docs/LABELS.md").read_text(encoding="utf-8")
    assert "Supported nonzero values are `K = 1–5`" in labels_doc
    assert "Values above 5 are clamped to an effective cap of 5" in labels_doc
