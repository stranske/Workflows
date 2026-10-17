"""Offline integration for the semantic expanded comparison boundary."""

from __future__ import annotations

import pytest
from scripts.langchain import pr_verifier


class _Response:
    content = [
        {"type": "thinking", "thinking": "private"},
        {
            "type": "text",
            "text": '{"verdict":"PASS","concerns":[],"summary":"Fixture review detail"}',
        },
    ]


class _Client:
    def __init__(self, calls: list[str], name: str) -> None:
        self.calls = calls
        self.name = name

    def invoke(self, prompt: str) -> _Response:
        self.calls.append(self.name)
        return _Response()


def _context() -> str:
    from tests.scripts.verifier_capacity_fakes import complete_capture_context

    return complete_capture_context()


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


@pytest.mark.parametrize("fence", [None, "json", ""])
def test_semantic_mode_builds_full_matrix_before_offline_native_callbacks(monkeypatch, fence):
    raw = '{"verdict":"PASS","concerns":[],"summary":"Fixture review detail"}'
    if fence is not None:
        raw = f"```{fence}\n{raw}\n```"
    monkeypatch.setattr(
        _Response,
        "content",
        [{"type": "thinking", "thinking": "private"}, {"type": "text", "text": raw}],
    )
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

    monkeypatch.setattr(pr_verifier, "_build_semantic_clients", lambda *args: runner.clients)
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
    run = pr_verifier._evaluate_pr_multiple_semantic(
        _context(),
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
        None,
        None,
    )
    assert events[:2] == ["preflight:one", "preflight:two"]
    assert calls == ["one", "two"]
    assert run[0].summary == "Fixture review detail"
    assert run[0].raw_content == raw
    assert "Fixture review detail" in run[0].raw_content
    assert "private" not in run[0].raw_content
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


def test_semantic_client_construction_disables_actual_sdk_retries(monkeypatch):
    from types import SimpleNamespace

    import pytest
    from tools import langchain_client

    cls = pytest.importorskip("langchain_openai").ChatOpenAI
    calls = []

    def build(**kwargs):
        calls.append(kwargs)
        client = langchain_client._build_openai_client(
            cls, model="gpt-4o", token="offline", timeout=1, max_retries=kwargs["max_retries"]
        )
        return [SimpleNamespace(client=client, provider="openai", model="gpt-4o")]

    monkeypatch.setattr(langchain_client, "build_chat_clients", build)
    clients = pr_verifier._build_semantic_clients(None, None)
    assert calls == [{"model1": None, "model2": None, "max_retries": 0}]
    assert clients[0][0].root_client.max_retries == 0
    assert clients[0][0].root_async_client.max_retries == 0


def test_cli_recovers_reviewed_oversize_capture_through_complete_joint_matrix(
    monkeypatch, tmp_path, capsys
):
    import io
    import json
    import sys
    from pathlib import Path

    from tools import verifier_semantic_rules as rules

    fixture = Path(__file__).parents[1] / "fixtures/verifier_semantic_packages"
    capture = json.loads((fixture / "capture.json").read_text())
    context = (fixture / "context.bin").read_text()
    diff_path = fixture / "diff.bin"
    monkeypatch.setattr(rules, "RULES_PATH", fixture / "rules.json")
    monkeypatch.setattr(pr_verifier, "_semantic_capture", lambda *args: capture)
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    key = tmp_path / "key"
    key.write_bytes(b"t" * 32)
    monkeypatch.setenv("VERIFIER_SEMANTIC_KEY_PATH", str(key))
    events = []

    class Client:
        def __init__(self, name):
            self.name = name

        def invoke(self, prompt):
            assert len([e for e in events if e[0] == "count"]) >= 4
            events.append(("invoke", self.name, len(prompt)))
            return _Response()

    clients = {"slot-1": Client("one"), "slot-2": Client("two")}
    slots = [
        {
            "slot_id": name,
            "provider": provider,
            "model": "fixture-model",
            "transport": "synthetic",
            "config_sha256": char * 64,
        }
        for name, provider, char in [("slot-1", "openai", "a"), ("slot-2", "anthropic", "b")]
    ]
    monkeypatch.setattr(pr_verifier, "_build_semantic_clients", lambda *args: [])
    monkeypatch.setattr(
        pr_verifier, "_semantic_slots_and_clients", lambda *args: (slots, clients, False)
    )
    # Character units deliberately emulate an exact counter; no model capacity
    # or authentic native execution is claimed by this offline fixture.
    capacity = len(pr_verifier._load_prompt()) + 15000
    assert len(context) + len(diff_path.read_text()) + len(pr_verifier._load_prompt()) > capacity

    def count(client, prompt):
        import hashlib

        assert len(prompt) <= capacity
        events.append(("count", client.name, len(prompt)))
        return {
            "status": "PASS",
            "request_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "input_tokens": len(prompt),
            "context_limit": capacity + 128000,
            "output_reserve": 128000,
        }

    monkeypatch.setattr(pr_verifier, "_preflight_input_capacity", count)
    monkeypatch.setattr(sys, "stdin", io.StringIO(context))
    monkeypatch.setattr(
        sys, "argv", ["verifier", "--diff-file", str(diff_path), "--compare", "--json"]
    )
    pr_verifier.main()
    payload = json.loads(capsys.readouterr().out)
    envelope = payload["semantic_acceptance"]
    assert len(envelope["execution"]["plan"]["packages"]) == 2
    assert len(envelope["admission"]["expected_cells"]) == 4
    assert len([e for e in events if e[0] == "invoke"]) == 4
    assert len([e for e in events if e[0] == "count"]) == 8
    assert envelope["admission"]["missing_cells"] == []
    assert pr_verifier.expanded_comparison_verdict(payload) == "CONCERNS"
    assert all(cell["synthetic"] for cell in envelope["execution"]["ledger"]["cells"])
    assert all(
        len(cell["counts"]["native_payload_sha256"]) == 64
        for cell in envelope["execution"]["ledger"]["cells"]
    )


