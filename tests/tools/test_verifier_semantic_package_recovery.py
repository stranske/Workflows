"""Historical recovered bytes must close a real proof chain, never global acceptance."""

import json
import shutil
from pathlib import Path

import pytest
from tools.verifier_semantic_package_recovery import recover_package, sha

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "evidence/issue-3820/historical-all-arms-recovery-20261011"
PLAN = ROOT / "evidence/issue-3820/resource-admission-20261011/original-resource-plan.json"


@pytest.fixture
def package(tmp_path):
    folder = tmp_path / "proof"
    shutil.copytree(SOURCE, folder)
    return folder


def test_actual_historical_source_recovery_preserves_global_floor(package):
    result = recover_package(package, PLAN)
    original = json.loads(PLAN.read_bytes())["capture_reassembly_contract"]
    assert result["historical_proof_chain_recovered"] is True
    assert result["global_dependency_contract"] == original
    assert len(original["obligations"]) == 277
    assert len(original["gaps"]) == 163
    assert len(original["required_range_ids"]) == 60
    assert result["acceptance_sufficient"] is False
    assert result["semantic_independence_proven"] is False
    assert result["provider_calls"] == 0


@pytest.mark.parametrize(
    "member",
    [
        "original-workflow.yml",
        "repaired-workflow.yml",
        "mutant-workflow.yml",
        "historical-test.py",
        "historical-source.py",
        "historical-template-source.py",
        "mutation-red.txt",
        "mutation-red.xml",
        "restored-green.txt",
        "restored-green.xml",
        "original-transform-call.txt",
    ],
)
def test_changed_historical_member_cannot_satisfy_package(package, member):
    path = package / member
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="mismatch|changed"):
        recover_package(package, PLAN)


def test_missing_raw_red_is_not_a_proof(package):
    (package / "mutation-red.txt").unlink()
    with pytest.raises(FileNotFoundError):
        recover_package(package, PLAN)


def test_changed_historical_edit_cannot_reconstruct_source(package):
    path = package / "historical-transform.json"
    data = json.loads(path.read_bytes())
    data["new"] += "\n"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="replay"):
        recover_package(package, PLAN)


@pytest.mark.parametrize("field", ["obligations", "gaps", "required_range_ids"])
def test_recovered_chain_cannot_drop_global_dependency(package, field):
    path = package / "global-contract.json"
    data = json.loads(path.read_bytes())
    data[field].pop()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="global dependency"):
        recover_package(package, PLAN)


@pytest.mark.parametrize(
    "replacement",
    [
        b'<testsuites><testsuite><testcase name="collection"><error/></testcase></testsuite></testsuites>',
        b'<testsuites><testsuite><testcase name="wrong"><failure message="AssertionError:"/></testcase></testsuite></testsuites>',
        b'<!DOCTYPE test [<!ENTITY x "unsafe">]><testsuites/>',
    ],
)
def test_even_rebound_fixture_or_collection_red_cannot_be_accepted(package, replacement):
    (package / "mutation-red.xml").write_bytes(replacement)
    path = package / "proof.json"
    proof = json.loads(path.read_bytes())
    proof["mutation-red_raw_sha256"]["xml"] = sha(replacement)
    path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="selected|declarations"):
        recover_package(package, PLAN)


def test_nonidentical_restoration_is_not_green(package):
    path = package / "proof.json"
    proof = json.loads(path.read_bytes())
    proof["restored_workflow_sha256"] = "0" * 64
    path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="restoration"):
        recover_package(package, PLAN)
