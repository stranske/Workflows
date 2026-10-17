"""Hermetic replays for rate-limited completion → label-timeline agent switches."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "agent_switch_cadence", "scripts/agent_switch_cadence.py"
)
cadence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cadence)

REPO = "stranske/Workflows"


def _same_evaluate_snapshot() -> dict:
    """Replayed rate-limited completion with same-evaluate label timeline."""
    t0 = "2026-10-17T09:00:00Z"
    t1 = "2026-10-17T09:00:01Z"
    return {
        "collection": {"history_complete": True, "limitations": ["fixture replay"]},
        "completions": [
            {
                "repo": REPO,
                "pr": 3989,
                "provider": "codex",
                "completed_at": t0,
                "completion": {"reason": "rate_limited"},
            }
        ],
        "label_events": [
            {
                "repo": REPO,
                "pr": 3989,
                "event": "labeled",
                "label": "agent:rate-limited",
                "created_at": t1,
            },
            {
                "repo": REPO,
                "pr": 3989,
                "event": "labeled",
                "label": "agents:tried-codex",
                "created_at": t1,
            },
            {
                "repo": REPO,
                "pr": 3989,
                "event": "unlabeled",
                "label": "agent:codex",
                "created_at": t1,
            },
            {
                "repo": REPO,
                "pr": 3989,
                "event": "labeled",
                "label": "agent:cursor",
                "created_at": t1,
            },
        ],
        "open_prs": [
            {
                "repo": REPO,
                "pr": 3989,
                "labels": ["agent:auto", "agent:cursor", "agents:keepalive"],
            }
        ],
    }


def test_same_evaluate_rate_limited_switch_is_visible_on_label_timeline():
    report = cadence.calculate(_same_evaluate_snapshot())
    assert report["metrics"]["rate_limited_events"] == 1
    assert report["metrics"]["median_additional_rounds"] == 0.0
    assert report["metrics"]["passes_same_evaluate_median"] is True
    row = report["rows"][0]
    assert row["reason"] == "rate_limited"
    assert row["provider"] == "codex"
    assert row["switch_agent"] == "cursor"
    assert row["additional_rounds"] == 0
    assert row["same_evaluate"] is True
    labels = {entry["label"] for entry in row["label_timeline"]}
    assert "agent:cursor" in labels
    assert "agent:rate-limited" in labels
    assert "agents:tried-codex" in labels
    table = cadence.markdown(report)
    assert "| Reason |" in table
    assert "rate_limited" in table
    assert "## Label timelines" in table
    assert "labeled `agent:cursor`" in table
    assert "labeled `agent:rate-limited`" in table


def test_evaluate_actions_replay_pairs_same_evaluate_switch_on_label_timeline():
    """Post-#3997 replay: keepalive evaluate mutations → cadence label timeline."""
    # Action sequence asserted by keepalive-loop same-evaluate quota regression.
    actions = [
        {"type": "label", "labels": ["agent:rate-limited"]},
        {"type": "label", "labels": ["agents:tried-codex"]},
        {"type": "remove-label", "name": "agent:codex"},
        {"type": "label", "labels": ["agent:cursor"]},
    ]
    snapshot = cadence.snapshot_from_rate_limit_evaluate(
        repo=REPO,
        pr=3989,
        provider="codex",
        completed_at="2026-10-17T08:05:00Z",
        switch_at="2026-10-17T08:05:01Z",
        actions=actions,
        open_labels=["agent:auto", "agent:cursor", "agents:keepalive", "agent:rate-limited"],
    )
    events = cadence.label_events_from_evaluate_actions(
        actions, repo=REPO, pr=3989, at="2026-10-17T08:05:01Z"
    )
    assert [event["event"] for event in events] == [
        "labeled",
        "labeled",
        "unlabeled",
        "labeled",
    ]
    report = cadence.calculate(snapshot)
    assert report["metrics"]["passes_same_evaluate_median"] is True
    row = report["rows"][0]
    assert row["same_evaluate"] is True
    assert row["additional_rounds"] == 0
    assert row["switch_agent"] == "cursor"
    timeline = {(entry["event"], entry["label"]) for entry in row["label_timeline"]}
    assert ("labeled", "agent:cursor") in timeline
    assert ("labeled", "agent:rate-limited") in timeline
    assert ("labeled", "agents:tried-codex") in timeline
    assert ("unlabeled", "agent:codex") in timeline
    rendered = cadence.markdown(report)
    assert "### stranske/Workflows#3989 (codex → cursor)" in rendered
    assert "`2026-10-17T08:05:01Z` labeled `agent:cursor`" in rendered
    assert "`2026-10-17T08:05:01Z` unlabeled `agent:codex`" in rendered


def test_progressed_open_prs_without_rate_limited_marker_are_clean(tmp_path: Path):
    snapshot = {
        "completions": [
            {
                "repo": REPO,
                "pr": 4029,
                "provider": "cursor",
                "completed_at": "2026-10-17T09:00:00Z",
                "completion": {"reason": "progressed"},
            }
        ],
        "open_prs": [
            {
                "repo": REPO,
                "pr": 4029,
                "labels": ["agent:auto", "agent:cursor", "agents:keepalive"],
            }
        ],
    }
    report = cadence.calculate(snapshot)
    assert report["metrics"]["stale_rate_limited_on_progressed"] == 0
    assert report["stale_rate_limited_on_progressed"] == []
    inp = tmp_path / "clean.json"
    inp.write_text(json.dumps(snapshot), encoding="utf-8")
    assert cadence.main(["--input", str(inp)]) == 0