def test_semantic_capture_admits_verified_full_patch_for_truncated_rendered_code(monkeypatch):
    import hashlib
    import json

    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+😀new\n"
    raw_diff = diff.encode("utf-8")
    canonical_diff = diff[:-1]
    context = _context()
    start = context.index("```json\n") + len("```json\n")
    end = context.index("\n```", start)
    coverage = json.loads(context[start:end])
    coverage["changed_code_sources"] = [
        {
            "source": "a.py",
            "from_path": "a.py",
            "status": "truncated",
            "included_chars": 4,
            "total_chars": len(canonical_diff),
            "start": 0,
            "end": len(canonical_diff.encode("utf-8")),
            "sha256": hashlib.sha256(canonical_diff.encode("utf-8")).hexdigest(),
        }
    ]
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(canonical_diff),
        "bytes": len(raw_diff),
        "sha256": hashlib.sha256(raw_diff).hexdigest(),
        "encoding": "utf-8",
    }
    context = context[:start] + json.dumps(coverage) + context[end:]
    monkeypatch.setenv("PR_HEAD_SHA", "a" * 40)
    capture = pr_verifier._semantic_capture(context, diff)
    assert capture["manifest"]["sufficient"] is True
    assert not any(gap == "changed_code:a.py:truncated" for gap in capture["gaps"])


def test_native_preflight_admits_only_verified_full_patch_for_truncated_code(monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    import pytest

    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+😀new\n"
    raw_diff = diff.encode("utf-8")
    canonical_diff = diff[:-1]
    context = _context()
    start = context.index("```json\n") + len("```json\n")
    end = context.index("\n```", start)
    coverage = json.loads(context[start:end])
    coverage["changed_code_sources"] = [
        {
            "source": "a.py",
            "from_path": "a.py",
            "status": "truncated",
            "included_chars": 4,
            "total_chars": len(canonical_diff),
            "start": 0,
            "end": len(canonical_diff.encode("utf-8")),
            "sha256": hashlib.sha256(canonical_diff.encode("utf-8")).hexdigest(),
        }
    ]
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(canonical_diff),
        "bytes": len(raw_diff),
        "sha256": hashlib.sha256(raw_diff).hexdigest(),
        "encoding": "utf-8",
    }
    context = context[:start] + json.dumps(coverage) + context[end:]
    prompt = pr_verifier._prepare_prompt(context, diff)
    calls: list[dict] = []

    class Client:
        root_client = SimpleNamespace(
            responses=SimpleNamespace(
                input_tokens=SimpleNamespace(
                    count=lambda **payload: calls.append(payload)
                    or SimpleNamespace(input_tokens=10)
                )
            )
        )

        @staticmethod
        def _get_request_payload(value):
            return {
                "model": "fixture-native",
                "input": value,
                "max_output_tokens": 5,
                "truncation": "disabled",
            }

    monkeypatch.setattr(
        pr_verifier,
        "_native_capacity_contract",
        lambda client: {
            "provider": "openai",
            "model": "fixture-native",
            "provenance": "synthetic-unit-test-only",
            "profile": {
                "max_input_tokens": 100,
                "max_context_tokens": 200,
                "max_output_tokens": 10,
            },
        },
    )
    receipt = pr_verifier._preflight_input_capacity(Client(), prompt, context=context, diff=diff)
    assert receipt["status"] == "PASS"
    assert receipt["capture_obligations"]["sufficient"] is True
    assert len(calls) == 1

    coverage["full_diff_artifact"]["sha256"] = "0" * 64
    broken_start = context.index("```json\n") + len("```json\n")
    broken_end = context.index("\n```", broken_start)
    broken_context = context[:broken_start] + json.dumps(coverage) + context[broken_end:]
    with pytest.raises(pr_verifier.InputCapacityError) as blocked:
        pr_verifier._preflight_input_capacity(
            Client(),
            pr_verifier._prepare_prompt(broken_context, diff),
            context=broken_context,
            diff=diff,
        )
    assert (
        "full_diff_artifact:sha256_mismatch" in blocked.value.receipt["capture_obligations"]["gaps"]
    )
    assert len(calls) == 1


