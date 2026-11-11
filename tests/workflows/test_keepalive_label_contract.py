"""Keep keepalive label documentation tied to an executable surface (#3330)."""

import re
from pathlib import Path

DOCS = (
    Path("docs/LABELS.md"),
    Path("docs/keepalive/GoalsAndPlumbing.md"),
)
RETIRED_HEADING = "### Retired label names"
RETIRED_LABELS = {"agents:max-parallel:<K>", "agent:codex-invite", "agent:aider"}
DISABLED_LABELS: set[str] = set()
# Labels whose executable surface is local automation outside this repository, named here so the exemption is
# deliberate. Each must say in docs/LABELS.md which local system owns it.
LOCAL_AUTOMATION_LABELS = {"agents:local-loop": "stranske/Orchestrator"}
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
    return label.replace("<K>", "").replace("<agent>", "")


def test_documented_keepalive_labels_have_an_executable_or_retired_surface() -> None:
    """A documented control must execute somewhere or be explicitly retired."""
    surface = _automation_surface()
    documentation_only = (
        _documentation_only_labels() | DISABLED_LABELS | set(LOCAL_AUTOMATION_LABELS)
    )
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


def test_retired_aider_label_has_no_runner_or_registry_entry() -> None:
    """agent:aider is retired (2026-11-11): documented as retired and absent from every registry."""
    labels_doc = Path("docs/LABELS.md").read_text()
    assert "`agent:aider` is retired" in labels_doc
    for registry in (
        Path(".github/agents/registry.yml"),
        Path("templates/consumer-repo/.github/agents/registry.yml"),
    ):
        assert "\n  aider:\n" not in registry.read_text()


def test_keepalive_sweeps_normalize_the_opt_in_label_before_filtering() -> None:
    """All sweep modes normalize labels and require an executable routing label."""
    root_workflow = SWEEP_PATHS[0].read_text(encoding="utf-8")
    consumer_workflow = SWEEP_PATHS[1].read_text(encoding="utf-8")
    assert root_workflow.count("(label.name || '').toLowerCase()") == 2
    assert consumer_workflow.count("(label.name || '').toLowerCase()") == 4
    required_snippets = (
        "labelNames.includes('agents:keepalive')",
        "const routingLabels = labelNames.filter",
        "'agent:needs-attention', 'agent:rate-limited', 'agent:retry'",
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


def test_local_automation_labels_name_their_owner() -> None:
    """The local-automation exemption is not silent: each label's section names the system that executes it."""
    doc = Path("docs/LABELS.md").read_text()
    for label, owner in LOCAL_AUTOMATION_LABELS.items():
        heading = f"### `{label}`"
        assert heading in doc, f"{label} has no section in docs/LABELS.md"
        section = doc.split(heading, maxsplit=1)[1].split("\n---", maxsplit=1)[0]
        assert owner in section, f"{label}'s section does not name its owner {owner}"