def test_intervening_rounds_inflate_additional_rounds_above_zero():
    snapshot = {
        "completions": [
            {
                "repo": REPO,
                "pr": 1,
                "provider": "codex",
                "completed_at": "2026-10-17T09:00:00Z",
                "reason": "rate_limited",
            },
            {
                "repo": REPO,
                "pr": 1,
                "provider": "codex",
                "completed_at": "2026-10-17T10:00:00Z",
                "reason": "no_progress",
            },
            {
                "repo": REPO,
                "pr": 1,
                "provider": "codex",
                "completed_at": "2026-10-17T11:00:00Z",
                "reason": "no_progress",
            },
        ],
        "label_events": [
            {
                "repo": REPO,
                "pr": 1,
                "event": "labeled",
                "label": "agent:claude",
                "created_at": "2026-10-17T11:05:00Z",
            }
        ],
    }
    report = cadence.calculate(snapshot)
    assert report["rows"][0]["additional_rounds"] == 2
    assert report["metrics"]["median_additional_rounds"] == 2.0
    assert report["metrics"]["passes_same_evaluate_median"] is False


def test_stale_rate_limited_marker_on_progressed_open_pr():
    snapshot = {
        "completions": [
            {
                "repo": REPO,
                "pr": 7,
                "provider": "cursor",
                "completed_at": "2026-10-17T12:00:00Z",
                "completion": {"reason": "progressed"},
            }
        ],
        "open_prs": [
            {
                "repo": REPO,
                "pr": 7,
                "labels": [
                    "agent:auto",
                    "agent:cursor",
                    "agent:rate-limited",
                    "agents:keepalive",
                ],
            },
            {
                "repo": REPO,
                "pr": 8,
                "labels": ["agent:cursor", "agents:keepalive"],
            },
        ],
    }
    report = cadence.calculate(snapshot)
    assert report["metrics"]["stale_rate_limited_on_progressed"] == 1
    assert report["stale_rate_limited_on_progressed"][0]["pr"] == 7


def test_cli_same_evaluate_replay_exits_zero(tmp_path: Path):
    inp = tmp_path / "snap.json"
    inp.write_text(json.dumps(_same_evaluate_snapshot()), encoding="utf-8")
    json_out = tmp_path / "out.json"
    md_out = tmp_path / "out.md"
    assert (
        cadence.main(
            ["--input", str(inp), "--json-out", str(json_out), "--markdown-out", str(md_out)]
        )
        == 0
    )
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["metrics"]["passes_same_evaluate_median"] is True
    assert "rate_limited" in md_out.read_text(encoding="utf-8")
    assert "## Label timelines" in md_out.read_text(encoding="utf-8")


def test_committed_evaluate_actions_fixture_replays_visible_label_timeline(tmp_path: Path):
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "agent_switch_cadence"
        / "same_evaluate_rate_limit_switch.json"
    )
    assert fixture.is_file()
    md_out = tmp_path / "out.md"
    assert cadence.main(["--input", str(fixture), "--markdown-out", str(md_out)]) == 0
    rendered = md_out.read_text(encoding="utf-8")
    assert "Same-evaluate switches: **1**" in rendered
    assert "Median additional rounds to switch: **0.0**" in rendered
    assert "## Label timelines" in rendered
    assert "labeled `agent:cursor`" in rendered
    assert "labeled `agent:rate-limited`" in rendered


def test_cli_fails_when_median_additional_rounds_is_nonzero(tmp_path: Path):
    inp = tmp_path / "snap.json"
    inp.write_text(
        json.dumps(
            {
                "completions": [
                    {
                        "repo": REPO,
                        "pr": 1,
                        "provider": "codex",
                        "completed_at": "2026-10-17T09:00:00Z",
                        "reason": "rate_limited",
                    },
                    {
                        "repo": REPO,
                        "pr": 1,
                        "provider": "codex",
                        "completed_at": "2026-10-17T10:00:00Z",
                        "reason": "no_progress",
                    },
                ],
                "label_events": [
                    {
                        "repo": REPO,
                        "pr": 1,
                        "event": "labeled",
                        "label": "agent:cursor",
                        "created_at": "2026-10-17T10:05:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert cadence.main(["--input", str(inp)]) == 1


def test_cli_fails_when_stale_rate_limited_markers_remain(tmp_path: Path):
    inp = tmp_path / "snap.json"
    inp.write_text(
        json.dumps(
            {
                "completions": [
                    {
                        "repo": REPO,
                        "pr": 7,
                        "provider": "cursor",
                        "completed_at": "2026-10-17T12:00:00Z",
                        "reason": "progressed",
                    }
                ],
                "open_prs": [
                    {
                        "repo": REPO,
                        "pr": 7,
                        "labels": ["agent:rate-limited", "agent:cursor"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert cadence.main(["--input", str(inp)]) == 2


def test_concrete_agent_skips_control_labels():
    assert cadence.concrete_agent("agent:cursor") == "cursor"
    assert cadence.concrete_agent("agent:auto") is None
    assert cadence.concrete_agent("agent:rate-limited") is None
    assert cadence.concrete_agent("agents:tried-codex") is None


@pytest.mark.parametrize(
    "reason",
    ["failed", "no_progress", "progressed"],
)
def test_non_rate_limited_reasons_are_ignored(reason: str):
    report = cadence.calculate(
        {
            "completions": [
                {
                    "repo": REPO,
                    "pr": 3,
                    "provider": "codex",
                    "completed_at": "2026-10-17T09:00:00Z",
                    "reason": reason,
                }
            ],
            "label_events": [
                {
                    "repo": REPO,
                    "pr": 3,
                    "event": "labeled",
                    "label": "agent:cursor",
                    "created_at": "2026-10-17T09:01:00Z",
                }
            ],
        }
    )
    assert report["rows"] == []
    assert report["metrics"]["rate_limited_events"] == 0