def test_semantic_capture_uses_lossless_coverage_but_preserves_missing_proof(monkeypatch):
    context = _context()
    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    monkeypatch.setenv("PR_HEAD_SHA", "a" * 40)
    for name in (
        "VERIFIER_CONTEXT_BUDGET_TOKENS",
        "VERIFIER_DIFF_BUDGET_TOKENS",
        "VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS",
    ):
        monkeypatch.setenv(name, "1")
    assert not pr_verifier.prompt_coverage(context, diff).sufficient
    assert pr_verifier.build_prompt_inputs(context, diff, lossless=True).coverage.sufficient
    assert pr_verifier._semantic_capture(context, diff)["resource_admitted"] is True
    missing = context.replace(
        "Implement the code change.", "The reviewer must post evidence in a PR comment."
    )
    capture = pr_verifier._semantic_capture(missing, diff)
    assert capture["resource_admitted"] is False
    assert any("Required acceptance evidence is unavailable" in gap for gap in capture["gaps"])


def test_cli_preserves_crlf_bytes_in_capture_and_line_ending_only_diffs(
    monkeypatch, tmp_path, capsys
):
    import hashlib
    import json
    import sys

    context_path = tmp_path / "verifier-context.md"
    diff_crlf = tmp_path / "crlf.patch"
    diff_lf = tmp_path / "lf.patch"
    context_bytes = b"# Verifier context\r\n\r\n## CI Information\r\nnone\r\n"
    crlf_bytes = b"diff --git a/a b/a\r\n-old\r\n+new\r\n"
    lf_bytes = crlf_bytes.replace(b"\r\n", b"\n")
    context_path.write_bytes(context_bytes)
    diff_crlf.write_bytes(crlf_bytes)
    diff_lf.write_bytes(lf_bytes)
    observed: list[tuple[str, str | None]] = []

    def non_native_compare(context: str, diff: str | None, **_kwargs):
        observed.append((context, diff))
        return [
            pr_verifier.EvaluationResult(
                verdict="CONCERNS",
                concerns=["offline byte-identity test"],
                used_llm=False,
            )
        ]

    monkeypatch.setattr(pr_verifier, "evaluate_pr_multiple", non_native_compare)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verifier",
            "--context-file",
            str(context_path),
            "--diff-file",
            str(diff_crlf),
            "--compare",
            "--json",
        ],
    )
    pr_verifier.main()
    payload = json.loads(capsys.readouterr().out)
    assert observed == [(context_bytes.decode(), crlf_bytes.decode())]
    assert payload["results"][0]["used_llm"] is False
    assert payload["results"][0]["verdict"] == "CONCERNS"
    capture_crlf = pr_verifier._semantic_capture(*observed[0])
    capture_lf = pr_verifier._semantic_capture(context_bytes.decode(), lf_bytes.decode())
    assert capture_crlf["raw_inputs"]["context"] == hashlib.sha256(context_bytes).hexdigest()
    assert capture_crlf["raw_inputs"]["diff"] == hashlib.sha256(crlf_bytes).hexdigest()
    assert capture_crlf["raw_inputs"]["diff"] != capture_lf["raw_inputs"]["diff"]
    assert capture_crlf["id"] != capture_lf["id"]
    inventory = json.loads((tmp_path / "verifier-capture-byte-inventory.json").read_text())
    inventory_hashes = {item["input"]: item["sha256"] for item in inventory["inputs"]}
    assert inventory_hashes == {
        "context": hashlib.sha256(context_bytes).hexdigest(),
        "diff": hashlib.sha256(crlf_bytes).hexdigest(),
    }


@pytest.mark.parametrize(
    "raw",
    [
        'prefix\n```json\n{"verdict":"PASS"}\n```',
        '```json\n{"verdict":"PASS"}\n```\nsuffix',
        '```python\n{"verdict":"PASS"}\n```',
        '```json\n{"verdict":"PASS"}',
        '```json\n{"verdict":"PASS"}\n```\n```json\n{}\n```',
        '```json\n{"verdict":"NOT_A_VERDICT"}\n```',
        '```json\n{"verdict":"PASS","confidence":"0.9"}\n```',
        '```json\n{"verdict":"PASS","unknown":true}\n```',
        "```json\n[]\n```",
    ],
)
def test_semantic_response_envelope_refuses_ambiguous_or_invalid_payloads(raw):
    with pytest.raises(ValueError):
        pr_verifier._parse_semantic_evaluation_payload(raw)
