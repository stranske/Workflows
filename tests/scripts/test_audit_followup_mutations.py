"""Reject incomplete mutation receipts even when their summary claims success."""

import hashlib
import json
from pathlib import Path

import pytest
from scripts import audit_followup_mutations as auditor


@pytest.fixture
def receipts(tmp_path):
    source = "# Résumé of the inspected source\nfirst = 1\nsecond = 2\n"
    tests = "# Retained résumé cases\ndef test_before(): pass\ndef test_added(): pass\n"
    cases = {f"{auditor.PYTHON_TEST}::test_added[{case}]" for case in ("a", "b")}

    def digest(text):
        return hashlib.sha256(text.encode()).hexdigest()

    python = {
        "revision": "a" * 40,
        "source_sha256": digest(source),
        "test_sha256": digest(tests),
        "proofs": [
            {
                "name": case,
                "test": case,
                "before": "first = 1",
                "mutant": "first = 0",
                "mutant_source_sha256": digest(source.replace("first = 1", "first = 0")),
                "restored_source_sha256": digest(source),
                "command": ["python", "-m", "pytest", case],
                "red_exit": 1,
                "green_exit": 0,
                "red_output": f"E AssertionError: assert 0 == 1\nFAILED {case}\n1 failed",
                "green_output": "1 passed",
            }
            for case in sorted(cases)
        ],
    }
    node = {
        "revision": "a" * 40,
        "proofs": [
            {
                "test": case,
                "before": "second = 2",
                "mutant": "second = 0",
                "source_sha256": digest(source),
                "mutant_sha256": digest(source.replace("second = 2", "second = 0")),
                "command": ["node", "--test", f"--test-name-pattern={case}", auditor.NODE_TEST],
                "red_exit": 1,
                "green_exit": 0,
                "red_output": f"{case}\nAssertionError [ERR_ASSERTION]",
                "green_output": f"{case}\npass 1\nfail 0",
            }
            for case in sorted(auditor.NODE_CASES)
        ],
    }
    files = {
        auditor.PYTHON_SOURCE: source,
        auditor.PYTHON_TEST: tests,
        auditor.NODE_SOURCE: source,
        auditor.NODE_TEST: "\n".join(f"test('{case}', () => {{}});" for case in auditor.NODE_CASES),
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run():
        directory = tmp_path / auditor.EVIDENCE
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "retained-mutation-reconciliation.json").write_text(json.dumps(python))
        (directory / "numbered-checklist-repair-proof.json").write_text(json.dumps(node))
        return auditor.audit(tmp_path, "def test_before(): pass\n", cases)

    return python, node, cases, run


def test_complete_receipts_cover_each_independently_collected_parameter(receipts):
    result = receipts[-1]()
    assert result["complete"] is True
    assert result["added_functions"] == 1
    assert result["collected_added_cases"] == 2
    assert len(result["receipts"]) == 4


def test_missing_parameter_is_not_hidden_by_other_receipts(receipts):
    python, _, _, run = receipts
    python["proofs"].pop()
    result = run()
    assert result["complete"] is False
    assert "missing=" in " ".join(result["problems"])
    assert "test_added[b]" in " ".join(result["problems"])


def test_utf8_inputs_preserve_hashes_with_a_legacy_default_encoding(receipts, monkeypatch):
    """Locale decoding must not change the bytes identified by source hashes."""
    read_text = Path.read_text

    def legacy_read_text(path, encoding=None, errors=None):
        return read_text(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", legacy_read_text)
    result = receipts[-1]()
    assert result["complete"] is True, result["problems"]


@pytest.mark.parametrize("failure", ["", f"FAILED {auditor.PYTHON_TEST}::test_other\n"])
def test_python_assertion_red_must_identify_the_selected_case(receipts, failure):
    """An assertion from an absent or different case cannot validate the mutation."""
    python, _, _, run = receipts
    python["proofs"][0]["red_output"] = f"E AssertionError: assert 0 == 1\n{failure}1 failed"
    result = run()
    assert result["complete"] is False
    assert result["receipts"][0]["issues"] == ["RED/GREEN does not identify a single selected case"]


@pytest.mark.parametrize("language", ["python", "node"])
@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        ("red_exit", 2, "RED is not an assertion failure"),
        ("red_output", "ImportError during collection", "RED is not an assertion failure"),
        ("green_exit", 1, "GREEN exit is not 0"),
        ("green_output", "", "GREEN"),
        ("command", ["pytest", "different-case"], "command does not select"),
        ("mutant", "second = 99", "does not reproduce its source hash"),
    ],
)
def test_invalid_receipts_cannot_establish_completion(receipts, language, field, value, problem):
    python, node, _, run = receipts
    (python if language == "python" else node)["proofs"][0][field] = value
    result = run()
    assert result["complete"] is False
    assert any(problem in issue for row in result["receipts"] for issue in row["issues"])


