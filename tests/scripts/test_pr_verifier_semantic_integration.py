"""Offline integration for the semantic expanded comparison boundary."""

from __future__ import annotations

from scripts.langchain import pr_verifier


class _Response:
    content = '{"verdict":"PASS","concerns":[]}'


class _Client:
    def __init__(self, calls: list[str], name: str) -> None:
        self.calls = calls
        self.name = name

    def invoke(self, prompt: str) -> _Response:
        self.calls.append(self.name)
        return _Response()


def _context() -> str:
    return """# Verifier context
## Context source coverage
```json
{"schema":"verifier-context-source-coverage/v1","stage":"generated-context","changed_code_sources":[{"source":"x.py","status":"included","included_chars":1,"total_chars":1}],"acceptance_sources":[{"source":"issue","status":"included","included_chars":1,"total_chars":1}],"acceptance_evidence_sources":[],"acceptance_source_discovery":{"required":false,"status":"included"},"full_diff_artifact":{"source":"diff","status":"included","chars":1}}
```
## Plan sources (scope, tasks, acceptance)
complete governing evidence
## CI Information
complete ci evidence
"""


def test_semantic_mode_requires_envelope_and_never_falls_back_to_legacy_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    assert pr_verifier.expanded_comparison_verdict({"results": []}) == "CONCERNS"
    key = tmp_path / "runner-key"
    key.write_bytes(b"k" * 32)
    monkeypatch.setenv("VERIFIER_SEMANTIC_KEY_PATH", str(key))
    envelope = {"schema": pr_verifier.SEMANTIC_ENVELOPE_SCHEMA, "admission": {"verdict": "FAIL"}}
    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": envelope}) == "CONCERNS"
    envelope["signature"] = pr_verifier._semantic_envelope_signature(envelope)
    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": envelope}) == "FAIL"
    envelope["admission"]["verdict"] = "PASS"
    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": envelope}) == "CONCERNS"
    key.write_bytes(b"r" * 32)
    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": envelope}) == "CONCERNS"


def test_semantic_mode_builds_full_matrix_before_offline_native_callbacks(monkeypatch):
    monkeypatch.setenv("PR_HEAD_SHA", "a" * 40)
    calls: list[str] = []
    clients = [_Client(calls, "one"), _Client(calls, "two")]
    slots = [
        {
            "slot_id": "slot-1",
            "provider": "openai",
            "model": "model-1",
            "transport": "native",
            "config_sha256": "1" * 64,
        },
        {
            "slot_id": "slot-2",
            "provider": "anthropic",
            "model": "model-2",
            "transport": "native",
            "config_sha256": "2" * 64,
        },
    ]
    events: list[str] = []

    runner = type(
        "Runner",
        (),
        {"clients": [(clients[0], "openai", "model-1"), (clients[1], "anthropic", "model-2")]},
    )()

    monkeypatch.setattr(pr_verifier.ComparisonRunner, "from_environment", lambda *args: runner)
    monkeypatch.setattr(
        pr_verifier,
        "_semantic_slots_and_clients",
        lambda *args: (slots, {"slot-1": clients[0], "slot-2": clients[1]}, False),
    )
    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda context, diff: "complete prompt")
    monkeypatch.setattr(
        pr_verifier,
        "prompt_coverage",
        lambda context, diff: type("Coverage", (), {"reasons": (), "sufficient": True})(),
    )

    def preflight(client, prompt):
        events.append(f"preflight:{client.name}")
        return {
            "status": "PASS",
            "request_sha256": "a" * 64,
            "input_tokens": 1,
            "context_limit": 100,
            "output_reserve": 2,
        }

    monkeypatch.setattr(pr_verifier, "_preflight_input_capacity", preflight)
    run = pr_verifier._evaluate_pr_multiple_semantic(_context(), "diff", None, None)
    assert events[:2] == ["preflight:one", "preflight:two"]
    assert calls == ["one", "two"]
    assert run.semantic_acceptance["schema"] == pr_verifier.SEMANTIC_ENVELOPE_SCHEMA
    assert (
        run.semantic_acceptance["admission"]["verdict"] == "CONCERNS"
    )  # offline provenance is synthetic


def test_semantic_capture_gap_blocks_native_callbacks(monkeypatch):
    capture = pr_verifier._semantic_capture("incomplete context", None)
    assert capture["resource_admitted"] is False
    # The execution helper's resource guard is separately covered; this proves
    # the production capture carries the historic unavailable-evidence gap.
    assert "full_diff_missing" in capture["gaps"]
