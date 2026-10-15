from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tools import verifier_semantic_rules as rules

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "verifier_semantic_packages"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture() -> tuple[dict, dict[str, bytes], dict]:
    raw = {"context": b"GLOBaaaabbbb", "diff": b"dddd"}
    capture = {
        "id": "capture-1",
        "implementation_head": "a" * 40,
        "governing_sha256": "b" * 64,
        "raw_inputs": {name: sha(value) for name, value in raw.items()},
        "gaps": [],
        "resource_admitted": True,
    }
    spans = [
        {
            "id": "global",
            "input": "context",
            "start": 0,
            "end": 4,
            "owners": ["p1", "p2"],
            "sha256": sha(raw["context"][:4]),
        },
        {
            "id": "p1",
            "input": "context",
            "start": 4,
            "end": 8,
            "owners": ["p1"],
            "sha256": sha(raw["context"][4:8]),
        },
        {
            "id": "p2",
            "input": "context",
            "start": 8,
            "end": 12,
            "owners": ["p2"],
            "sha256": sha(raw["context"][8:]),
        },
        {
            "id": "diff",
            "input": "diff",
            "start": 0,
            "end": 4,
            "owners": ["p2"],
            "sha256": sha(raw["diff"]),
        },
    ]
    rule = {
        "schema": "workflows-verifier-semantic-rule/v1",
        "capture_id": capture["id"],
        "governing_sha256": capture["governing_sha256"],
        "clauses": [
            {
                "id": "global-p1",
                "predicate": "provenance",
                "raw_dependencies": ["global"],
                "requires": [],
                "joint_groups": [],
            },
            {
                "id": "local-p1",
                "predicate": "equality",
                "raw_dependencies": ["p1"],
                "requires": ["global-p1"],
                "joint_groups": [],
            },
            {
                "id": "global-p2",
                "predicate": "provenance",
                "raw_dependencies": ["global"],
                "requires": [],
                "joint_groups": [],
            },
            {
                "id": "joint-a",
                "predicate": "set",
                "raw_dependencies": ["p2"],
                "requires": ["global-p2"],
                "joint_groups": ["joint"],
            },
            {
                "id": "joint-b",
                "predicate": "bounds",
                "raw_dependencies": ["diff"],
                "requires": ["global-p2"],
                "joint_groups": ["joint"],
            },
        ],
    }
    entry = {
        "binding": {
            **{key: capture[key] for key in ("id", "implementation_head", "governing_sha256")},
            "raw_inputs": dict(capture["raw_inputs"]),
        },
        "rule": rule,
        "spans": spans,
        "joins": [{"span_ids": ["global"], "package_ids": ["p1", "p2"]}],
        "global_clause_ids_by_package": {
            "p1": ["global-p1"],
            "p2": ["global-p2"],
        },
        "packages": [
            {"id": "p1", "clause_ids": ["global-p1", "local-p1"], "raw_inputs": ["global", "p1"]},
            {
                "id": "p2",
                "clause_ids": ["global-p2", "joint-a", "joint-b"],
                "raw_inputs": ["global", "p2", "diff"],
            },
        ],
    }
    return capture, raw, entry


def test_reviewed_decomposition_uses_exact_spans_and_joint_closure() -> None:
    capture, raw, entry = fixture()
    prepared = rules.prepare_reviewed_execution(capture, raw, rules=(entry,))
    assert prepared is not None
    assert prepared["plan"]["packages"][1]["clause_ids"] == ["global-p2", "joint-a", "joint-b"]
    assert (
        b"".join(
            item["bytes"]
            for item in prepared["prompts"]["p1"]["members"]
            if item["input"] == "context"
        )
        == b"GLOBaaaa"
    )
    # Whole input is 16 bytes; both closed evidence sets are independently small.
    assert sum(map(len, raw.values())) > 13
    assert all(
        sum(len(member["bytes"]) for member in item["members"]) <= 12
        for item in prepared["prompts"].values()
    )
    calls: list[str] = []
    outcomes = rules.preflight_package_prompts(
        prepared["prompts"], lambda package, _: calls.append(package) or True
    )
    assert calls == ["p1", "p2"] and outcomes == {"p1": True, "p2": True}


def test_no_package_invokes_before_all_frozen_preflights_pass() -> None:
    capture, raw, entry = fixture()
    prompts = rules.prepare_reviewed_execution(capture, raw, rules=(entry,))["prompts"]
    invoked: list[str] = []
    with pytest.raises(ValueError, match="every package"):
        rules.preflight_then_invoke(
            prompts,
            lambda package, _: package == "p1",
            lambda package, _: invoked.append(package),
        )
    assert invoked == []


