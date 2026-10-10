"""Fresh reusable helpers must not resolve from a stale consumer checkout."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "authored_comparison_tests", ROOT / "tests/workflows/test_verifier_expanded_comparison.py"
)
authored = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(authored)


def old_consumer(tmp_path, body):
    package = tmp_path / "scripts" / "langchain"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "pr_verifier.py").write_text(body)


@pytest.mark.parametrize(
    "body",
    [
        '"""Old consumer lacks the helper."""\n',
        'def expanded_comparison_verdict(*args, **kwargs): return "CONCERNS"\n',
        'raise AssertionError("Caller verifier must never execute")\n',
    ],
)
def test_fresh_workflows_helper_precedes_stale_consumer(tmp_path, body):
    old_consumer(tmp_path, body)
    outputs = authored.run_workflow(tmp_path, {"results": authored._arms()})
    assert outputs["verdict"] == outputs["unified"] == "PASS", outputs


def test_stale_consumer_cannot_override_nonpass_arm(tmp_path):
    old_consumer(tmp_path, 'def expanded_comparison_verdict(*args, **kwargs): return "PASS"\n')
    arms = authored._arms()
    arms[0].update(used_llm=False, verdict="CONCERNS")
    outputs = authored.run_workflow(tmp_path, {"results": arms})
    assert outputs["verdict"] == outputs["unified"] == "CONCERNS", outputs


def test_missing_authoritative_checkout_never_falls_back_to_caller(tmp_path, monkeypatch):
    old_consumer(tmp_path, 'def expanded_comparison_verdict(*args, **kwargs): return "PASS"\n')
    empty_source = tmp_path / "empty-source"
    empty_source.mkdir()
    monkeypatch.setattr(authored, "ROOT", empty_source)
    outputs = authored.run_workflow(tmp_path, {"results": authored._arms()})
    assert outputs["verdict"] == outputs["unified"] == "CONCERNS", outputs
