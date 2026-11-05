"""Lock the recorded product-component deliberate-break to the current verifier."""

import hashlib
import json
import re
from pathlib import Path

from tests.scripts import pr_verifier_causal_break as gate
from tests.scripts import test_pr_verifier_delivery_destinations as delivery

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "docs/ci/verifier-grammar-deliberate-break/receipt.json"


def _verifier_text() -> str:
    return (ROOT / "scripts/langchain/pr_verifier.py").read_text(encoding="utf-8")


def test_positive_channel_rows_are_the_nonempty_destination_requirements():
    mark = gate._parametrizations(
        delivery.test_product_component_coordination_preserves_bare_other_channel
    )[0]
    names = list(mark.args[0])
    positive = []
    for param in mark.args[1]:
        kwargs = dict(zip(names, param.values, strict=True))
        _criterion, expected, _required = delivery._product_component_case(**kwargs)
        bare = kwargs["governor"] == "must" and not kwargs["condition"]
        assert bool(expected) == (bare or kwargs["independent"])
        if bare:
            bare_channel = "comments" if kwargs["product_channel"] == "body" else "body"
            assert bare_channel in expected
        if kwargs["independent"]:
            assert "artifacts" in expected
        if expected:
            positive.append(f"{gate.CHANNEL_TEST}[{param.id}]")
    assert positive == gate.channel_node_ids()
    assert len(positive) == 380


def test_floor_rows_follow_the_shared_required_absent_flag():
    required = []
    waived = 0
    for kwargs in gate.floor_case_kwargs():
        formula = kwargs["governor"] == "must" and not kwargs["condition"]
        assert gate.floor_is_required_absent(kwargs) is formula
        suffix = "-".join(
            str(kwargs[name])
            for name in (
                "reverse",
                "coordination",
                "product_channel",
                "independent",
                "condition",
                "governor",
                "voice",
            )
        )
        node = f"{gate.FLOOR_TEST}[{suffix}]"
        if formula:
            required.append(node)
        else:
            waived += 1
    assert required == gate.floor_node_ids()
    assert len(required) == 48
    assert waived == 240
    assert required[0].endswith("[False-and-body-False--must-active]")


def test_mutation_anchors_are_unique_and_reversible():
    text = _verifier_text()
    assert text.count(gate.CHANNELS_OLD) == 1
    assert text.count(gate.FLOOR_OLD) == 1
    channels = text.replace(gate.CHANNELS_OLD, gate.CHANNELS_NEW, 1)
    assert "return set()" in channels.split("def _classify_evidence_options", 1)[0]
    assert channels.replace(gate.CHANNELS_NEW, gate.CHANNELS_OLD, 1) == text
    floor = text.replace(gate.FLOOR_OLD, gate.FLOOR_NEW, 1)
    assert 'if result.verdict == "PASS":\n        return result\n' in floor
    assert floor.replace(gate.FLOOR_NEW, gate.FLOOR_OLD, 1) == text


def test_recorded_breaks_failed_then_passed_on_this_verifier():
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    source = (ROOT / "scripts/langchain/pr_verifier.py").read_bytes()
    assert receipt["restored_byte_identical"] is True
    assert receipt["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert receipt["mapped_floor_test"] == gate.FLOOR_TEST
    by_name = {item["name"]: item for item in receipt["gates"]}
    expected = {
        "required_evidence_channels_empty": (
            gate.channel_node_ids(),
            "assert set() ==",
            "channels",
        ),
        "apply_coverage_floor_pass_unchanged": (
            gate.floor_node_ids(),
            "assert 'PASS' == 'CONCERNS'",
            "floor",
        ),
    }
    for name, (nodes, causal_text, stem) in expected.items():
        item = by_name[name]
        assert item["node_count"] == len(nodes)
        assert item["broken_exit_code"] == 1
        assert item["restored_exit_code"] == 0
        assert item["broken_summary"] == f"{len(nodes)} failed"
        assert item["restored_summary"] == f"{len(nodes)} passed"
        broken = (RECEIPT.parent / item["broken_transcript"]).read_text(encoding="utf-8")
        restored = (RECEIPT.parent / item["restored_transcript"]).read_text(encoding="utf-8")
        assert causal_text in broken
        assert gate._failed_nodes(broken) == nodes
        assert f"{len(nodes)} failed in <time>" in broken
        assert f"{len(nodes)} passed in <time>" in restored
        assert not re.search(r"\bfailed\b", restored)
        assert item["broken_transcript"] == f"{stem}-broken.pytest.txt"
        assert item["restored_transcript"] == f"{stem}-restored.pytest.txt"