@pytest.mark.parametrize("mutation", ["changed-governing", "mutated-input"])
def test_unknown_or_changed_capture_never_infers_a_split(mutation: str) -> None:
    capture, raw, entry = fixture()
    if mutation == "changed-governing":
        capture["governing_sha256"] = "c" * 64
    else:
        raw["diff"] = b"nope"
        capture["raw_inputs"]["diff"] = sha(raw["diff"])
    assert rules.prepare_reviewed_execution(capture, raw, rules=(entry,)) is None
    residual = rules.prepare_residual_all_input(capture, raw)
    assert residual["plan"]["packages"] == [
        {
            "id": "residual",
            "clause_ids": ["residual-all-input"],
            "raw_inputs": sorted(raw),
            "closure_sha256": residual["plan"]["packages"][0]["closure_sha256"],
        }
    ]


def test_rejects_missing_byte_coverage_and_undeclared_shared_evidence() -> None:
    capture, raw, entry = fixture()
    entry["spans"] = entry["spans"][:-1]
    with pytest.raises(ValueError, match="every capture byte"):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))


def test_rejects_missing_global_clause_copy() -> None:
    capture, raw, entry = fixture()
    entry["global_clause_ids_by_package"]["p2"] = ["joint-a"]
    with pytest.raises(ValueError, match="global clause"):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))
    capture, raw, entry = fixture()
    entry["joins"] = []
    with pytest.raises(ValueError, match="declared join"):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))


def test_rejects_missing_joint_member_and_unowned_prompt_member() -> None:
    capture, raw, entry = fixture()
    entry["packages"][1]["clause_ids"].remove("joint-b")
    entry["packages"][1]["raw_inputs"].remove("diff")
    with pytest.raises(ValueError, match="n-way joint"):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))
    capture, raw, entry = fixture()
    entry["spans"][1]["owners"] = ["p2"]
    with pytest.raises(ValueError, match="ownership"):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))


def test_rejects_more_than_eight_reviewed_packages() -> None:
    capture, raw, entry = fixture()
    entry["packages"] *= 5
    with pytest.raises(ValueError, match="package specs"):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))


def test_fixed_registry_loader_rejects_duplicate_json_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    path = tmp_path / "rules.json"
    path.write_text('{"schema":"workflows-verifier-semantic-rules/v1","rules":[],"rules":[]}')
    monkeypatch.setattr(rules, "RULES_PATH", path)
    with pytest.raises(ValueError, match="duplicate registry key"):
        rules.load_reviewed_rules()


def test_prepare_uses_the_fixed_source_owned_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = json.loads((FIXTURE_DIR / "capture.json").read_text())
    raw = {name: (FIXTURE_DIR / f"{name}.bin").read_bytes() for name in capture["raw_inputs"]}
    monkeypatch.setattr(rules, "RULES_PATH", FIXTURE_DIR / "rules.json")
    prepared = rules.prepare_reviewed_execution(capture, raw)
    assert prepared["contract"]["capture_id"] == capture["id"]
    assert sum(map(len, raw.values())) > 16 * 1024
    # This is the actual framed prompt, not only its raw source members.
    assert all(len(prompt["bytes"]) < 13_000 for prompt in prepared["prompts"].values())
    assert (
        prepared["prompts"]["p2"]["package_id"] == "p2"
    )  # joint-a and joint-b share this closed prompt


def grouped_join_fixture() -> tuple[dict, dict[str, bytes], dict]:
    capture, raw, entry = fixture()
    original = entry["spans"].pop(0)
    for index, (start, end) in enumerate(((0, 2), (2, 4))):
        entry["spans"].append(
            {
                **original,
                "id": f"global-{index}",
                "start": start,
                "end": end,
                "sha256": sha(raw["context"][start:end]),
            }
        )
    for clause in entry["rule"]["clauses"]:
        if clause["raw_dependencies"] == ["global"]:
            clause["raw_dependencies"] = ["global-0", "global-1"]
    for package in entry["packages"]:
        package["raw_inputs"].remove("global")
        package["raw_inputs"].extend(["global-0", "global-1"])
    entry["joins"][0]["span_ids"] = ["global-0", "global-1"]
    return capture, raw, entry


def test_grouped_shared_span_join_prepares_complete_execution() -> None:
    capture, raw, entry = grouped_join_fixture()
    prepared = rules.prepare_reviewed_execution(capture, raw, rules=(entry,))
    assert prepared is not None
    for prompt in prepared["prompts"].values():
        members = {member["id"]: member["bytes"] for member in prompt["members"]}
        assert members["global-0"] + members["global-1"] == b"GLOB"


@pytest.mark.parametrize("mutation", ["missing-span", "wrong-owners"])
def test_grouped_join_still_requires_every_span_and_exact_owners(mutation: str) -> None:
    capture, raw, entry = grouped_join_fixture()
    if mutation == "missing-span":
        entry["joins"][0]["span_ids"] = ["global-0"]
        message = "declared join"
    else:
        entry["joins"][0]["package_ids"] = ["p1", "p3"]
        message = "exact shared ownership"
    with pytest.raises(ValueError, match=message):
        rules.prepare_reviewed_execution(capture, raw, rules=(entry,))
