"""The guard's payload matcher, exercised against the artifact names the fleet really publishes.

The rule this pins is not "does the regex compile" — it is that the matcher accepts the shape the
PRODUCER actually emits. Measured 2026-08-30 across the lane fleet, eight repos published a trend,
a summary and two matrix-suffixed payloads (`gate-coverage-3.12-1`, `gate-coverage-3.13-1`) — every
artifact the guard needs — and the guard skipped all of them, because it matched two exact names.
It had a failing run in all thirteen repos.

The matcher is JavaScript embedded in a YAML workflow, so the test extracts it and runs it under
node rather than reimplementing the rule in Python: two implementations of one rule drift, and a
Python copy would keep passing while the shipped matcher broke.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDS = (
    REPO_ROOT / ".github/workflows/maint-coverage-guard.yml",
    REPO_ROOT / "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
)

# The names each repo's Gate published on 2026-08-30. Recorded rather than invented: a fixture of
# imagined names is what let the exact-match list look correct for as long as it did.
FLEET_ARTIFACTS = {
    "eight-repos-matrix": [
        "gate-coverage-trend-history",
        "gate-coverage-trend",
        "gate-coverage-summary",
        "gate-coverage-3.12-1",
        "gate-coverage-3.13-1",
    ],
    "counter-risk-no-trend": ["gate-coverage-3.13-1", "gate-coverage-3.12-1"],
    "orchestrator-both-shapes": [
        "gate-coverage-summary.md",
        "gate-coverage",
        "gate-coverage-trend-history",
        "gate-coverage-3.13-1",
        "gate-coverage-trend",
        "gate-coverage-summary",
        "gate-coverage-3.12-1",
    ],
    "legacy-exact-json": ["gate-coverage.json", "gate-coverage-delta.json", "gate-coverage-trend"],
    "no-coverage-at-all": ["build-log", "pytest-report"],
}


def _matcher_source(path: Path) -> str:
    """Lift the matcher out of the workflow, dedented to column zero."""
    text = path.read_text(encoding="utf-8")
    start = text.index("const coveragePayloadNames = [")
    end = text.index("};", text.index("const payloadCandidates")) + 2
    return textwrap.dedent(text[start:end])


def _run(path: Path, names: list[str]) -> list[str]:
    script = (
        _matcher_source(path)
        + "\nconsole.log(JSON.stringify(payloadCandidates(new Set("
        + json.dumps(names)
        + "))));\n"
    )
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not installed, so the guard's embedded matcher cannot be executed",
)


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_the_matrix_suffixed_payload_the_producer_really_emits_is_matched(guard):
    """The whole defect, in one assertion."""
    assert _run(guard, FLEET_ARTIFACTS["eight-repos-matrix"])[0] == "gate-coverage-3.12-1"


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_the_trend_is_never_mistaken_for_the_payload(guard):
    """A bare prefix match would compare coverage against itself.

    `gate-coverage-trend`, `-trend-history`, `-summary` and `-delta` all carry the payload's
    prefix, so the exclusion is what stops the fix from being worse than the defect.
    """
    non_payloads = ["gate-coverage-trend", "gate-coverage-summary", "gate-coverage-delta.json"]
    assert _run(guard, non_payloads) == []


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_a_repo_where_the_exact_name_already_worked_is_untouched(guard):
    """Back-compat is not a nicety here: it is what keeps this from being a second migration."""
    assert _run(guard, FLEET_ARTIFACTS["orchestrator-both-shapes"])[0] == "gate-coverage"
    assert _run(guard, FLEET_ARTIFACTS["legacy-exact-json"])[0] == "gate-coverage.json"


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_a_repo_publishing_no_coverage_still_matches_nothing(guard):
    """The one case where "coverage is not measured here" is the true finding."""
    assert _run(guard, FLEET_ARTIFACTS["no-coverage-at-all"]) == []


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_the_choice_does_not_depend_on_the_api_listing_order(guard):
    """Two interpreters, two payloads, one figure — which must not move for no reason.

    The artifacts API does not promise an order, and one repo already returns these two reversed
    relative to the others, so an unsorted match would make a repo's reported coverage flip between
    interpreters run to run.
    """
    forward = _run(guard, ["gate-coverage-3.12-1", "gate-coverage-3.13-1"])
    reverse = _run(guard, ["gate-coverage-3.13-1", "gate-coverage-3.12-1"])
    assert forward == reverse


def test_both_copies_carry_the_same_matcher():
    """Root and consumer diverging here is the original defect's own mechanism."""
    assert _matcher_source(GUARDS[0]) == _matcher_source(GUARDS[1])


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_the_failure_message_can_say_measured_under_an_unusable_name(guard):
    """ "Not measured" and "measured, unusable name" are opposite findings with different fixes.

    The message this replaced asserted the first in every case, which is how eight repos that were
    measuring coverage were told to go and switch coverage on.
    """
    text = guard.read_text(encoding="utf-8")
    assert "seenCoverageArtifacts.size === 0" in text, "the two findings must be branched apart"
    assert "Coverage IS being measured in this repo" in text
