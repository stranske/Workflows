"""Recover a historical all-arms proof chain without upgrading native acceptance.

This offline tool binds original source, exact historical edits, selected assertion
RED/restored GREEN, and the unchanged global dependency contract. It does not
execute historical shell/code, call providers, or certify semantic independence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(folder: Path, name: str) -> bytes:
    raw = (folder / name).read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError(f"oversized proof member: {name}")
    return raw


def _nodes(raw: bytes, *, red: bool) -> list[str]:
    # Reject declarations before parsing; historical JUnit needs no DTD/entities.
    if b"<!" in raw:
        raise ValueError("JUnit declarations are forbidden")
    root = ET.fromstring(raw)
    nodes = list(root.iter("testcase"))
    if len(nodes) != 2 or list(root.iter("error")) or list(root.iter("skipped")):
        raise ValueError("proof needs exactly two selected cases without errors/skips")
    identities = []
    for node in nodes:
        identity = node.attrib.get("classname", "") + "::" + node.attrib.get("name", "")
        if not identity.startswith(
            "tests.workflows.test_verifier_expanded_comparison::"
            "test_expanded_each_arm_blocks_pass[used-false-"
        ):
            raise ValueError("unexpected historical selected test")
        failures = node.findall("failure")
        if red:
            if len(failures) != 1 or "AssertionError:" not in failures[0].get("message", ""):
                raise ValueError("RED must be a selected assertion failure")
        elif failures:
            raise ValueError("restored GREEN must have no failures")
        identities.append(identity)
    if len(set(identities)) != 2:
        raise ValueError("duplicate selected test")
    return sorted(identities)


def recover_package(folder: Path, resource_plan: Path) -> dict:
    """Validate recovered bytes against original proof; retain every global gap."""
    proof = json.loads(_read(folder, "proof.json"))
    verification = json.loads(_read(folder, "verification.json"))
    provenance = json.loads(_read(folder, "provenance.json"))
    transform = json.loads(_read(folder, "historical-transform.json"))
    members = {}
    bindings = {
        "original-workflow.yml": "original_workflow_sha256",
        "repaired-workflow.yml": "repaired_workflow_sha256",
        "mutant-workflow.yml": "mutated_workflow_sha256",
        "historical-test.py": "test_sha256",
        "historical-source.py": "source_sha256",
        "historical-template-source.py": "template_source_sha256",
    }
    raw_members = {}
    governing = _read(folder, "governing-source.md")
    if (
        sha(governing)
        != verification["sha256"]["evidence/issue-3820/expanded-comparison-all-arms-repair.md"]
    ):
        raise ValueError("governing historical source hash mismatch")
    if (
        sha(_read(folder, "proof.json"))
        != verification["sha256"]["evidence/issue-3820/expanded-comparison-proof.json"]
    ):
        raise ValueError("historical proof receipt binding mismatch")
    members["governing-source.md"] = sha(governing)
    for name, key in bindings.items():
        raw = _read(folder, name)
        if sha(raw) != proof[key]:
            raise ValueError(f"historical hash mismatch: {name}")
        raw_members[name] = raw
        members[name] = sha(raw)
    if raw_members["historical-source.py"] != raw_members["historical-template-source.py"]:
        raise ValueError("historical source/template parity differs")
    if proof["repaired_workflow_sha256"] != proof["restored_workflow_sha256"]:
        raise ValueError("restoration is not byte-identical")
    original = raw_members["original-workflow.yml"].decode("utf-8")
    if original.count(transform["old"]) != 1 or not transform["old"] or not transform["new"]:
        raise ValueError("historical aggregation edit is not unique")
    repaired = original.replace(transform["old"], transform["new"]).replace(
        "bounded-native-capacity-v4", "bounded-native-capacity-v5"
    )
    mutant = original.replace("bounded-native-capacity-v4", "bounded-native-capacity-v5")
    if repaired.encode() != raw_members["repaired-workflow.yml"]:
        raise ValueError("repaired bytes do not replay the original edit")
    if mutant.encode() != raw_members["mutant-workflow.yml"]:
        raise ValueError("mutant bytes do not retain the original aggregation")
    if proof["red"]["exit_code"] != 1 or proof["green"]["exit_code"] != 0:
        raise ValueError("historical exit codes are not RED/GREEN")
    selected = []
    for suffix, red in [("mutation-red", True), ("restored-green", False)]:
        for ext in ["txt", "xml"]:
            name = f"{suffix}.{ext}"
            raw = _read(folder, name)
            if sha(raw) != proof[f"{suffix}_raw_sha256"][ext]:
                raise ValueError(f"raw historical proof mismatch: {name}")
            members[name] = sha(raw)
            if ext == "xml":
                selected.append(_nodes(raw, red=red))
    if selected[0] != selected[1]:
        raise ValueError("RED/GREEN selected test identities differ")
    if sha(_read(folder, "original-transform-call.txt")) != provenance["transform_call_sha256"]:
        raise ValueError("original execution edit record changed")
    contract = json.loads(_read(folder, "global-contract.json"))
    expected = json.loads(resource_plan.read_bytes())["capture_reassembly_contract"]
    if contract != expected or contract.get("dependency_policy") != "all-captured-inputs":
        raise ValueError("global dependency contract changed")
    return {
        "schema": "workflows-verifier-historical-proof-package/v1",
        "claim": "expanded comparison cannot PASS when either configured arm has used_llm=false",
        "historical_proof_chain_recovered": True,
        "acceptance_sufficient": False,
        "semantic_independence_proven": False,
        "provider_calls": 0,
        "scope": "historical stubbed-CLI workflow proof, not current-head/native acceptance",
        "members": members,
        "selected_test_identities": selected[0],
        "provenance": provenance,
        "related_original_obligations": [
            item["id"]
            for item in contract["obligations"]
            if item["value"]["source"]
            in {
                ".github/workflows/reusable-agents-verifier.yml",
                "scripts/langchain/pr_verifier.py",
                "templates/consumer-repo/scripts/langchain/pr_verifier.py",
                "tests/workflows/test_verifier_expanded_comparison.py",
                "evidence/issue-3820/expanded-comparison-all-arms-repair.md",
                "evidence/issue-3820/expanded-comparison-proof.json",
                "evidence/issue-3820/expanded-comparison-mutation-red.txt",
                "evidence/issue-3820/expanded-comparison-mutation-red.xml",
                "evidence/issue-3820/expanded-comparison-restored-green.txt",
                "evidence/issue-3820/expanded-comparison-restored-green.xml",
            }
        ],
        "related_obligations_discharged": False,
        "global_dependency_contract": contract,
        "remaining": [
            "original unavailable evidence gaps remain unchanged",
            "governing acceptance and cross-proof semantic closure",
            "cumulative resource admission and exact native full result matrix",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--resource-plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = recover_package(args.folder, args.resource_plan)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print(json.dumps({"status": "FAIL", "acceptance_sufficient": False, "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