def test_abbreviated_assertion_diff_stays_incomplete(receipts):
    python, _, _, run = receipts
    python["proofs"][0]["red_output"] += "\nFull output truncated (4 lines hidden)"
    result = run()
    assert result["complete"] is False
    assert result["receipts"][0]["issues"] == ["receipt output is truncated"]


def test_truncated_is_valid_payload_text_not_an_output_diagnostic(receipts):
    python, _, _, run = receipts
    python["proofs"][0]["red_output"] += "\nE expected 'CSV trailer is truncated'"
    assert run()["complete"] is True


def test_oserror_receipt_with_assertionerror_in_test_body_is_not_assertion_red(receipts):
    python, _, _, run = receipts
    python["proofs"][0]["red_output"] = (
        '    raise AssertionError("read_text must not run")\n'
        "E OSError: File name too long\n"
        f"FAILED {python['proofs'][0]['test']}\n1 failed"
    )
    result = run()
    assert result["complete"] is False
    assert "RED is not an assertion failure" in result["receipts"][0]["issues"][0]


def test_source_or_test_drift_invalidates_otherwise_green_receipts(receipts):
    python, _, _, run = receipts
    python["test_sha256"] = "b" * 64
    result = run()
    assert result["complete"] is False
    assert "hashes do not match" in result["problems"][0]


def test_missing_collection_cannot_prove_all_added_tests(receipts):
    _, _, cases, run = receipts
    cases.clear()
    result = run()
    assert result["complete"] is False
    assert "test_added" in result["problems"][0]


def test_same_text_at_different_location_must_reproduce_recorded_hash():
    source = "first = 1\nfirst = 1\n"
    second_mutated = "first = 1\nfirst = 0\n"
    assert auditor._matches_mutation(
        source, "first = 1", "first = 0", hashlib.sha256(second_mutated.encode()).hexdigest()
    )
    assert not auditor._matches_mutation(source, "first = 1", "first = 0", "b" * 64)


def test_different_revisions_cannot_be_silently_combined(receipts):
    _, node, _, run = receipts
    node["revision"] = "b" * 40
    result = run()
    assert result["complete"] is False
    assert "different source revisions" in result["problems"][0]


@pytest.mark.parametrize("revision", ["", "main", "a" * 8, "z" * 40, None])
def test_equal_nonimmutable_revisions_cannot_prove_source_identity(receipts, revision):
    python, node, _, run = receipts
    python["revision"] = node["revision"] = revision
    result = run()
    assert result["complete"] is False
    assert "Python receipt revision must be a full commit SHA" in result["problems"]
    assert "Node receipt revision must be a full commit SHA" in result["problems"]


def test_missing_revision_is_reported_as_incomplete(receipts):
    python, node, _, run = receipts
    del python["revision"], node["revision"]
    result = run()
    assert result["complete"] is False
    assert "Python receipt revision must be a full commit SHA" in result["problems"]
    assert "Node receipt revision must be a full commit SHA" in result["problems"]


def test_each_audit_row_identifies_its_receipt_and_source_revision(receipts):
    result = receipts[-1]()
    assert result["complete"] is True
    for row in result["receipts"]:
        assert row["source_revision"] == "a" * 40
        assert row["receipt_file"] == (
            "retained-mutation-reconciliation.json"
            if row["language"] == "python"
            else "numbered-checklist-repair-proof.json"
        )


@pytest.mark.parametrize(
    ("valid_binding", "revision", "complete"),
    [
        (True, "c" * 40, True),
        (False, "c" * 40, False),
        (True, "", False),
        (True, "main", False),
        (True, None, False),
    ],
)
def test_supplement_must_bind_original_index_and_preserve_mutation(
    receipts, tmp_path, valid_binding, revision, complete
):
    python, _, _, run = receipts
    replacement = dict(python["proofs"][1], historical_index=1)
    python["proofs"][1]["red_output"] += "\nFull output truncated (4 lines hidden)"
    run()
    directory = tmp_path / auditor.EVIDENCE
    supplement = {
        "revision": revision,
        "historical_sha256": hashlib.sha256(
            (directory / "retained-mutation-reconciliation.json").read_bytes()
        ).hexdigest(),
        "source_sha256": python["source_sha256"],
        "test_sha256": python["test_sha256"],
        "proofs": [replacement],
    }
    if not valid_binding:
        supplement["historical_sha256"] = "b" * 64
    (directory / "retained-mutation-unabridged-reruns.json").write_text(json.dumps(supplement))
    result = run()
    assert result["complete"] is complete
    assert result["rerun_revision"] == (revision if complete else None)
    row = result["receipts"][1]
    assert row["source_revision"] == (revision if complete else "a" * 40)
    assert row["receipt_file"] == (
        "retained-mutation-unabridged-reruns.json"
        if complete
        else "retained-mutation-reconciliation.json"
    )
    assert row["receipt_index"] == (0 if complete else 1)
    assert row["historical_index"] == 1
    # Other rows must retain their original provenance when a supplement is used.
    assert all(
        row["source_revision"] == "a" * 40
        for index, row in enumerate(result["receipts"])
        if index != 1
    )
