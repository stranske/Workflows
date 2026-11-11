"""Lock deliberate-break receipts for the tests added in this round.

Each receipt names one production symbol, one pytest node, a red failure, and
the restored-source pass. Immutable recorded source snapshots contain the
restored bytes; current production may evolve independently. Prior #4000 and
#4405 transcripts are recorded as unavailable and are not treated as these runs.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
RECEIPTS_PATH = EVIDENCE / "mutation-receipts.json"
RECEIPTS_MD = EVIDENCE / "mutation-receipts.md"
EXPANDED = "tests/scripts/test_pr_verifier_expanded_comparison_verdict.py"
VERIFIER_TESTS = "tests/scripts/test_verifier_config.py"

# Assertion line captured while the mutant was in the tree. The unreadable-key
# case escapes as IsADirectoryError, so its named failure is the exception.
FAILURE_TEXT = {
    "semantic-non-dict": "test_pr_verifier_expanded_comparison_verdict.py:71: AssertionError: assert 'PASS' == 'CONCERNS'",
    "semantic-bad-signature": "test_pr_verifier_expanded_comparison_verdict.py:86: AssertionError: assert 'FAIL' == 'CONCERNS'",
    "semantic-unreadable-key": "IsADirectoryError: [Errno 21] Is a directory:",
    "semantic-admission-allowlist": "test_pr_verifier_expanded_comparison_verdict.py:111: AssertionError: assert 'UNVERIFIABLE_INPUT' == 'CONCERNS'",
    "semantic-signed-verdict": "test_pr_verifier_expanded_comparison_verdict.py:129: AssertionError: assert 'CONCERNS' == 'FAIL'",
    "legacy-two-providers": "test_pr_verifier_expanded_comparison_verdict.py:137: AssertionError: assert 'PASS' == 'CONCERNS'",
    "legacy-results-shape": "test_pr_verifier_expanded_comparison_verdict.py:146: AssertionError: assert 'PASS' == 'CONCERNS'",
    "legacy-both-judges": "test_pr_verifier_expanded_comparison_verdict.py:158: AssertionError: assert 'CONCERNS' == 'PASS'",
    "configured-fail": "test_pr_verifier_expanded_comparison_verdict.py:177: AssertionError: assert 'CONCERNS' == 'FAIL'",
    "impersonation-guard": "test_pr_verifier_expanded_comparison_verdict.py:201: AssertionError: assert 'FAIL' == 'CONCERNS'",
    "concerns-block-pass": "test_pr_verifier_expanded_comparison_verdict.py:227: AssertionError: assert 'PASS' == 'CONCERNS'",
    "unverifiable-both-slots": "test_pr_verifier_expanded_comparison_verdict.py:248: AssertionError: assert 'CONCERNS' == 'UNVERIFIABLE_INPUT'",
    "model-overrides": "test_pr_verifier_expanded_comparison_verdict.py:256: AssertionError: assert 'CONCERNS' == 'PASS'",
    "nested-list": "test_verifier_config.py:139: AssertionError: assert False",
    "nested-payload": "test_verifier_config.py:142: AssertionError: assert False",
    "artifact-coercion": "test_verifier_config.py:154: AssertionError: assert False",
    "duplicate-verdicts": "test_verifier_config.py:162: AssertionError: assert 'PASS' == 'FAIL'",
    "explicit-anthropic-selection": "test_langchain_client.py:1379: AssertionError: assert 'not-anthropic' == 'anthropic'",
    "blank-slot-model-single": "test_langchain_client.py:1396: AssertionError: assert ClientInfo",
    "blank-slot-model-paired": "test_langchain_client.py:1409: AssertionError: assert [ClientInfo",
    "blocked-override-not-retried": "test_langchain_client.py:1428: AssertionError: assert [('openai', '...gpt-blocked')] == [('openai', '...claude-safe')]",
    "unblocked-model1-shared": "test_langchain_client.py:1450: AssertionError: assert [('openai', '...-sonnet-5-5')] == [('openai', '...ed-override')]",
    "explicit-model2": "test_langchain_client.py:1471: AssertionError: assert [('openai', '...st-override')] == [('openai', '...nd-override')]",
    "github-slot-selection": "test_langchain_client.py:1490: AssertionError: assert 'not-github' == 'github-models'",
    "github-slot-selection-paired": "test_langchain_client.py:1509: AssertionError: assert [('not-github...gpt-6.1-sol')] == [('github-mod...gpt-6.1-sol')]",
    "github-constructor-miss": "test_langchain_client.py:1524: RuntimeError: github constructor failed",
    "blocked-slot-model-single": "test_langchain_client.py:1567: AssertionError: assert ClientInfo",
    "blocked-slot-model-paired": "test_langchain_client.py:1568: AssertionError: assert [ClientInfo",
    "configured-slot-file-miss": "test_langchain_client.py:1580: AssertionError: assert [SlotDefiniti",
    "empty-channel-cache-hit": "test_pr_verifier_evidence_cache_miss.py:29: assert 0 == (0 + 1)",
    "empty-option-cache-hit": "test_pr_verifier_evidence_cache_miss.py:48: assert 0 == (0 + 1)",
}


def _load() -> dict:
    return json.loads(RECEIPTS_PATH.read_text(encoding="utf-8"))


def _recorded_source(path: str) -> str:
    """Read a receipt-era snapshot, independent of checkout history and live files."""
    entry = _load()["recorded_source"]["files"][path]
    snapshot = (EVIDENCE / entry["path"]).resolve()
    if not snapshot.is_relative_to((EVIDENCE / "recorded-source").resolve()):
        raise ValueError("recorded source path escapes its evidence directory")
    data = snapshot.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("recorded source digest mismatch")
    return data.decode("utf-8")


def _function_text(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = source.splitlines()[node.lineno - 1 : node.end_lineno]
            return "\n".join(lines) + "\n"
    raise ValueError(f"{name} is not defined in the recorded source")


def _test_names(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def validate_receipt(receipt: dict, source: str, *, source_sha256: str) -> None:
    """Raise ValueError unless the receipt shows a real red failure and a restored pass."""
    red = receipt["red"]
    green = receipt["green"]
    if red["exit_code"] != 1:
        raise ValueError("red exit must be 1")
    if green["exit_code"] != 0:
        raise ValueError("green exit must be 0")
    if red["elapsed_seconds"] >= 120 or green["elapsed_seconds"] >= 120:
        raise ValueError("focused pytest exceeded two minutes")
    if "1 failed" not in red["output"] or "1 passed" not in green["output"]:
        raise ValueError("pytest summary does not match the exit codes")
    nodeid = receipt["nodeid"]
    for phase in (red, green):
        command = phase["command"]
        if ("-m", "not slow") not in set(zip(command, command[1:], strict=False)):
            raise ValueError("pytest marker must skip slow tests")
        if nodeid not in command:
            raise ValueError("pytest command does not name the receipt test")
    if receipt["mutant_snippet"] in source:
        raise ValueError("mutant snippet remains in the source")
    if source.count(receipt["original_snippet"]) != 1:
        raise ValueError("restored source must contain the original snippet once")
    if receipt["original_snippet"] not in _function_text(source, receipt["symbol"]):
        raise ValueError("original snippet is outside the named symbol")
    if (
        hashlib.sha256(source.encode()).hexdigest() != source_sha256
        or source_sha256 != receipt["restored_sha256"]
    ):
        raise ValueError("restored sha256 does not match the source")
    if receipt["mutant_sha256"] == receipt["restored_sha256"]:
        raise ValueError("mutation did not change the source bytes")
    failure = FAILURE_TEXT[receipt["id"]]
    if failure not in red["output"]:
        raise ValueError("named failure does not match the captured red output")
    if nodeid.split("::", 1)[1] not in receipt["red_named_failure"]:
        raise ValueError("named failure does not name the test")


def test_every_added_comparison_test_has_one_restored_receipt() -> None:
    record = _load()
    receipts = record["receipts"]
    by_id = {item["id"]: item for item in receipts}
    assert record["schema"] == "workflows.issue-4426-mutation-receipts/v1"
    assert record["checked_on"] == "2026-11-06T19:51:20Z"
    assert record["production_restored"] is True
    assert set(by_id) == set(FAILURE_TEXT)

    comparison = [
        item
        for item in receipts
        if item["source"] == "scripts/langchain/pr_verifier.py"
        and item["symbol"] == "expanded_comparison_verdict"
    ]
    names = _test_names(_recorded_source(EXPANDED))
    assert len(names) == 13
    assert [item["nodeid"].split("::", 1)[1] for item in comparison] == names
    source = _recorded_source("scripts/langchain/pr_verifier.py")
    digest = hashlib.sha256(source.encode()).hexdigest()
    for item in comparison:
        validate_receipt(item, source, source_sha256=digest)
        start = source.count("\n", 0, source.index(item["original_snippet"])) + 1
        assert start == item["source_start_line"]


def test_landed_verifier_config_receipts_cover_coercion_lists_and_verdicts() -> None:
    record = _load()
    source = _recorded_source("scripts/langchain/verifier_config.py")
    digest = hashlib.sha256(source.encode()).hexdigest()
    selected = {
        item["id"]: item
        for item in record["receipts"]
        if item["source"] == "scripts/langchain/verifier_config.py"
    }
    assert set(selected) == {
        "nested-list",
        "nested-payload",
        "artifact-coercion",
        "duplicate-verdicts",
    }
    assert selected["nested-list"]["symbol"] == "is_terminal_artifact"
    assert selected["nested-payload"]["symbol"] == "is_terminal_artifact"
    assert selected["artifact-coercion"]["symbol"] == "_coerce_artifact"
    assert selected["duplicate-verdicts"]["symbol"] == "artifact_from_verification_text"
    list_node = selected["nested-list"]["nodeid"]
    assert list_node == selected["nested-payload"]["nodeid"]
    assert list_node.endswith(
        "test_is_terminal_artifact_handles_nested_lists_payloads_and_non_artifacts"
    )
    assert selected["artifact-coercion"]["nodeid"].endswith(
        "test_terminal_artifact_coercion_and_pending_stage_edges"
    )
    assert selected["duplicate-verdicts"]["nodeid"].endswith(
        "test_artifact_text_without_report_marker_and_duplicate_verdicts"
    )
    config_lines = _recorded_source(VERIFIER_TESTS).splitlines()
    assert '[{"verdict": "PASS"}, {"verdict": "ERROR"}]' in config_lines[138]
    assert '{"payload": {"verdict": "PASS"}}' in config_lines[141]
    assert "Dumpable()" in config_lines[153]
    assert 'artifact["verdict"] == "FAIL"' in config_lines[161]
    for item in selected.values():
        validate_receipt(item, source, source_sha256=digest)
    assert "test_verifier_config.py:139:" in selected["nested-list"]["red"]["output"]
    assert "test_verifier_config.py:142:" in selected["nested-payload"]["red"]["output"]
    assert selected["nested-list"]["red"]["output"] != selected["nested-payload"]["red"]["output"]


CACHE_MISS_IDS = (
    "explicit-anthropic-selection",
    "blank-slot-model-single",
    "blank-slot-model-paired",
    "blocked-override-not-retried",
    "unblocked-model1-shared",
    "explicit-model2",
    "github-slot-selection",
    "github-slot-selection-paired",
    "github-constructor-miss",
    "blocked-slot-model-single",
    "blocked-slot-model-paired",
    "configured-slot-file-miss",
    "empty-channel-cache-hit",
    "empty-option-cache-hit",
)


def test_cache_miss_receipts_name_a_restored_failure() -> None:
    record = _load()
    by_id = {item["id"]: item for item in record["receipts"]}
    assert set(CACHE_MISS_IDS) <= set(by_id)
    sources = {
        path: _recorded_source(path)
        for path in ("tools/langchain_client.py", "scripts/langchain/pr_verifier.py")
    }
    digests = {
        path: hashlib.sha256(source.encode()).hexdigest() for path, source in sources.items()
    }
    assert digests["tools/langchain_client.py"] == (
        "dbe98ec39a46841bcd18969ca7e56637f0ba38ffcaae80195071f9247a7e7174"
    )
    assert digests["scripts/langchain/pr_verifier.py"] == (
        "f2f0993b3b909d2317bad6a751886c38a0956efb1859d085415f67e3da72f478"
    )
    blocked = [
        by_id["blocked-slot-model-single"]["nodeid"],
        by_id["blocked-slot-model-paired"]["nodeid"],
    ]
    assert blocked[0] == blocked[1]
    assert blocked[0].endswith("test_resolver_blocked_slot_model_is_not_built")
    for item_id in CACHE_MISS_IDS:
        item = by_id[item_id]
        validate_receipt(item, sources[item["source"]], source_sha256=digests[item["source"]])


def test_prior_mutation_transcripts_stay_unavailable() -> None:
    record = _load()
    missing = record["unavailable_prior_receipts"]
    assert "39003191738" in missing["pr_4000"]
    assert "nested-list" in missing["pr_4000"]
    assert "duplicate-verdict" in missing["pr_4000"]
    assert "/tmp/3998-mutation-transcript.txt" in missing["pr_4405"]
    assert "not a GitHub Actions artifact" in missing["pr_4405"]
    prose = RECEIPTS_MD.read_text(encoding="utf-8")
    assert record["checked_on"] in prose
    assert "about 180" in prose
    for receipt in record["receipts"]:
        assert receipt["id"] in prose
        assert f"red exit {receipt['red']['exit_code']}" in prose
        assert f"green exit {receipt['green']['exit_code']}" in prose
    assert "f2f0993b3b909d2317bad6a751886c38a0956efb1859d085415f67e3da72f478" in prose
    assert "18d6a89ee9894496342d22385fae79019d36a4f5ca67940b9b44c49d43d22ff7" in prose


def test_validator_rejects_a_mutant_that_does_not_fail() -> None:
    record = _load()
    source = _recorded_source("scripts/langchain/pr_verifier.py")
    receipt = copy.deepcopy(record["receipts"][0])
    receipt["red"]["exit_code"] = 0
    with pytest.raises(ValueError, match="red exit"):
        validate_receipt(receipt, source, source_sha256=receipt["restored_sha256"])

    unrestored = copy.deepcopy(record["receipts"][0])
    mutated = source.replace(unrestored["original_snippet"], unrestored["mutant_snippet"], 1)
    with pytest.raises(ValueError, match="mutant snippet"):
        validate_receipt(unrestored, mutated, source_sha256=unrestored["restored_sha256"])


def test_historical_receipts_do_not_read_live_production(monkeypatch, tmp_path: Path) -> None:
    # A future checkout can move symbols and tests without rewriting old receipts.
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    for receipt in _load()["receipts"]:
        source = _recorded_source(receipt["source"])
        validate_receipt(receipt, source, source_sha256=receipt["restored_sha256"])


def test_validator_rejects_forged_source_or_unchanged_mutant() -> None:
    receipt = copy.deepcopy(_load()["receipts"][0])
    source = _recorded_source(receipt["source"])
    with pytest.raises(ValueError, match="restored sha256"):
        validate_receipt(receipt, source + "\n", source_sha256=receipt["restored_sha256"])
    receipt["mutant_sha256"] = receipt["restored_sha256"]
    with pytest.raises(ValueError, match="mutation did not change"):
        validate_receipt(receipt, source, source_sha256=receipt["restored_sha256"])


def test_follow_up_receipts_bind_final_tests_and_both_client_implementations() -> None:
    record = _load()
    sources = {}
    for path, entry in record["follow_up_recorded_source"]["files"].items():
        data = (EVIDENCE / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        sources[path] = data.decode()
    receipts = record["follow_up_receipts"]
    assert len(receipts) == 14
    assert len({item["id"] for item in receipts}) == 14
    assert record["follow_up_production_restored"] is True
    for receipt in receipts:
        source = sources[receipt["source"]]
        assert hashlib.sha256(source.encode()).hexdigest() == receipt["restored_sha256"]
        assert source.count(receipt["original_snippet"]) == 1
        assert receipt["mutant_snippet"] not in source, "mutant snippet remains"
        mutated = source.replace(receipt["original_snippet"], receipt["mutant_snippet"], 1)
        assert hashlib.sha256(mutated.encode()).hexdigest() == receipt["mutant_sha256"]
        test_path = receipt["nodeid"].split("::")[0]
        assert hashlib.sha256(sources[test_path].encode()).hexdigest() == receipt["test_sha256"]
        for phase, exit_code, summary in (("red", 1, "1 failed"), ("green", 0, "1 passed")):
            run = receipt[phase]
            assert run["exit_code"] == exit_code
            assert run["elapsed_seconds"] < 120
            assert summary in run["output"]
            assert receipt["nodeid"] in run["command"]
            assert any(
                run["command"][i : i + 2] == ["-m", "not slow"]
                for i in range(len(run["command"]) - 1)
            ), "missing not slow marker"
        assert receipt["nodeid"] in receipt["red_named_failure"]
        assert receipt["red_named_failure"] in receipt["red"]["output"], "fabricated named failure"

    regressions = record["follow_up_regressions"]
    assert {item["source"] for item in regressions} == {
        "tools/langchain_client.py",
        "templates/consumer-repo/tools/langchain_client.py",
    }
    for item in regressions:
        original = (EVIDENCE / item["original_snapshot"]).read_bytes()
        assert (
            hashlib.sha256(original).hexdigest() == item["original_sha256"]
        ), "original snapshot digest"
        for phase in ("red", "green"):
            command = item[phase]["command"]
            assert any(
                command[i : i + 2] == ["-m", "not slow"] for i in range(len(command) - 1)
            ), "missing not slow marker"
        assert f"FAILED {item['nodeid']}" in item["red"]["output"], "fabricated regression failure"
        assert item["red"]["exit_code"] == 1
        assert item["green"]["exit_code"] == 0
        assert item["nodeid"] in item["red"]["output"]
        assert item["original_sha256"] != item["fixed_sha256"]
        assert hashlib.sha256(sources[item["source"]].encode()).hexdigest() == item["fixed_sha256"]


@pytest.mark.parametrize("corruption", ["snapshot", "failure", "marker"])
def test_follow_up_rejects_corrupted_evidence(monkeypatch, corruption) -> None:
    record = copy.deepcopy(_load())
    if corruption == "snapshot":
        snapshot = EVIDENCE / record["follow_up_regressions"][0]["original_snapshot"]
        read_bytes = Path.read_bytes
        monkeypatch.setattr(
            Path,
            "read_bytes",
            lambda path: read_bytes(path) + b"corrupt" if path == snapshot else read_bytes(path),
        )
        message = "original snapshot digest"
    elif corruption == "failure":
        record["follow_up_receipts"][0]["red_named_failure"] += " fabricated"
        message = "fabricated named failure"
    else:
        record["follow_up_receipts"][0]["red"]["command"].remove("not slow")
        message = "missing not slow marker"
    monkeypatch.setitem(globals(), "_load", lambda: record)
    with pytest.raises(AssertionError, match=message):
        test_follow_up_receipts_bind_final_tests_and_both_client_implementations()
