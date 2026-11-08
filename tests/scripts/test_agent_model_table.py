"""The shared agent model table: resolution rules and the in-repo half of the drift check."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts import agent_model_table as amt
from scripts import check_model_tables as cmt

ROOT = Path(__file__).resolve().parents[2]

TABLE_PATH = ROOT / ".github" / "agents" / "model-table.json"


@pytest.fixture()
def table() -> dict:
    return amt.load_table(TABLE_PATH)


def test_repo_agrees_with_its_own_table() -> None:
    problems, compared = cmt.run(ROOT, skip_orchestrator=True)
    assert problems == []
    assert "NOT compared" in compared


def test_drained_check_prints_zero_mismatches(capsys: pytest.CaptureFixture[str]) -> None:
    # The fully-drained output must be reachable: an identical copy prints 0, not silence.
    assert cmt.main(["--orchestrator-table", str(TABLE_PATH)]) == 0
    out = capsys.readouterr().out
    assert "model tables agree: 0 mismatches" in out


def test_copy_drift_is_counted_per_leaf(table: dict, tmp_path: Path, capsys) -> None:
    drifted = copy.deepcopy(table)
    drifted["providers"]["claude"]["models"]["full"] = "claude-opus-4-8"
    drifted["work_kinds"]["routine"]["effort"] = "high"
    path = tmp_path / "copy.json"
    path.write_text(json.dumps(drifted), encoding="utf-8")
    assert cmt.main(["--orchestrator-table", str(path)]) == 1
    out = capsys.readouterr().out
    assert "model tables agree: 2 mismatches" in out
    assert "providers.claude.models.full" in out


def test_unreadable_copy_is_not_zero(tmp_path: Path, capsys) -> None:
    assert cmt.main(["--orchestrator-table", str(tmp_path / "missing.json")]) == 2
    out = capsys.readouterr().out
    assert "CANNOT COMPARE" in out
    assert "0 mismatches" not in out


def test_registry_drift_is_counted(table: dict) -> None:
    registry = {
        "execution_profiles": {
            "codex-routine": {
                "agent": "codex",
                "lifecycle": "active",
                "model": "gpt-6.1-sol",
                "reasoning_effort": "medium",
                "fallback_model": "gpt-5.5",
            },
            "codex-unmapped": {"agent": "codex", "lifecycle": "active"},
        },
        "subscription_analysis": {"claude": {"model": "claude-haiku-4-5"}},
    }
    problems = cmt.check_registry(table, registry)
    assert any("codex-routine.model" in p for p in problems)
    assert any("codex-routine.fallback_model" in p for p in problems)
    assert any("codex-unmapped" in p for p in problems)
    assert len(problems) == 3


@pytest.mark.parametrize(
    ("kwargs", "kind", "source"),
    [
        ({"work_kind": "hard"}, "hard", "work_kind input"),
        ({"execution_profile": "codex-extract"}, "extract", "execution profile codex-extract"),
        (
            {"execution_profile": "codex-default", "mode": "autofix"},
            "routine",
            "runner mode autofix",
        ),
        ({"mode": "keepalive"}, "implement", "runner mode keepalive"),
        ({}, "implement", "table default"),
    ],
)
def test_work_kind_order(table: dict, kwargs: dict, kind: str, source: str) -> None:
    assert amt.resolve_work_kind(table, **kwargs) == (kind, source)


def test_hosted_claude_keepalive_is_pinned_with_effort(table: dict) -> None:
    got = amt.resolve(table, "claude", "hosted", mode="keepalive")
    assert got["model"] == table["providers"]["claude"]["models"]["full"]
    assert got["reasoning_effort"] == "high"
    assert got["fallback_model"] == table["providers"]["claude"]["fallback"]


def test_effort_only_where_the_model_takes_it(table: dict) -> None:
    assert amt.resolve(table, "claude", "hosted", work_kind="extract")["reasoning_effort"] == ""
    assert amt.resolve(table, "cursor", "hosted", work_kind="implement")["reasoning_effort"] == ""
    assert amt.resolve(table, "codex", "hosted", work_kind="extract")["reasoning_effort"] == "low"


def test_surface_specific_ids(table: dict) -> None:
    hosted = amt.resolve(table, "gemini", "hosted", work_kind="implement")["model"]
    local = amt.resolve(table, "gemini", "local", work_kind="implement")["model"]
    assert hosted == table["providers"]["gemini"]["surface_models"]["hosted"]["full"]
    assert local == table["providers"]["gemini"]["models"]["full"]


def test_local_only_agents_refuse_hosted(table: dict) -> None:
    for agent in ("vibe", "aider"):
        with pytest.raises(amt.TableError):
            amt.resolve(table, agent, "hosted")


def test_unknown_kind_refuses(table: dict) -> None:
    with pytest.raises(amt.TableError):
        amt.resolve(table, "codex", "hosted", work_kind="everything")


def test_every_hosted_runner_reads_the_table() -> None:
    for agent, rel in cmt.HOSTED_RUNNERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert ".workflows-lib/scripts/agent_model_table.py" in text, rel
        assert f"--agent {agent}" in text, rel
        assert "Pinned model:" in text, rel


def test_embedded_orchestrator_copy_is_read_from_its_module(tmp_path: Path, capsys) -> None:
    text = TABLE_PATH.read_text(encoding="utf-8")
    module = tmp_path / "model_table.py"
    module.write_text(
        'BEGIN_MARK = \'TABLE_JSON = r"""\'\n'
        "# BEGIN AGENT MODEL TABLE\n"
        f'TABLE_JSON = r"""{text}"""  # END AGENT MODEL TABLE\n',
        encoding="utf-8",
    )
    assert cmt.main(["--orchestrator-table", str(module)]) == 0
    assert "model tables agree: 0 mismatches" in capsys.readouterr().out
    module.write_text("TABLE = {}\n", encoding="utf-8")
    assert cmt.main(["--orchestrator-table", str(module)]) == 2
    assert "CANNOT COMPARE" in capsys.readouterr().out
